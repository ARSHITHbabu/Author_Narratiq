#!/usr/bin/env python3
"""
Deterministic E2E fixture manuscript + test user (Stage 6 task 6.2).

Gives 6.3 (checklist automation), 6.4 (Playwright E2E) and 6.5 (AI-quality
harness) a known, reproducible story instead of ad hoc manually-created data.
Cast (Devika, Mara, Sant, Vance) matches both docs/testing/author-feature-test-checklist.docx
and the character name already used across several existing backend tests
(test_search_module.py, test_story_bible_outcomes.py, test_story_bible_quality.py,
test_transform_preservation.py) — chosen for consistency, not invented fresh.

Safety (added 2026-09-22, after docs/incidents/2026-09-22-database-row-count-discrepancy.md):
  - Refuses to run against any database not on db_safety_guard.py's positive
    allow-list — the SAME guard the pytest suite itself uses, so there is one
    definition of "safe to run test tooling against", not two.
  - The fixture password is NEVER hardcoded in source. It must come from the
    FIXTURE_PASSWORD environment variable; generation aborts without it.
  - --reset deletes only a user matched by the EXACT fixture email (never a
    pattern, never "any user matching X"), and re-verifies the fetched row's
    own email attribute equals that exact string immediately before deleting
    it — a defence against a filter-construction bug, not just trusting the
    query. It never touches any other user's data.

Usage:
  FIXTURE_PASSWORD=...  python3 backend/scripts/seed_fixture.py --reset
  FIXTURE_PASSWORD=...  FIXTURE_EMAIL=other@narratiq.test python3 backend/scripts/seed_fixture.py --reset

DATABASE_URL must point at an allow-listed test database (see db_safety_guard.py);
this script never prints DATABASE_URL or any credential, only the bare database name.
"""
import argparse
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_BACKEND_DIR / "tests"))

from db_safety_guard import allowed_test_dbs, is_allowed_test_db_name, refusal_message  # noqa: E402

DEFAULT_FIXTURE_EMAIL = "e2e-fixture@narratiq.test"
DEFAULT_FIXTURE_USERNAME = "e2e_fixture"


def _require_allowlisted_database() -> None:
    from database import engine

    db_name = engine.url.database
    allowed = allowed_test_dbs()
    if not is_allowed_test_db_name(db_name, allowed):
        print(refusal_message(db_name, allowed), file=sys.stderr)
        sys.exit(1)
    print(f"[seed_fixture] target database confirmed on allow-list: {db_name!r}")


def _require_password() -> str:
    password = os.environ.get("FIXTURE_PASSWORD")
    if not password:
        print(
            "REFUSING TO RUN: FIXTURE_PASSWORD is not set.\n"
            "This script never hardcodes a fixture password — set it explicitly:\n"
            "  FIXTURE_PASSWORD='...' python3 backend/scripts/seed_fixture.py --reset\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return password


CHAPTERS = [
    {
        "number": 1,
        "title": "The Archive Debt",
        "content": (
            "<p>Devika Rao had promised the Bureau three years of her memory work, and the debt "
            "was almost paid. She met Mara Coste on the archive steps, the way she always did on "
            "settlement days, and Mara said the thing she always said: that Devika should stop "
            "counting and start living.</p>"
            "<p>\"Sant thinks the Bureau is stalling you on purpose,\" Mara said. \"He found a "
            "second contract under your name. You never signed a second contract.\"</p>"
            "<p>Devika had not signed a second contract. She was sure of that the way she was sure "
            "of very little else these days.</p>"
        ),
    },
    {
        "number": 2,
        "title": "Coopers Row",
        "content": (
            "<p>Teodor Vance kept his office on Coopers Row, three floors above the tea house where "
            "Devika used to meet her sister before the sister stopped answering letters. Vance had "
            "known Devika's family for longer than Devika had been alive, and he still called her "
            "\"Rao's girl\" when he forgot himself.</p>"
            "<p>\"The second contract is real,\" Vance told her. \"I witnessed it. You were in the "
            "room. You don't remember because the Bureau took that memory as partial payment, which "
            "is not supposed to be possible under a single contract.\"</p>"
            "<p>Mara went very still when Devika repeated this to her later. \"Then it's not one debt,\" "
            "Mara said. \"It's two, and you've only been paying off one of them.\"</p>"
        ),
    },
    {
        "number": 3,
        "title": "What Sant Found",
        "content": (
            "<p>Sant Okoro had spent eleven days in the Bureau's public ledger room, and he emerged "
            "with a name: the second contract had been co-signed by someone using Devika's late "
            "sister's registration number, two years after that number should have gone dormant.</p>"
            "<p>\"Someone used your sister's credentials to sign you into a debt you don't remember "
            "agreeing to,\" Sant said. \"Either your sister is not as gone as the Bureau told you, or "
            "someone at the Bureau is very good at forging dormant registrations.\"</p>"
            "<p>Devika thought of the letters that had stopped, and did not know which possibility "
            "frightened her more.</p>"
        ),
    },
]

CHARACTERS = [
    {"name": "Devika Rao", "role": "protagonist", "aliases": ["Devika", "Rao's girl"]},
    {"name": "Mara Coste", "role": "supporting", "aliases": ["Mara"]},
    {"name": "Sant Okoro", "role": "supporting", "aliases": ["Sant"]},
    {"name": "Teodor Vance", "role": "supporting", "aliases": ["Vance"]},
]

RELATIONSHIPS = [
    ("Devika Rao", "Mara Coste", "ally", "strong"),
    ("Devika Rao", "Sant Okoro", "ally", "moderate"),
    ("Devika Rao", "Teodor Vance", "family_friend", "moderate"),
]

GROUND_TRUTH_PATH = _BACKEND_DIR / "tests" / "fixtures" / "e2e_manuscript_ground_truth.md"


def _write_ground_truth() -> None:
    lines = [
        "# E2E fixture manuscript — ground truth",
        "",
        "Generated by `backend/scripts/seed_fixture.py`. Used by task 6.3's",
        "checklist automation to assert against known-correct answers instead",
        "of only checking HTTP 200.",
        "",
        "## Cast",
        "- **Devika Rao** — protagonist. Owes a memory-debt to \"the Bureau\".",
        "- **Mara Coste** — Devika's ally; skeptical of the Bureau from Ch1.",
        "- **Sant Okoro** — Devika's ally; researches the second contract in Ch3.",
        "- **Teodor Vance** — family friend; reveals the second contract in Ch2.",
        "",
        "## Mystery thread (should be detected as OPEN, not resolved, by a 3-chapter scan)",
        "A second, forged debt contract exists under Devika's name, apparently",
        "co-signed using her missing sister's dormant registration. Unresolved",
        "as of Chapter 3 — no chapter answers whether the sister is alive or",
        "whether the Bureau itself forged the signature.",
        "",
        "## Timeline",
        "1. Ch1 — Devika is close to paying off her (believed-single) debt; Mara",
        "   raises the existence of a second contract.",
        "2. Ch2 — Vance confirms the second contract is real and that a memory",
        "   was taken as partial payment for it without Devika's awareness.",
        "3. Ch3 — Sant finds the second contract was co-signed using Devika's",
        "   sister's registration number, two years after it should have gone",
        "   dormant.",
        "",
        "## Relationships established",
        "- Devika ↔ Mara: ally, strong",
        "- Devika ↔ Sant: ally, moderate",
        "- Devika ↔ Vance: family_friend, moderate",
        "",
        "## What a correct continuity/plot-hole scan should NOT flag",
        "The three chapters are internally consistent — no contradicted fact,",
        "no timeline reordering. A false positive here (that isn't a citation of",
        "the deliberately unresolved mystery thread above) indicates a real",
        "continuity-check defect, not a feature of this fixture.",
        "",
    ]
    GROUND_TRUTH_PATH.write_text("\n".join(lines))
    print(f"[seed_fixture] ground truth written: {GROUND_TRUTH_PATH.relative_to(_BACKEND_DIR.parent)}")


def _delete_existing_fixture(db, email: str) -> None:
    from models import User

    existing = db.query(User).filter(User.email == email).first()
    if existing is None:
        return
    # Defence in depth: re-verify the fetched row really is the fixture
    # account before deleting anything, rather than trusting the filter alone.
    if existing.email != email:
        raise RuntimeError(
            f"seed_fixture internal error: fetched user email {existing.email!r} "
            f"does not match the requested fixture email {email!r} — refusing to delete."
        )
    from models import Story

    for story in db.query(Story).filter(Story.user_id == existing.user_id).all():
        db.delete(story)  # cascades to chapters/characters/etc per models.py relationships
    db.delete(existing)
    db.commit()
    print(f"[seed_fixture] existing fixture account removed (matched by exact email)")


def build(reset: bool, email: str, username: str) -> dict:
    _require_allowlisted_database()
    password = _require_password()

    from database import SessionLocal
    from models import User, Story, Chapter, Character, CharacterRelationship
    import bcrypt

    db = SessionLocal()
    try:
        if reset:
            _delete_existing_fixture(db, email)
        else:
            if db.query(User).filter(User.email == email).first() is not None:
                print(
                    f"[seed_fixture] fixture account already exists ({email}) and --reset was not "
                    f"passed — nothing to do. Pass --reset to recreate it.",
                )
                return {}

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user = User(email=email, username=username, hashed_password=hashed)
        db.add(user)
        db.flush()

        story = Story(user_id=user.user_id, title="The Archive Debt (E2E fixture)")
        db.add(story)
        db.flush()

        chapter_ids: dict[int, str] = {}
        for ch_def in CHAPTERS:
            ch = Chapter(
                story_id=story.story_id,
                chapter_number=ch_def["number"],
                title=ch_def["title"],
                content=ch_def["content"],
                word_count=len(ch_def["content"].split()),
            )
            db.add(ch)
            db.flush()
            chapter_ids[ch_def["number"]] = ch.chapter_id

        char_ids: dict[str, str] = {}
        for c in CHARACTERS:
            char = Character(story_id=story.story_id, user_id=user.user_id,
                              name=c["name"], role=c["role"], aliases=c["aliases"])
            db.add(char)
            db.flush()
            char_ids[c["name"]] = char.character_id

        for from_name, to_name, rel_type, strength in RELATIONSHIPS:
            db.add(CharacterRelationship(
                story_id=story.story_id,
                from_character_id=char_ids[from_name],
                to_character_id=char_ids[to_name],
                relationship_type=rel_type,
                strength=strength,
            ))

        db.commit()
        _write_ground_truth()

        result = {
            "user_id": user.user_id,
            "story_id": story.story_id,
            "chapter_ids": chapter_ids,
            "character_ids": char_ids,
        }
        print(f"[seed_fixture] created: user_id={user.user_id} story_id={story.story_id} "
              f"chapters={len(chapter_ids)} characters={len(char_ids)}")
        print(f"[seed_fixture] E2E_EMAIL={email}  (E2E_PASSWORD is whatever FIXTURE_PASSWORD was set to)")
        print(f"[seed_fixture] E2E_STORY_ID={story.story_id}")
        return result
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true",
                         help="Delete any existing fixture account (matched by exact email) and recreate it.")
    parser.add_argument("--email", default=os.environ.get("FIXTURE_EMAIL", DEFAULT_FIXTURE_EMAIL))
    parser.add_argument("--username", default=DEFAULT_FIXTURE_USERNAME)
    args = parser.parse_args()

    build(reset=args.reset, email=args.email, username=args.username)


if __name__ == "__main__":
    main()
