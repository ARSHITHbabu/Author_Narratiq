#!/usr/bin/env python3
"""
Stage 12.1 — objective evidence for PA-H10, PA-H11 and PA-C9 on the indexed long
manuscript (run measure_long_manuscript_ranking.py with --keep first).

  PA-H10  major revelations in stored chapter summaries: for each planted
          revelation chapter, does the production summary name the decisive
          fact (who / what)? Checked with the revelation's own key terms.
  PA-H11  later-chapter representation: for broad whole-story questions through
          the production Q&A retrieval (top_k 10, chapter quota), the share of
          delivered passages from chapters 21–40, and the distinct chapters.
  PA-C9   story-wide character memory: for questions naming a character, how
          many of the chapters that character appears in (by the fixture text)
          are covered by the delivered passages (top_k 6 + the character
          context the router adds).

  DATABASE_URL=...narratiq_test python3 tests/measure_long_manuscript_coverage.py out.json
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

REVELATIONS = [   # chapter, fact, terms that must all appear in the summary (case-insensitive)
    (31, "Liesel Marr poisoned Edric Thorne", ["marr", "thorne"], ["poison", "foxglove", "vial"]),
    (38, "Abel Ferris is Wren's father", ["ferris"], ["father"]),
    (22, "the lighthouse oil line was cut on Marr's orders", ["marr"], ["oil", "light", "lamp"]),
    (34, "Crane's clerk Jory Wake betrayed the smugglers", ["jory", "wake"], ["sold", "betray", "dates", "customs"]),
    (39, "Liesel Marr set the rope-works fire", ["marr"], ["fire"]),
    (9, "the second ledger is sewn into the altar cloth", ["ledger"], ["altar"]),
    (27, "a brass token with the Ferris crest in the boot", ["token"], ["ferris"]),
]
BROAD = ["What happens in this story?", "Summarize the main events of the story.",
         "What are the most important turning points in the plot?", "How does the story end?"]
CHARACTER_QS = [("Tobin Gale", "What do we learn about Tobin Gale?"),
                ("Silas Crane", "What role does Silas Crane play in the story?"),
                ("Abel Ferris", "Who is Abel Ferris and what does he do?")]


async def main(out):
    from database import SessionLocal
    from models import Chapter, ChapterSummary, Story, User
    from services.ai_service import retrieve_character_context, retrieve_chunks_from_store
    db = SessionLocal()
    story = (db.query(Story).join(User, User.user_id == Story.user_id)
             .filter(User.email.like("long-ms-%"), Story.title == "The Saltmarsh Ledger")
             .order_by(Story.created_at.desc()).first())
    sid = story.story_id
    report = {"story_id": sid, "PA-H10": [], "PA-H11": [], "PA-C9": []}
    summaries = {s.chapter_number: s for s in db.query(ChapterSummary).filter(ChapterSummary.story_id == sid)}
    for ch, fact, who_terms, what_terms in REVELATIONS:
        s = summaries.get(ch)
        blob = json.dumps({"summary": s.raw_summary, "key_events": s.key_events} if s else {}, ensure_ascii=False).lower()
        ok = all(t in blob for t in who_terms) and any(t in blob for t in what_terms)
        report["PA-H10"].append({"chapter": ch, "fact": fact, "in_summary": ok,
                                 "summary": (s.raw_summary if s else None), "key_events": (s.key_events if s else None)})
        print("PA-H10", ch, fact, ok, flush=True)
    for q in BROAD:
        got = await retrieve_chunks_from_store(q, sid, db, top_k=10, max_chapter_number=None, diversify_chapters=True)
        chs = [g["chapter"] for g in got]
        late = sum(1 for c in chs if c > 20)
        report["PA-H11"].append({"query": q, "delivered_chapters": chs, "late_share": round(late / len(chs), 2) if chs else None,
                                 "distinct_chapters": len(set(chs))})
        print("PA-H11", q, chs, flush=True)
    texts = {c.chapter_number: c.content for c in db.query(Chapter).filter(Chapter.story_id == sid)}
    for name, q in CHARACTER_QS:
        surname = name.split()[-1]
        appears = sorted(n for n, t in texts.items() if surname in t)
        got = await retrieve_chunks_from_store(q, sid, db, top_k=6, max_chapter_number=None, diversify_chapters=True)
        ctx = await retrieve_character_context(sid, q, db, top_k=3, token_budget=600)
        ctx_text = json.dumps(ctx, ensure_ascii=False, default=str) if ctx else ""
        covered = sorted({g["chapter"] for g in got})
        report["PA-C9"].append({"character": name, "query": q, "appears_in_chapters": appears,
                                "passage_chapters": covered,
                                "coverage": round(len(set(covered) & set(appears)) / len(appears), 2) if appears else None,
                                "character_context_chars": len(ctx_text)})
        print("PA-C9", name, "appears", appears, "covered", covered, flush=True)
    Path(out).write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    db.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
