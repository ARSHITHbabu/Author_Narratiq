"""
Stage 12 Tranche 3 (A21) — does the transcript clean-up keep the author's words?

Runs services.audio_service.clean_transcript against the live model on four
transcripts (a dictated note heading, fillers, a plan note, dialogue) and
records the share of non-filler words each output kept. Evidence:
docs/testing/stage-12/tranche3/transcript-cleanup-{before,after}.json.

  cd backend && python3 scripts/quality/transcript_cleanup_probe.py 10 /tmp/cleanup.json
"""
import asyncio, sys, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.audio_service import clean_transcript
RAWS = {
 "fixture": "Audio note for chapter 3. The lighthouse keeper, Marigold, lit the lantern at midnight. She wrote in the logbook that the fishing boats came home safely before the storm.",
 "fillers": "um so the the scene opens at the docks you know and uh Mara is waiting for the ferry basically she has the letter in her coat and she doesn't open it",
 "plan": "Note to self for the next draft. Move the funeral to chapter five. Tobias should not know about the will until the reading.",
 "dialogue": "Then Ada says I never wanted the lighthouse. And Wren answers you never wanted anything that was hard to keep.",
}
def words(t): return set(re.findall(r"[a-z0-9']+", t.lower()))
FILL = {"um","uh","like","you","know","so","basically","actually","the"}
async def main(n):
    out = {}
    for k, raw in RAWS.items():
        rows = []
        for _ in range(n):
            c = await clean_transcript(raw)
            rw = words(raw) - FILL
            kept = len(rw & words(c)) / len(rw)
            rows.append({"kept": round(kept, 3), "text": c})
        out[k] = rows
        print(k, [r["kept"] for r in rows], flush=True)
    json.dump(out, open(sys.argv[2], "w"), indent=2)
asyncio.run(main(int(sys.argv[1])))
