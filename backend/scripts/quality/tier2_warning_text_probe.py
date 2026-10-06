"""
Stage 12.3 — task 7.10 live measurement: does a Tier-2 consistency warning
describe the contradiction (what the passage did) instead of restating the rule?

For each scenario a world rule is recorded and a passage that breaks it is sent
through /api/ai/tone with controls.consistency = "strict" (pro plan, D6), N
times, through the in-process app against the allow-listed test database.
Each Tier-2 warning (kind "consistency") is classified:

  describing  — names what the passage does: either carries a verified quote of
                the passage (`evidence`) or does not merely echo the context
                (services.consistency.restates_rule == False);
  restating   — only echoes the rule.

--legacy runs the pre-12.3 prompt and post-processing (kept verbatim below,
measurement only) for a before/after comparison on the same scenarios.

  cd backend
  DATABASE_URL=…/narratiq_test python3 scripts/quality/tier2_warning_text_probe.py --runs 5 --out OUT.json [--legacy]
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SCENARIOS = [
    {"id": "harbour-lamps", "rule": "The harbour lamps are lit only by the keeper.",
     "text": "Kira waited by the window. The harbour lights went out one by one and she did not move. "
             "Elara lit the harbour lamps herself."},
    {"id": "curfew", "rule": "No one may leave the city walls after the curfew bell.",
     "text": "The curfew bell rang twice over Greyharn. Elara waited for the watch to pass, then slipped "
             "through the north gate and walked out onto the dunes beyond the walls."},
    {"id": "no-magic", "rule": "There is no magic in this world; nothing happens that the laws of nature forbid.",
     "text": "The storm pressed against the tower. Kira raised her hand, whispered a word, and the rain "
             "stopped in mid-air above the courtyard."},
    {"id": "silent-order", "rule": "Members of the Silent Order never speak aloud.",
     "text": "Brother Anselm of the Silent Order met them at the gate. \"You are late,\" he said loudly, "
             "\"and the abbot will not wait.\""},
]


def _legacy_patch():
    """The 2026-09-25 Tier-2 prompt and post-processing, verbatim (before 7.10)."""
    from services import consistency

    def legacy_coerce(parsed):
        if not isinstance(parsed, dict) or not isinstance(parsed.get("issues"), list):
            return None, 1
        out, dropped = [], 0
        for it in parsed["issues"][:4]:
            if isinstance(it, dict) and str(it.get("message") or "").strip():
                out.append({"kind": "consistency", "severity": "soft",
                            "message": str(it["message"]).strip()[:300],
                            "entity": {"type": str(it.get("kind") or "fact")}})
            else:
                dropped += 1
        return out, dropped

    async def legacy_check(block, output):
        if not block.strip():
            return [], False
        from services.ai_service import complete_structured
        system = (
            "You check a rewritten passage against established story context. Report ONLY clear "
            "contradictions of the context (a character acting against a recorded trait, a broken world "
            "rule, a contradicted fact). Do not report style issues. Return ONLY JSON: "
            '{"issues": [{"kind": "trait|world_rule|fact", "message": "one short sentence"}]} '
            'Return {"issues": []} when there is no clear contradiction.'
        )
        try:
            value, _ = await complete_structured(system, f"{block}\n\nREWRITTEN PASSAGE:\n{output[:6000]}",
                                                 coerce=legacy_coerce, temperature=0.1, max_tokens=300,
                                                 label="strict_consistency")
        except Exception:
            return [], False
        return (value or []), value is not None

    consistency.strict_consistency_check = legacy_check


def classify(w: dict, rule: str, passage_out: str) -> str:
    from services.consistency import restates_rule
    if w.get("evidence"):
        return "describing"
    return "restating" if restates_rule(w.get("message", ""), rule, "", passage_out) else "describing"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--legacy", action="store_true")
    a = ap.parse_args()
    if a.legacy:
        _legacy_patch()

    from fastapi.testclient import TestClient
    import main as app_main
    from database import SessionLocal
    from models import Chapter, Character, Story, StoryWorldProfile, User
    from routers.auth import create_token, hash_password

    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    user = User(email=f"tier2-probe-{tag}@narratiq-internal-test.com", username=f"tier2probe{tag}",
                hashed_password=hash_password("x"), plan="pro")          # D6: Tier 2 is pro+ (D2 manual plan)
    db.add(user)
    db.commit()
    headers = {"Authorization": f"Bearer {create_token(user.user_id)}"}
    rows = []
    try:
        with TestClient(app_main.app) as c:
            for sc in SCENARIOS:
                sid = c.post("/api/projects/", headers=headers, json={"title": f"Tier-2 probe {sc['id']}"}).json()["story_id"]
                ch = db.query(Chapter).filter(Chapter.story_id == sid).first()
                for name in ("Elara", "Kira"):
                    db.add(Character(story_id=sid, user_id=user.user_id, name=name, role="supporting"))
                db.add(StoryWorldProfile(story_id=sid, world_rules=[sc["rule"]]))
                db.commit()
                for i in range(a.runs):
                    r = c.post("/api/ai/tone", headers=headers, json={
                        "story_id": sid, "chapter_id": ch.chapter_id, "text": sc["text"], "tone": "dark",
                        "controls": {"consistency": "strict"}})
                    body = r.json() if r.status_code == 200 else {}
                    out = body.get("transformed", "")
                    ws = [w for w in body.get("warnings", []) if w.get("kind") == "consistency"]
                    rows.append({"scenario": sc["id"], "run": i, "status": r.status_code,
                                 "strict_ran": (body.get("context_used") or {}).get("strict_check"),
                                 "output": out,
                                 "warnings": [{**w, "class": classify(w, sc["rule"], out)} for w in ws]})
                    print(f"  {sc['id']:13s} run {i}: {[(w['class'], w['message'][:90]) for w in rows[-1]['warnings']]}",
                          flush=True)
    finally:
        for s in db.query(Story).filter(Story.user_id == user.user_id).all():
            db.delete(s)
        db.delete(db.query(User).filter(User.user_id == user.user_id).first())
        db.commit()
        db.close()

    ws = [w for r in rows for w in r["warnings"]]
    summary = {
        "mode": "legacy (pre-7.10)" if a.legacy else "current (7.10)",
        "calls": len(rows), "strict_ran": sum(1 for r in rows if r["strict_ran"]),
        "calls_with_a_warning": sum(1 for r in rows if r["warnings"]),
        "warnings": len(ws),
        "describing": sum(1 for w in ws if w["class"] == "describing"),
        "restating": sum(1 for w in ws if w["class"] == "restating"),
        "with_verified_evidence": sum(1 for w in ws if w.get("evidence")),
    }
    from config import settings
    Path(a.out).write_text(json.dumps({
        "meta": {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "runs": a.runs,
                 "model": settings.vllm_model_name, "prompt_version": settings.prompt_version},
        "summary": summary, "rows": rows}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
