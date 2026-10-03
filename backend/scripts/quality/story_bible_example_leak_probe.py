#!/usr/bin/env python3
"""
Stage 12.1 — does a Story Bible prompt example leak into generated output?

Live model, the seeded fixture story "The Archive Debt (E2E fixture)" on the
allow-listed test database, context built by the router's own
`_build_full_context`. Read-only (nothing is saved to the story).

  before   the World Rules section with the pre-12.1 prompt (its realistic
           example restored for the measurement) — how often the example leaks
  after    all five sections with the current prompts + post-processing

Each output line is checked for: any prompt example (old or current), any
placeholder text ("<…>"), and — for World Rules — whether its lines cite a chapter.

  DATABASE_URL=...narratiq_test python3 scripts/quality/story_bible_example_leak_probe.py 10 out.json
"""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from database import SessionLocal  # noqa: E402
from models import Story  # noqa: E402
from routers.story_bible import _build_full_context  # noqa: E402
from services import ai_service as ai  # noqa: E402

OLD_EXAMPLES = ["lattice sessions require an induction collar", "the archive burns", "she burns the archive"]
SECTIONS = ["characters", "locations", "timeline", "world_rules", "themes"]


def check(text: str) -> dict:
    norm = ai._norm(text)
    lines = [ln for ln in text.splitlines() if ln.strip().startswith(("-", "*", "•"))]
    return {
        "example_leaks": [ex for ex in OLD_EXAMPLES + list(ai._BIBLE_PROMPT_EXAMPLES) if f" {ex} " in norm],
        "placeholder_leaks": re.findall(r"<[^>\n]{3,60}>|\[Ch N\]", text),
        "bullets": len(lines),
        "cited_bullets": sum(1 for ln in lines if re.search(r"\[Ch\s*\d", ln)),
    }


def _retrieval_fixture_context() -> str:
    """A second story whose text clearly shows rules of its world (flood gates,
    the Cistern, the harbour magistrate): the 6-chapter retrieval fixture, as
    chapter-tagged text, so the rules-producing path is exercised too."""
    from routers.search import _html_to_plain
    from tests.fixtures.retrieval_fixture import CHAPTERS
    return "\n".join(f"[Ch {i}] {_html_to_plain(c['content'])}" for i, c in enumerate(CHAPTERS, start=1))


async def main(n: int, out: str):
    db = SessionLocal()
    story = db.query(Story).filter(Story.title == "The Archive Debt (E2E fixture)").first()
    context = _build_full_context(story.story_id, db)
    db.close()
    if len(sys.argv) > 3 and sys.argv[3] == "--retrieval-fixture":
        context = _retrieval_fixture_context()
    real = ai._complete_ex
    results = {"story": story.title if len(sys.argv) <= 3 else "retrieval fixture (6 chapters, tagged text)", "runs": n, "before_world_rules": [], "after": []}

    async def old_prompt(system, user, **kw):        # restore the pre-12.1 World Rules example
        user = user.replace("EVERY bullet MUST end with the chapter tag that demonstrates it. Shape (a placeholder, "
                            "not content to copy):\n  - <a rule this story's world follows, as the text shows it> [Ch N]\n",
                            "EVERY bullet MUST end with the chapter tag that demonstrates it, e.g.\n"
                            "  - Lattice sessions require an induction collar [Ch 1]\n")
        assert "Lattice sessions" in user
        return await real(system, user, **kw)

    captured = {}

    async def capture(system, user, **kw):              # the exact prompts the current code sends
        captured["s"], captured["u"] = system, user
        return "", "stop"
    ai._complete_ex = capture
    await ai.generate_story_bible_section(section="world_rules", context=context)
    ai._complete_ex = real
    for i in range(n):
        raw, _ = await old_prompt(captured["s"], captured["u"], temperature=0.2, max_tokens=1500)
        results["before_world_rules"].append({"run": i, "text": raw, **check(raw)})
        print("before", i, check(raw)["example_leaks"], flush=True)
    for i in range(n):
        bible = {}
        for sec in SECTIONS:
            text, _ = await ai.generate_story_bible_section(section=sec, context=context)
            bible[sec] = {"text": text, **check(text)}
        results["after"].append({"run": i, "sections": bible})
        print("after", i, {s: (v["example_leaks"], len(v["placeholder_leaks"]), v["cited_bullets"]) for s, v in bible.items()},
              flush=True)
    Path(out).write_text(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), sys.argv[2]))
