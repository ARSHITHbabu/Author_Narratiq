"""
Stage 12 remediation A7 — CAST-C4 possible-duplicate detection.

Detect → suggest → the author confirms the merge. Nothing here may merge,
delete or modify a character; similarly named characters can be deliberately
different people.

Unit tests need nothing; the DB tests use stored vectors written directly (no
BGE-M3). The live calibration of PROFILE_SIMILARITY_THRESHOLD against real
BGE-M3 profiles is `test_profile_threshold_separates_distinct_characters_live`.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_character_duplicates.py -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from services.character_duplicates import (  # noqa: E402
    PROFILE_SIMILARITY_THRESHOLD, name_signals, possible_duplicate_for_name,
)


def kinds(a, b):
    return [k for k, _x, _y in name_signals(a, b)]


# ── Name signals (pure) ─────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b,expected", [
    (["Mara Halloran"], ["Captain Mara"], "name_part"),
    (["Mara"], ["Mara Halloran"], "name_part"),
    (["Dr. Ilse Varga"], ["Ilse"], "name_part"),
    (["Marek"], ["Marekk"], "similar_spelling"),
    (["Katherine"], ["Catherine"], "similar_spelling"),
    (["Mara Halloran"], ["Mara Halloran"], "same_name"),
    (["Vell", "the Magistrate"], ["The  Magistrate"], "same_name"),   # alias, whitespace/case
])
def test_flags_plausible_duplicates(a, b, expected):
    assert kinds(a, b)[0] == expected


@pytest.mark.parametrize("a,b", [
    (["John Smith"], ["John Doe"]),          # shared first name only
    (["Mara"], ["Kira"]),
    (["Father"], ["Mother"]),                # titles only -> no tokens
    (["Captain"], ["Captain Mara"]),         # a bare title is not a name
    (["Elara"], ["Eleanor"]),
    (["Ann"], ["Anna Karenina"]),            # not a subset; ratio too low
])
def test_does_not_flag_distinct_names(a, b):
    assert kinds(a, b) == []


def test_possible_duplicate_for_cast_suggestion():
    class C:
        def __init__(self, cid, name, aliases=()):
            self.character_id, self.name, self.aliases = cid, name, list(aliases)

    existing = [C("1", "Mara Halloran"), C("2", "Kira Voss")]
    assert possible_duplicate_for_name("Captain Mara", [], existing).character_id == "1"
    assert possible_duplicate_for_name("Tomas", ["Kira"], existing).character_id == "2"
    assert possible_duplicate_for_name("Tomas Reyne", [], existing) is None


# ── Database / endpoint ─────────────────────────────────────────────────────

DIM = 1024


def _vec(i: int, j: int | None = None, w: float = 0.0):
    v = [0.0] * DIM
    v[i] = 1.0
    if j is not None:
        v[j] = w
    return v


def _add(db, author, name, aliases=(), emb=None):
    from models import Character, CharacterProfile
    c = Character(story_id=author.sid, user_id=author.uid, name=name, aliases=list(aliases))
    db.add(c)
    db.flush()
    if emb is not None:
        db.add(CharacterProfile(character_id=c.character_id, story_id=author.sid, embedding=emb))
    db.commit()
    return c


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)


def _snapshot(db, sid):
    from models import Character
    db.expire_all()
    return sorted((c.character_id, c.name, tuple(c.aliases or [])) for c in
                  db.query(Character).filter(Character.story_id == sid).all())


def test_endpoint_lists_candidates_with_reasons_and_changes_nothing():
    from _phase3_helpers import two_authors
    with two_authors() as (db, a, _b, client):
        # two_authors already gives Elara, Kira, Marn — distinct.
        _add(db, a, "Elara Voss")                       # name_part with Elara
        _add(db, a, "Marnn")                            # similar spelling of Marn
        before = _snapshot(db, a.sid)
        r = client.get(f"/api/stories/{a.sid}/characters/duplicate-candidates", headers=a.headers)
        assert r.status_code == 200, r.text
        pairs = {frozenset((p["character_a"]["name"], p["character_b"]["name"])): p for p in r.json()}
        assert frozenset(("Elara", "Elara Voss")) in pairs
        assert frozenset(("Marn", "Marnn")) in pairs
        assert frozenset(("Elara", "Kira")) not in pairs
        p = pairs[frozenset(("Elara", "Elara Voss"))]
        assert p["reasons"][0]["kind"] == "name_part" and "Elara" in p["reasons"][0]["text"]
        # Read-only: no character was merged, renamed or deleted.
        assert _snapshot(db, a.sid) == before


def test_profile_similarity_signal_uses_stored_embeddings():
    from _phase3_helpers import two_authors
    with two_authors() as (db, a, _b, client):
        _add(db, a, "Vell", emb=_vec(5, 6, 0.1))
        _add(db, a, "the Magistrate", emb=_vec(5, 6, 0.12))   # cosine ~0.9998
        _add(db, a, "Tomas", emb=_vec(9))                      # orthogonal
        r = client.get(f"/api/stories/{a.sid}/characters/duplicate-candidates", headers=a.headers)
        names = [frozenset((p["character_a"]["name"], p["character_b"]["name"])) for p in r.json()]
        assert frozenset(("Vell", "the Magistrate")) in names
        assert not any("Tomas" in n for n in names)
        hit = next(p for p in r.json() if {p["character_a"]["name"], p["character_b"]["name"]}
                   == {"Vell", "the Magistrate"})
        assert hit["reasons"][-1]["kind"] == "similar_profile"
        assert hit["profile_similarity"] >= PROFILE_SIMILARITY_THRESHOLD


def test_other_authors_story_is_404_and_never_mixed():
    from _phase3_helpers import two_authors
    with two_authors() as (db, a, b, client):
        _add(db, b, "Elara")       # same name as A's Elara, but in B's story
        r = client.get(f"/api/stories/{b.sid}/characters/duplicate-candidates", headers=a.headers)
        assert r.status_code == 404
        r = client.get(f"/api/stories/{a.sid}/characters/duplicate-candidates", headers=a.headers)
        from models import Character
        ids_a = {c.character_id for c in db.query(Character).filter(Character.story_id == a.sid)}
        for p in r.json():
            for side in ("character_a", "character_b"):
                assert p[side]["character_id"] in ids_a


def test_merge_still_requires_the_author_and_works_on_a_candidate():
    """The candidate list feeds the existing, author-invoked merge endpoint."""
    from _phase3_helpers import two_authors
    from models import Character
    with two_authors() as (db, a, b, client):
        dup = _add(db, a, "Elara Voss")
        elara = db.query(Character).filter(Character.story_id == a.sid, Character.name == "Elara").one()
        # B cannot merge A's characters.
        r = client.post(f"/api/stories/{a.sid}/characters/{elara.character_id}/merge",
                        headers=b.headers, json={"duplicate_id": dup.character_id})
        assert r.status_code == 404
        r = client.post(f"/api/stories/{a.sid}/characters/{elara.character_id}/merge",
                        headers=a.headers, json={"duplicate_id": dup.character_id})
        assert r.status_code == 200, r.text
        assert "Elara Voss" in r.json()["survivor"]["aliases"]
        r = client.get(f"/api/stories/{a.sid}/characters/duplicate-candidates", headers=a.headers)
        assert not any("Elara Voss" in (p["character_a"]["name"], p["character_b"]["name"]) for p in r.json())


def test_cast_generation_flags_possible_duplicate(monkeypatch):
    from _phase3_helpers import two_authors
    from services import ai_service

    async def fake_extract(_chapters):
        return [
            {"name": "Elara Voss", "role": "protagonist"},   # possible duplicate of Elara
            {"name": "Kira", "role": "supporting"},          # exact -> already_exists
            {"name": "Tomas Reyne", "role": "minor"},        # new
        ]

    monkeypatch.setattr(ai_service, "extract_cast", fake_extract)
    with two_authors() as (db, a, _b, client):
        r = client.post(f"/api/stories/{a.sid}/characters/generate-cast", headers=a.headers, json={})
        assert r.status_code == 200, r.text
        by = {s["name"]: s for s in r.json()["suggestions"]}
        assert by["Elara Voss"]["already_exists"] is False
        assert by["Elara Voss"]["possible_duplicate_name"] == "Elara"
        assert by["Kira"]["already_exists"] is True and by["Kira"]["possible_duplicate_of"] is None
        assert by["Tomas Reyne"]["possible_duplicate_of"] is None


# ── Live calibration (real BGE-M3) ──────────────────────────────────────────

DISTINCT_PROFILES = {
    "Mara Halloran": "harbour pilot, stubborn, grew up on the docks, wants to buy her own boat",
    "Kira Voss": "lighthouse keeper's daughter, quiet, keeps the brass key, distrusts the council",
    "Magistrate Vell": "presumed drowned eleven years ago, faked his death, wants the harbour back",
    "Tomas Reyne": "young customs clerk, ambitious, forges records for the smugglers",
    "Ilse Varga": "physician, widowed, tends the sick in the lower town, sharp-tongued",
    "Old Brannock": "retired sailor who drinks at the Anchor and tells stories nobody believes",
}


@pytest.mark.skipif(os.environ.get("SKIP_LLM_TESTS") == "1", reason="needs BGE-M3")
def test_profile_threshold_separates_distinct_characters_live():
    """Real BGE-M3 embeddings of six distinct characters from one story, built
    the way _embed_profile builds them. Every distinct pair must sit below the
    threshold; a restated profile of the same character must sit above it."""
    import asyncio
    from itertools import combinations
    from services.ai_service import embed_text
    from database import SessionLocal
    from services.vector_math import cosine

    async def emb(text):
        return await embed_text(text)

    db = SessionLocal()
    vecs = {n: asyncio.run(emb(f"{n} supporting {d}")) for n, d in DISTINCT_PROFILES.items()}
    sims = {(x, y): cosine(db, vecs[x], vecs[y]) for x, y in combinations(vecs, 2)}
    worst = max(sims.values())
    print(f"\n[A7 calibration] max distinct-pair cosine = {worst:.3f}; threshold = {PROFILE_SIMILARITY_THRESHOLD}")
    assert worst < PROFILE_SIMILARITY_THRESHOLD, sims

    same = asyncio.run(emb("the Magistrate supporting presumed drowned eleven years ago, faked his "
                           "death, wants to take back the harbour"))
    s = cosine(db, same, vecs["Magistrate Vell"])
    db.close()
    print(f"[A7 calibration] same-character restated cosine = {s:.3f}")
    assert s >= PROFILE_SIMILARITY_THRESHOLD, "a restated profile of the same character is missed"
