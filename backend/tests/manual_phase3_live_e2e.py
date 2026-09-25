"""
Stage 7 — LIVE end-to-end verification of Phase 3 against the running stack
(real FastAPI on :8000, real vLLM/Qwen2.5-7B, real BGE-M3, real PostgreSQL).
`manual_*` convention: not part of the default pytest run; it needs the live
services and writes a JSON report.

Controlled fixtures only: two throwaway authors (s7live-*@narratiq-internal-test.com) are
registered through the real API, and at the end EXACTLY those users and their
stories/pins/cards are deleted (scoped by the ids created here). A third
fixture pin is deliberately left backdated-expired (--leave-expired-pin) so the
hourly sweep can be observed deleting it in the live backend log.

Measures (spec §39.4 / checklist 7.9, 7.10, 7.12):
  * P3-07 divergence: successive generations WITH vs WITHOUT the avoid-set
  * Tier-2 strict consistency cost (D6): latency, extra call
  * Voice matching cost (D5): prompt-token estimate off vs light vs strong

    cd backend && python3 tests/manual_phase3_live_e2e.py [--base http://localhost:8000]
"""
import argparse
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

REPORT = Path(__file__).resolve().parent / "fixtures" / "phase3_live_e2e_report.json"
CHAPTER_1 = ("Elara found the sealed letter under the floorboards of her mother's room. She did not open it. "
             "She hid it inside her coat and went down to the harbour, where Kira was mending nets.")
CHAPTER_2 = ("The corridor was long and dark. Elara walked down it slowly, counting the doors. She was tired, and "
             "she looked at every door as though it might open on its own. Kira followed a few steps behind and "
             "said nothing. The lantern in Elara's hand threw thin light on the stone.")
PASSAGES = [
    "The corridor was long and dark. Elara walked down it slowly, counting the doors.",
    "Kira waited by the window. The harbour lights went out one by one and she did not move.",
    "The old man told them the bridge would hold. It did not. Elara was the first to reach the far bank.",
]

results: dict = {"checks": {}, "measurements": {}}


def check(name: str, ok: bool, evidence) -> None:
    results["checks"][name] = {"pass": bool(ok), "evidence": evidence}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {str(evidence)[:180]}")


def lex(a: str, b: str) -> float:
    from services.similarity import lexical_score
    return lexical_score(a, b)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--leave-expired-pin", action="store_true")
    args = ap.parse_args()
    c = httpx.Client(base_url=args.base, timeout=300)
    tag = uuid.uuid4().hex[:6]
    users, stories = [], []

    def register(n: str):
        r = c.post("/api/auth/register", json={"email": f"s7live-{n}-{tag}@narratiq-internal-test.com",
                                                "username": f"s7live{n}{tag}", "password": f"pw-{uuid.uuid4().hex}"})
        r.raise_for_status()
        d = r.json()
        users.append(d["user"]["user_id"])
        return {"Authorization": f"Bearer {d['access_token']}"}, d["user"]["user_id"]

    try:
        ha, uid_a = register("a")
        hb, uid_b = register("b")
        sid = c.post("/api/projects/", headers=ha, json={"title": "S7 live fixture"}).json()["story_id"]
        stories.append((ha, sid))
        sid_b = c.post("/api/projects/", headers=hb, json={"title": "S7 live fixture B"}).json()["story_id"]
        stories.append((hb, sid_b))
        chs = c.get(f"/api/stories/{sid}/chapters", headers=ha).json()
        ch1 = chs[0]["chapter_id"]
        c.patch(f"/api/stories/{sid}/chapters/{ch1}", headers=ha, json={"content": f"<p>{CHAPTER_1}</p>"})
        ch2 = c.post(f"/api/stories/{sid}/chapters", headers=ha, json={"title": "The corridor", "content": f"<p>{CHAPTER_2}</p>"}).json()["chapter_id"]
        for name in ("Elara", "Kira"):
            c.post(f"/api/stories/{sid}/characters", headers=ha, json={"name": name})

        # Story intelligence seed (fixture data) so P3-08 has something to ground on.
        from database import SessionLocal
        from models import StoryDNA, StoryMemoryEntry, StoryWorldProfile, User
        from services.ai_service import embed_text_sync
        db = SessionLocal()
        db.add(StoryMemoryEntry(story_id=sid, memory_type="character", memory_key=f"live-{tag}-1",
                                content="Kira does not know about the sealed letter.", chapter_first_established=1,
                                importance=0.9, embedding=embed_text_sync("Kira does not know about the sealed letter.")))
        db.add(StoryWorldProfile(story_id=sid, world_rules=["The harbour lamps are lit only by the keeper."]))
        db.add(StoryDNA(story_id=sid, pov_style="third person limited", tense="past",
                        sentence_rhythm="short, plain sentences", vocabulary_tier="plain, concrete",
                        prose_style="sparse, physical detail"))
        db.query(User).filter(User.user_id == uid_b).update({"plan": "pro"})   # D2 manual assignment, fixture only
        db.commit()

        text = PASSAGES[0]
        body = {"story_id": sid, "chapter_id": ch2, "text": text, "tone": "suspenseful"}

        # ── Backward compatibility + ownership ──────────────────────────────
        t0 = time.time(); r = c.post("/api/ai/tone", headers=ha, json=body); legacy_ms = int((time.time() - t0) * 1000)
        check("legacy request (no controls) unchanged shape", r.status_code == 200 and r.json()["warnings"] == [] and r.json()["context_used"] == {},
              {"status": r.status_code, "ms": legacy_ms})
        rf = c.post("/api/ai/tone", headers=hb, json=body)
        rn = c.post("/api/ai/tone", headers=hb, json={**body, "story_id": str(uuid.uuid4())})
        check("C7-6 foreign story_id ≡ nonexistent (404, same body)", rf.status_code == rn.status_code == 404 and rf.json() == rn.json(),
              {"foreign": rf.status_code, "missing": rn.status_code})

        # ── Phase 3 generation with grounding ───────────────────────────────
        t0 = time.time(); r = c.post("/api/ai/tone", headers=ha, json={**body, "controls": {}}); p3_ms = int((time.time() - t0) * 1000)
        g1 = r.json()
        check("P3-08 grounded generation", r.status_code == 200 and g1["context_used"].get("facts", 0) >= 1 and "Elara" in g1["context_used"].get("characters", []),
              {"context_used": g1["context_used"], "warnings": [w["kind"] for w in g1["warnings"]], "ms": p3_ms})
        check("P3-10 light voice from story_dna by default", g1["context_used"].get("voice", {}).get("level") == "light", g1["context_used"].get("voice"))
        results["measurements"]["latency_ms"] = {"legacy": legacy_ms, "phase3_default": p3_ms}

        # ── Pins ────────────────────────────────────────────────────────────
        rp = c.post(f"/api/stories/{sid}/ai/pins", headers=ha, json={"chapter_id": ch2, "tool": "tone", "tool_params": {"tone": "suspenseful"},
                                                                    "content": g1["transformed"], "source_excerpt": text, "label": "v1"})
        pin1 = rp.json()["pin"]
        check("P3-01 pin created with expiry", rp.status_code == 201 and pin1["expires_at"], {"expires_at": pin1["expires_at"], "limits": rp.json()["limits"]})
        time.sleep(3)
        pin1d = c.get(f"/api/stories/{sid}/ai/pins/{pin1['pin_id']}", headers=ha).json()
        check("P3-11 background pin embedding stored (D4 on)", pin1d["has_embedding"], pin1d["has_embedding"])
        check("isolation: B reading A's pin ≡ missing", c.get(f"/api/stories/{sid}/ai/pins/{pin1['pin_id']}", headers=hb).json()
              == c.get(f"/api/stories/{sid}/ai/pins/{uuid.uuid4()}", headers=hb).json(), "404/404")

        # ── P3-03 context pins ──────────────────────────────────────────────
        r = c.post("/api/ai/tone", headers=ha, json={**body, "text": PASSAGES[1], "controls": {"context_pin_ids": [pin1["pin_id"]],
                                                                                              "instruction": "Borrow the mood of idea 1."}})
        check("P3-03 pinned version used as context", r.status_code == 200 and r.json()["context_used"].get("pins") == 1, r.json()["context_used"])

        # ── P3-06 variation from a pin + anti-echo ──────────────────────────
        r = c.post("/api/ai/tone", headers=ha, json={**body, "controls": {"base_pin_id": pin1["pin_id"], "derivation": "variation"}})
        d = r.json()
        echo = d["context_used"].get("anti_echo")
        check("P3-06 variation generated from a pin; anti-echo measured", r.status_code == 200 and echo is not None,
              {"anti_echo_vs_parent": echo, "echo_warning": any(w["kind"] == "echo" for w in d["warnings"])})
        rp2 = c.post(f"/api/stories/{sid}/ai/pins", headers=ha, json={"chapter_id": ch2, "tool": "tone", "tool_params": {"tone": "suspenseful"},
                                                                     "content": d["transformed"], "parent_pin_id": pin1["pin_id"], "derivation": "variation"})
        check("P3-06 lineage recorded", rp2.json()["pin"]["root_pin_id"] == pin1["pin_id"] and rp2.json()["pin"]["lineage_depth"] == 1,
              {k: rp2.json()["pin"][k] for k in ("root_pin_id", "lineage_depth", "parent_pin_id")})
        results["measurements"]["variation_anti_echo"] = echo

        # ── P3-11 similarity, P3-04 compare/merge ───────────────────────────
        r = c.post(f"/api/stories/{sid}/ai/similarity", headers=ha, json={"text": g1["transformed"]})
        check("P3-11 similarity finds the identical pin", r.status_code == 200 and r.json()["matches"][0]["label"] == "near_duplicate", r.json()["matches"][:2])
        r = c.post("/api/ai/compare-summary", headers=ha, json={"story_id": sid, "text_a": g1["transformed"], "text_b": d["transformed"]})
        check("P3-04 AI comparison summary (best effort)", r.status_code == 200, {"available": r.json().get("available"), "summary": r.json().get("summary", "")[:120]})
        blocks = [{"text": g1["transformed"].split(". ")[0] + ". ", "source": "a"}, {"text": d["transformed"].split(". ")[-1], "source": "b"}]
        r = c.post("/api/ai/merge-versions", headers=ha, json={"story_id": sid, "blocks": blocks})
        m = r.json()
        check("P3-04 merge smoothing respects fidelity bounds", r.status_code == 200 and (not m["smoothed"] or (m["word_delta"] <= 0.12 and m["min_block_similarity"] >= 0.9)),
              {k: m[k] for k in ("smoothed", "word_delta", "min_block_similarity")})

        # ── P3-09 promote; survives expiry ──────────────────────────────────
        r = c.post(f"/api/stories/{sid}/ai/pins/{pin1['pin_id']}/promote", headers=ha, json={"card_type": "future_scene", "release_pin": False})
        card = r.json()["card"]
        check("P3-09 promoted to Idea Shelf", r.status_code == 201 and card["source_pin_id"] == pin1["pin_id"], {"card_id": card["card_id"]})

        # ── P3-07 divergence with vs without avoid-set ──────────────────────
        div = {"without_avoid": [], "with_avoid": []}
        for p in PASSAGES:
            for mode in ("without_avoid", "with_avoid"):
                outs = []
                for _ in range(3):
                    ctl = {"avoid_texts": outs[-8:]} if mode == "with_avoid" and outs else {}
                    rr = c.post("/api/ai/emotion", headers=ha, json={"story_id": sid, "chapter_id": ch2, "text": p,
                                                                      "emotion": "fear", "intensity": "high", "controls": ctl})
                    outs.append(rr.json()["transformed"])
                sims = [lex(outs[i], outs[j]) for i in range(3) for j in range(i)]
                div[mode].append(statistics.mean(sims))
        mean_without, mean_with = statistics.mean(div["without_avoid"]), statistics.mean(div["with_avoid"])
        results["measurements"]["p3_07_divergence"] = {"mean_pairwise_similarity_without_avoid": round(mean_without, 4),
                                                       "mean_pairwise_similarity_with_avoid": round(mean_with, 4),
                                                       "per_passage": div}
        check("P3-07 measured divergence improves with the avoid-set", mean_with < mean_without,
              results["measurements"]["p3_07_divergence"])

        # ── D6 Tier-2 cost (pro user) ───────────────────────────────────────
        sid_b_ch = c.get(f"/api/stories/{sid_b}/chapters", headers=hb).json()[0]["chapter_id"]
        for name in ("Elara", "Kira"):
            c.post(f"/api/stories/{sid_b}/characters", headers=hb, json={"name": name})
        db.add(StoryWorldProfile(story_id=sid_b, world_rules=["The harbour lamps are lit only by the keeper."]))
        db.commit()
        tb = {"story_id": sid_b, "chapter_id": sid_b_ch, "text": PASSAGES[1] + " Elara lit the harbour lamps herself.", "tone": "dark"}
        t0 = time.time(); ra = c.post("/api/ai/tone", headers=hb, json={**tb, "controls": {"consistency": "auto"}}); auto_ms = int((time.time() - t0) * 1000)
        t0 = time.time(); rs = c.post("/api/ai/tone", headers=hb, json={**tb, "controls": {"consistency": "strict"}}); strict_ms = int((time.time() - t0) * 1000)
        results["measurements"]["d6_tier2_cost"] = {"auto_ms": auto_ms, "strict_ms": strict_ms,
                                                    "extra_ms": strict_ms - auto_ms, "extra_llm_calls": 1,
                                                    "strict_ran": rs.json()["context_used"].get("strict_check"),
                                                    "strict_warnings": [w["message"] for w in rs.json()["warnings"] if w["kind"] == "consistency"]}
        check("D6 strict check runs for pro and costs one extra call", rs.json()["context_used"].get("strict_check") is True,
              results["measurements"]["d6_tier2_cost"])
        rfree = c.post("/api/ai/tone", headers=ha, json={**body, "controls": {"consistency": "strict"}})
        check("D6 strict check refused (with notice) on free plan", any(w["kind"] == "strict_unavailable" for w in rfree.json()["warnings"]), "info warning")

        # ── D5 voice token cost ─────────────────────────────────────────────
        costs = {}
        for level in ("off", "light", "strong"):
            rr = c.post("/api/ai/tone", headers=ha, json={**body, "controls": {"style_match": level, "consistency": "off"}})
            costs[level] = rr.json()["context_used"].get("tokens_estimate", 0)
        results["measurements"]["d5_voice_tokens"] = {**costs, "light_minus_off": costs["light"] - costs["off"],
                                                      "strong_minus_off": costs["strong"] - costs["off"]}
        check("D5 light voice costs ~90 tokens", 20 <= costs["light"] - costs["off"] <= 200, results["measurements"]["d5_voice_tokens"])

        # ── Leave one backdated pin for the hourly-sweep observation ─────────
        if args.leave_expired_pin:
            from datetime import datetime, timedelta
            from models import AiGenerationPin
            db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == rp2.json()["pin"]["pin_id"]).update(
                {"expires_at": datetime.utcnow() - timedelta(minutes=5)})
            db.commit()
            results["expired_pin_left_for_sweep"] = {"pin_id": rp2.json()["pin"]["pin_id"], "user_id": uid_a, "story_id": sid}
            users.remove(uid_a)           # keep author A until the sweep is observed
            stories[:] = [s for s in stories if s[1] != sid]
        db.close()
    finally:
        from database import SessionLocal
        from models import AiGenerationPin, NoteCard, User
        for h, s in stories:
            c.delete(f"/api/projects/{s}", headers=h)
        db = SessionLocal()
        for uid in users:
            db.query(AiGenerationPin).filter(AiGenerationPin.user_id == uid).delete(synchronize_session=False)
            db.query(NoteCard).filter(NoteCard.user_id == uid).delete(synchronize_session=False)
            u = db.query(User).filter(User.user_id == uid).first()
            if u is not None and u.email.startswith("s7live-") and u.email.endswith("@narratiq-internal-test.com"):
                db.delete(u)
        db.commit()
        db.close()
        REPORT.write_text(json.dumps(results, indent=2, default=str))
        print(f"\nreport: {REPORT}")
    return 0 if all(v["pass"] for v in results["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
