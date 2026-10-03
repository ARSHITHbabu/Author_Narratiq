#!/usr/bin/env python3
"""
Build tests/fixtures/long_manuscript_pa.json from long_manuscript_spec.py.

The scene prose of each chapter is written by the model (vLLM, temperature 0.7)
from that chapter's beat; the spec's planted paragraphs are then inserted
verbatim at fixed positions. Run ONCE; the JSON is committed so every
measurement uses identical text. Re-running produces a different manuscript.

  cd backend && python3 tests/fixtures/build_long_manuscript.py
"""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from long_manuscript_spec import BEATS, CHARACTERS, GENRE, SCENARIOS, TITLE  # noqa: E402

OUT = Path(__file__).parent / "long_manuscript_pa.json"
SYSTEM = (
    f"You are a novelist writing chapters of a {GENRE} called \"{TITLE}\", set in the salt-marsh harbour "
    "town of Greymouth. Write in past tense, third person, close on Wren Halloway. Write only the chapter's "
    "prose: no title, no headings, no notes. Use 7 to 9 paragraphs, about 900 words. Do not resolve any "
    "mystery or reveal who is responsible for anything; stay inside the beat you are given."
)


def planted_by_chapter() -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for sc in SCENARIOS:
        for p in [sc["critical"], *sc["decoys"]]:
            if "text" in p:
                out.setdefault(p["chapter"], [])
                if p["text"] not in out[p["chapter"]]:
                    out[p["chapter"]].append(p["text"])
    return out


async def write_chapter(client, model, n: int, beat: str, sem) -> str:
    async with sem:
        r = await client.chat.completions.create(
            model=model, temperature=0.7, max_tokens=1600,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": f"Chapter {n} of 40. Beat: {beat}"}])
        return r.choices[0].message.content.strip()


async def main():
    from config import settings
    from services.ai_service import get_vllm_client
    client, sem = get_vllm_client(), asyncio.Semaphore(8)
    prose = await asyncio.gather(*[write_chapter(client, settings.vllm_model_name, i + 1, b, sem)
                                   for i, b in enumerate(BEATS)])
    planted = planted_by_chapter()
    chapters = []
    for i, text in enumerate(prose, start=1):
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for j, extra in enumerate(planted.get(i, [])):
            pos = min(len(paras), 2 + 3 * j)        # spread plantings through the chapter
            paras.insert(pos, extra)
        chapters.append({"number": i, "title": f"Chapter {i}", "paragraphs": paras})
    words = sum(len(p.split()) for c in chapters for p in c["paragraphs"])
    OUT.write_text(json.dumps({"title": TITLE, "genre": GENRE, "characters": CHARACTERS,
                               "words": words, "chapters": chapters}, indent=1, ensure_ascii=False))
    print(f"wrote {OUT.name}: {len(chapters)} chapters, {words} words")


if __name__ == "__main__":
    asyncio.run(main())
