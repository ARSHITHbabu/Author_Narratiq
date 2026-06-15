"""
End-to-end check for genre detection against the LIVE vLLM (not a unit test).

Exercises detect_genre() with diverse inputs to confirm the guided-JSON fix
parses reliably — including the comp-title malformation that previously failed.

Run (with the backend env loaded):  python3 tests/manual_genre_detection_check.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import detect_genre

CASES = [
    ("short", "A lonely lighthouse keeper befriends a talking seagull during a brutal winter storm."),
    ("long-scifi-amnesia",
     "Devika wakes in a sterile facility with no memory of who she is. As fragments return, she "
     "realizes the institution has been editing human memories for decades, and her own past holds "
     "the key to exposing them. She must decide whether the truth is worth the lives it will cost, "
     "while a quiet orderly who knows too much becomes her only ally in a place where trust is "
     "currency and every wall has ears. The deeper she digs, the more she questions whether the "
     "self she is fighting to recover ever truly existed."),
    ("romance",
     "Two rival wedding planners are forced to share a tiny seaside office for one chaotic summer, "
     "and their constant bickering slowly turns into something neither expected."),
    ("literary-sparse",
     "An old man tends his dead wife's garden every morning, refusing to let a single rose wilt, "
     "as the town around him quietly forgets she ever lived."),
    ("epic-fantasy",
     "When the last dragon egg hatches in a kingdom that outlawed magic, a stable boy must smuggle "
     "the creature across three warring provinces before the Inquisition turns it into a weapon."),
    ("edge-emoji-unicode",
     "🌊 A surfer named Iñaki chases a mythic wave called «La Viuda» across the Pacific — café "
     "stops, naïve dreams, and a résumé of near-drownings — to prove his late father wrong."),
]


async def main():
    passed = 0
    for name, desc in CASES:
        try:
            r = await detect_genre(desc)
            ok = isinstance(r, dict) and isinstance(r.get("genre"), str)
            comps = r.get("comparable_titles", [])
            comps_ok = isinstance(comps, list) and all(isinstance(c, str) for c in comps)
            status = "PASS" if (ok and comps_ok) else "FAIL"
            if status == "PASS":
                passed += 1
            print(f"[{status}] {name}: genre={r.get('genre')!r} sub={r.get('sub_genre')!r} "
                  f"tone={r.get('tone')} comps={comps}")
        except Exception as e:
            print(f"[ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(CASES)} cases produced valid, parseable profiles.")


if __name__ == "__main__":
    asyncio.run(main())
