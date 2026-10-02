#!/usr/bin/env python3
"""
Per-spec fixture stories for the live Playwright suite (Stage 9 task 9.1).

Several live specs need their OWN disposable story with specific text, and they
all read the same E2E_STORY_ID, so one shared story cannot satisfy them all:

  selection-toolbar         two chapters; chapter one begins "The lighthouse",
                            chapter two "A second chapter". Titles must NOT be
                            "Chapter N": the binder already prints that label, so
                            the spec's exact-text click would match twice
  lock-and-strength         chapter one is exactly the two "sensor" sentences
  sidecar-lock-and-strength a chapter titled "Fixture" with the same two sentences
  notes-reliability         a story note titled "Tide chart margins", plus an
                            empty story (E2E_EMPTY_STORY_ID)
  ocr-panel                 a story with no chapters (E2E_NO_CHAPTER_STORY_ID)
  character-hint-sync       two live, similar-but-distinct character hints. The
                            story must be INDEXED first (POST …/chapters/sync-summaries):
                            mention re-indexing is queued only for indexed chapters,
                            so the "still being indexed" banner never appears otherwise.
                            The spec registers E2E_HINT_NAME, so re-seed before each run.
  search-replace            one chapter with formatting inside names, nested marks,
                            an "&amp;" entity and a heading (Stage 12 A9). Re-seed
                            before each run: the spec replaces text
  manuscript-upload         a story with two chapters, so the import must number
                            the imported chapters 3, 4, … (Stage 12 A8)
  story-bible-generation    uses the seed_fixture.py story, which must also be
                            indexed first — generation answers 422 "No indexed
                            chapters found" on an unindexed story (correctly).

Until now these were created by hand for each verification run. This script
creates them in the seed_fixture.py account (run that first), on an
allow-listed test database only, and prints one env block per spec. Re-running
deletes only the stories this script created (exact title prefix, fixture
account only) and recreates them.

  DATABASE_URL=...narratiq_test python3 backend/scripts/seed_browser_fixtures.py
"""
import os
import re
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_BACKEND_DIR / "tests"))

from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name, refusal_message  # noqa: E402

PREFIX = "[e2e-browser] "
SENSOR = ("The sensor reported normal readings for the third day in a row. "
          "Priya logged the data and closed her laptop for the night.")


def main() -> None:
    from database import SessionLocal, engine
    from models import Chapter, CharacterHint, ManuscriptJob, Story, StoryNote, User

    if not is_allowed_test_db_name(engine.url.database, allowed_test_dbs()):
        print(refusal_message(engine.url.database, allowed_test_dbs()), file=sys.stderr)
        sys.exit(1)
    email = os.environ.get("FIXTURE_EMAIL", "e2e-fixture@narratiq-internal-test.com")
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.email != email:
        sys.exit(f"fixture account {email!r} not found — run scripts/seed_fixture.py first")

    # Remove this script's own earlier stories (exact prefix, this account only).
    for old in db.query(Story).filter(Story.user_id == user.user_id, Story.title.startswith(PREFIX)).all():
        db.query(CharacterHint).filter(CharacterHint.story_id == old.story_id).delete(synchronize_session=False)
        db.query(StoryNote).filter(StoryNote.story_id == old.story_id).delete(synchronize_session=False)
        db.query(ManuscriptJob).filter(ManuscriptJob.story_id == old.story_id).delete(synchronize_session=False)
        db.delete(old)
    db.commit()

    def story(title, chapters):
        s = Story(user_id=user.user_id, title=PREFIX + title)
        db.add(s); db.flush()
        chs = []
        for n, (ctitle, html) in enumerate(chapters, start=1):
            words = len(re.sub(r"<[^>]+>", " ", html).split())
            c = Chapter(story_id=s.story_id, title=ctitle, chapter_number=n, content=html, word_count=words)
            db.add(c); chs.append(c)
        db.flush()
        return s, chs

    toolbar, _ = story("Selection toolbar", [
        ("The Causeway", "<p>The lighthouse stood at the end of the causeway, its lamp dark for the first "
                      "time in forty years. Wren walked the last mile in the rain.</p>"
                      "<p>Inside, the keeper's log lay open at a page nobody had finished.</p>"),
        ("Low Tide", "<p>A second chapter began the next morning, when the tide went out and left the "
                      "causeway bare. Wren read the unfinished page again.</p>"),
    ])
    lock, _ = story("Lock and strength", [("Night Shift", f"<p>{SENSOR}</p>")])
    sidecar, _ = story("Sidecar lock and strength", [("Fixture", f"<p>{SENSOR}</p>")])
    notes, _ = story("Notes reliability", [("Harbour", "<p>The harbour master counted the boats.</p>")])
    db.add(StoryNote(story_id=notes.story_id, user_id=user.user_id, title="Tide chart margins",
                     content="Check the spring tides before the harbour scene."))
    empty, _ = story("Empty (no chapters, no notes)", [])
    hints, hchs = story("Character hint sync", [
        ("The Bureau", "<p>Oriel Thane waited at the Bureau door while Oriel Thayne argued with the clerk.</p>"),
    ])
    for name in ("Oriel Thane", "Oriel Thayne"):
        db.add(CharacterHint(story_id=hints.story_id, chapter_id=hchs[0].chapter_id, chapter_number=1,
                             suggested_name=name, context_snippet=f"{name} waited at the Bureau door."))
    search, _ = story("Search and replace", [
        ("Harbour Notes", "<h2>The Harbour</h2>"
                          "<p>Dev<strong>ika</strong> met Devika at the harbour.</p>"
                          "<p>Tom &amp; Jerry kept the ampersand sign.</p>"
                          "<p>the <strong>old <em>cas</em></strong>tle and the old castle</p>"),
    ])
    upload, _ = story("Manuscript import", [
        ("Before One", "<p>The first chapter the author wrote by hand.</p>"),
        ("Before Two", "<p>The second chapter the author wrote by hand.</p>"),
    ])
    db.commit()

    print(f"[seed_browser_fixtures] database: {engine.url.database!r}; account: {email}")
    blocks = {
        "selection-toolbar": {"E2E_STORY_ID": toolbar.story_id},
        "lock-and-strength": {"E2E_STORY_ID": lock.story_id},
        "sidecar-lock-and-strength": {"E2E_STORY_ID": sidecar.story_id},
        "notes-reliability": {"E2E_STORY_ID": notes.story_id, "E2E_EMPTY_STORY_ID": empty.story_id},
        "ocr-panel": {"E2E_STORY_ID": notes.story_id, "E2E_NO_CHAPTER_STORY_ID": empty.story_id},
        "character-hint-sync": {"E2E_STORY_ID": hints.story_id, "E2E_HINT_NAME": "Oriel Thane",
                                "E2E_HINT_KEEP": "Oriel Thayne"},
        "manuscript-upload": {"E2E_STORY_ID": upload.story_id},
        "search-replace": {"E2E_STORY_ID": search.story_id},
    }
    for spec, env in blocks.items():
        print(f"{spec}: " + " ".join(f"{k}={v!r}" for k, v in env.items()))
    db.close()


if __name__ == "__main__":
    main()
