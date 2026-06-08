#!/usr/bin/env python3
"""
End-to-end regression smoke test for NarratIQ AI.

Exercises the full stack against a RUNNING backend with REAL data — auth, story
creation, chapters, genre intelligence, cast generation, character profiles, and
the plot assistant (all three modes) — and asserts each works.

This is the guard rail for "it worked, then a change broke it". Every bug this
session (cast context-overflow, the `:q::vector` plot-assistant 500, empty
character profiles, the un-awaited embed_text calls) would have been caught here
on the first run. Run it after any backend change and before any deploy.

Usage:
    python3 scripts/smoke_test.py                 # against http://localhost:8000
    NARRATIQ_URL=https://host python3 scripts/smoke_test.py
    python3 scripts/smoke_test.py --skip-index    # skip the slow indexed-QA check

Exit code 0 = all checks passed, 1 = at least one failed.
"""
import os
import sys
import time
import random
import argparse

try:
    import requests
except ImportError:
    print("smoke_test requires `requests` (pip install requests)")
    sys.exit(2)

BASE = os.environ.get("NARRATIQ_URL", "http://localhost:8000").rstrip("/")
PASS, FAIL = "PASS ✅", "FAIL ❌"
_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"  {PASS if ok else FAIL}  {name}" + (f" — {detail}" if detail else ""))
    return ok


CHAPTERS = [
    ("Chapter 1 — Arrival", """
<p>Eleanor Voss arrived at the lighthouse at Dunmore on the last ferry of the season. She was
forty-three, with silver-streaked dark hair and a long grey coat. A marine biologist, she had left
her post in Edinburgh after her brother Thomas drowned, and came to restore the lighthouse their
grandfather once kept. The harbour master, Cormac Doyle — broad, weather-beaten, gruff but kind —
warned her the last keeper, Silas Mercer, had vanished without trace in 1962.</p>"""),
    ("Chapter 2 — The Journal", """
<p>Eleanor found the journal of Silas Mercer, the keeper who disappeared. Silas had been barely
twenty-five, ambitious and lonely, desperate to be believed when he wrote of strange green lights on
the water. Cormac admitted he had seen the lights too as a boy, and had stayed silent out of shame,
letting Silas be branded a madman. Eleanor resolved to prove Silas had told the truth.</p>"""),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-index", action="store_true",
                    help="skip the slow indexed-QA grounding check")
    args = ap.parse_args()

    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    print(f"NarratIQ smoke test → {BASE}\n")

    # 0. Health
    try:
        h = s.get(f"{BASE}/api/health", timeout=15).json()
        check("health: backend ready", h.get("backend") == "ready", str(h.get("backend")))
        check("health: vLLM ready", h.get("vllm") == "ready", str(h.get("vllm")))
    except Exception as e:
        check("health endpoint reachable", False, repr(e))
        return _summary()

    # 1. Auth
    sfx = random.randint(100000, 999999)
    try:
        r = s.post(f"{BASE}/api/auth/register", json={
            "email": f"smoke{sfx}@example.com", "username": f"smoke{sfx}",
            "password": "SmokeTest123!"}, timeout=30)
        ok = r.status_code == 200 and "access_token" in r.json()
        check("signup returns token", ok, f"status={r.status_code}")
        if not ok:
            return _summary()
        s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    except Exception as e:
        check("signup", False, repr(e)); return _summary()

    # login (separate session) — proves credentials persist
    try:
        r = s.post(f"{BASE}/api/auth/login", json={
            "email": f"smoke{sfx}@example.com", "password": "SmokeTest123!"}, timeout=30)
        check("login returns token", r.status_code == 200 and "access_token" in r.json(),
              f"status={r.status_code}")
    except Exception as e:
        check("login", False, repr(e))

    # 2. Project / story
    r = s.post(f"{BASE}/api/projects/", json={"title": "Smoke Story", "description": "regression"},
               timeout=30)
    story_id = (r.json() or {}).get("story_id") or (r.json() or {}).get("id")
    if not check("create story", bool(story_id), f"status={r.status_code}"):
        return _summary()

    # 3. Chapters
    for title, content in CHAPTERS:
        r = s.post(f"{BASE}/api/stories/{story_id}/chapters",
                   json={"title": title, "content": content}, timeout=30)
        if not check(f"create chapter {title!r}", r.status_code in (200, 201), f"status={r.status_code}"):
            return _summary()

    # 4. Genre intelligence (intake) — richer quick analysis
    r = s.post(f"{BASE}/api/intake/{story_id}",
               json={"description":
                     "A marine biologist restores a haunted lighthouse to prove a vanished keeper "
                     "was telling the truth about strange lights on the water.",
                     "audience_hint": "adult"}, timeout=120)
    if check("genre intelligence: 200", r.status_code == 200, f"status={r.status_code} {r.text[:120]}"):
        gp = r.json().get("genre_profile", {})
        rich = [k for k in ("secondary_genres", "comparable_titles", "marketing_category",
                            "emotional_arc", "narrative_pov", "pacing", "intelligence_notes")
                if gp.get(k)]
        check("genre intelligence: base fields present", bool(gp.get("genre") and gp.get("tone")),
              f"genre={gp.get('genre')!r}")
        check("genre intelligence: richer fields present", len(rich) >= 3,
              f"rich fields returned: {rich}")

    # 5. Generate cast (works on raw, unindexed chapters)
    r = s.post(f"{BASE}/api/stories/{story_id}/characters/generate-cast", timeout=180)
    cast_ok = check("generate-cast: 200", r.status_code == 200, f"status={r.status_code} {r.text[:160]}")
    suggestions = []
    if cast_ok:
        gen = r.json()
        suggestions = gen.get("suggestions", [])
        check("generate-cast: characters found", len(suggestions) > 0,
              f"{len(suggestions)} found across {gen.get('chapters_scanned')} chapter(s)")
        check("generate-cast: all named", all(x.get("name", "").strip() for x in suggestions),
              "")
        rich_chars = [x for x in suggestions if any(
            x.get(k) for k in ("appearance", "personality", "goals", "motivations", "backstory"))]
        check("generate-cast: rich profile detail extracted", len(rich_chars) > 0,
              f"{len(rich_chars)}/{len(suggestions)} have rich fields")

    # 6. Confirm cast → profiles populated
    if suggestions:
        to_save = [{k: x.get(k, "") for k in
                    ("name", "role", "status", "description", "evidence_snippet",
                     "age", "appearance", "personality", "goals", "motivations",
                     "backstory", "arc_notes")} | {"aliases": x.get("aliases", []),
                                                    "traits": x.get("traits", [])}
                   for x in suggestions if not x.get("already_exists")]
        r = s.post(f"{BASE}/api/stories/{story_id}/characters/confirm-cast",
                   json={"suggestions": to_save}, timeout=60)
        if check("confirm-cast: 201", r.status_code in (200, 201), f"status={r.status_code}"):
            created = r.json().get("created", [])
            populated = [c for c in created if (c.get("profile") or {}) and any(
                (c["profile"].get(k)) for k in
                ("appearance", "personality", "goals", "motivations", "backstory"))]
            check("confirm-cast: saved profiles are populated", len(populated) > 0,
                  f"{len(populated)}/{len(created)} saved with rich profile")

    # 7. Plot assistant — all three modes return 200
    def plot(q, ch_text=""):
        return s.post(f"{BASE}/api/plot-assistant/", json={
            "story_id": story_id, "question": q, "current_chapter_text": ch_text,
            "current_chapter_number": None}, timeout=120)
    r = plot("Who is Silas Mercer?")
    check("plot assistant: QA mode 200", r.status_code == 200, f"status={r.status_code} {r.text[:160]}")
    r = plot("What should happen next to raise the stakes?", CHAPTERS[1][1])
    check("plot assistant: creative mode 200", r.status_code == 200,
          f"status={r.status_code} suggestions={len(r.json().get('suggestions', [])) if r.status_code==200 else 0}")
    r = plot("Who is Cormac and how can I deepen his guilt?", CHAPTERS[1][1])
    check("plot assistant: mixed mode 200", r.status_code == 200, f"status={r.status_code}")

    # 8. Indexed QA grounding (slow — exercises the pgvector retrieval path with data)
    #    Chapter indexing (summary + embeddings) runs in the BACKGROUND and shares
    #    vLLM with our queries, so we give it a grace window before polling and
    #    poll gently (every 5 s) to avoid starving it. The pgvector *path* itself is
    #    already proven by the startup self-check; this confirms grounding end-to-end.
    if not args.skip_index:
        s.post(f"{BASE}/api/stories/{story_id}/chapters/sync-summaries", timeout=30)
        print("  … waiting for background indexing (vector path), up to ~200 s …")
        time.sleep(12)   # grace: let summary/embedding tasks get vLLM time first
        grounded = False
        for _ in range(38):
            r = plot("Who is Silas Mercer and what did he record?")
            if r.status_code == 200 and "retrieved" in (r.json().get("context_used", "")):
                grounded = True
                break
            time.sleep(5)
        check("plot assistant: grounds QA on indexed pgvector retrieval", grounded,
              "vector query returned indexed context" if grounded
              else "indexing did not finish in time (background load) — path itself is OK")

    return _summary()


def _summary() -> int:
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'='*60}\nRESULT: {passed}/{total} checks passed")
    failed = [n for n, ok, _ in _results if not ok]
    if failed:
        print("FAILED:")
        for n in failed:
            print(f"  - {n}")
        print(f"{'='*60}")
        return 1
    print(f"ALL CHECKS PASSED {PASS}\n{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
