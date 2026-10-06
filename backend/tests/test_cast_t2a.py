"""
Stage 12 Tranche 2a — cast presence (A10), consistency (A11), importance (A12).

Deterministic: _merge_cast and the router are exercised with stubbed model
output; no vLLM. The live measurement is tests/measure_cast_consistency.py.

  A11  two people who share a first name are never merged by a name subset;
       alias evidence still merges; description/evidence come from the earliest
       grounded window; kinship claims must be grounded near the character;
       cut-off model JSON keeps every complete character.
  A10  presence is merged (on_page wins), validated, persisted on confirm and
       editable; referenced/historical figures are never dropped.
  A12  suggestion order is deterministic (presence, role, mentions, first
       appearance, name); saved characters stay alphabetical unless asked.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_cast_t2a.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from services.ai_service import _merge_cast, _salvage_json_objects  # noqa: E402

W1 = "=== Chapter 1 ===\nMira Okoye walked the salt road. An old woman called Hessa Lin traded maps."
W2 = ("=== Chapter 2 ===\n'Why are you helping me?' Mira finally asked. Hessa set down her pen. "
      "'Because the Cartographer was my sister,' she said.")


def by_name(cast):
    return {c["name"]: c for c in cast}


# ── A11: matching ────────────────────────────────────────────────────────────

def test_shared_first_name_is_never_merged_by_subset():
    cast = _merge_cast([[{"name": "Tomas Reyne", "description": "A customs clerk."}],
                        [{"name": "Tomas", "description": "The keeper's son."}],
                        [{"name": "Tomas Hale", "description": "The keeper's son, nine."}]])
    names = sorted(c["name"] for c in cast)
    assert names == ["Tomas", "Tomas Hale", "Tomas Reyne"]
    b = by_name(cast)
    assert "clerk" in b["Tomas Reyne"]["description"] and "keeper" not in b["Tomas Reyne"]["description"]
    # the ambiguous short name is flagged, not merged
    assert b["Tomas"]["_possible_duplicate_in_batch"] in ("Tomas Reyne", "Tomas Hale")


def test_a_shared_alias_alone_never_merges_two_people():
    cast = _merge_cast([[{"name": "Tomas Reyne", "aliases": ["Tomas"], "description": "A customs clerk."},
                         {"name": "Tomas Hale", "aliases": ["Tomas"], "description": "The keeper's son."}]])
    assert sorted(c["name"] for c in cast) == ["Tomas Hale", "Tomas Reyne"]


def test_a_record_carrying_another_full_name_is_flagged_not_split():
    cast = _merge_cast([[{"name": "Tomas Reyne", "aliases": ["Tomas Hale"], "description": "Clerk."}]])
    assert cast[0]["_possible_combined_with"] == "Tomas Hale"
    ok = _merge_cast([[{"name": "Mara Halloran", "aliases": ["Mara", "Captain Mara Halloran"]}]])
    assert "_possible_combined_with" not in ok[0]


def test_alias_evidence_and_titles_still_merge():
    cast = _merge_cast([[{"name": "Mara Halloran", "aliases": ["Mara"], "description": "A pilot."}],
                        [{"name": "Mara", "description": "Captain of the ferry."}],
                        [{"name": "Captain Mara Halloran", "description": "x"}]])
    assert [c["name"] for c in cast] == ["Mara Halloran"]           # one character
    assert {"Mara", "Captain Mara Halloran"} <= set(cast[0]["aliases"])


def test_description_and_evidence_come_from_the_earliest_window():
    cast = _merge_cast([[{"name": "Hessa Lin", "description": "An old map seller.",
                          "evidence_snippet": "an old woman called Hessa Lin"}],
                        [{"name": "Hessa Lin", "description": "A much longer later description of Hessa Lin.",
                          "evidence_snippet": "Hessa set down her pen"}]], [W1, W2])
    h = cast[0]
    assert h["description"] == "An old map seller."
    assert h["evidence_snippet"] == "an old woman called Hessa Lin"


def test_union_fields_combine_windows_without_repeating():
    cast = _merge_cast([[{"name": "Corvin Ashe", "backstory": "He guards the gate."}],
                        [{"name": "Corvin Ashe", "backstory": "He guards the gate. He hid the key."}]])
    assert cast[0]["backstory"] == "He guards the gate. He hid the key."


# ── A11 / CAST-H8: kinship grounding ─────────────────────────────────────────

def test_misattributed_kinship_is_dropped_and_grounded_kinship_kept():
    cast = _merge_cast(
        [[{"name": "Mira Okoye", "description": "A traveller.", "aliases": ["Mira"]},
          {"name": "Hessa Lin", "description": "A map seller."}],
         [{"name": "Mira Okoye", "description": "Seeks the truth behind her sister's drowning.",
           "backstory": "Her sister drowned in the flood."},
          {"name": "Hessa Lin", "backstory": "The Cartographer was her sister."}]],
        [W1, W2])
    b = by_name(cast)
    assert "sister" not in b["Mira Okoye"]["description"] + b["Mira Okoye"]["backstory"]
    assert "sister" in b["Hessa Lin"]["backstory"]


def test_a_description_whose_only_version_fails_kinship_is_still_kept_not_blanked():
    cast = _merge_cast([[{"name": "Mira Okoye", "description": "Her sister drowned."}]], [W1])
    assert cast[0]["description"] == "Her sister drowned."     # never silently blank


def test_no_window_text_means_no_kinship_check():
    cast = _merge_cast([[{"name": "Mira", "description": "Her sister drowned."}]])
    assert cast[0]["description"] == "Her sister drowned."


# ── A10: presence in the merge ───────────────────────────────────────────────

def test_presence_on_page_wins_and_invalid_defaults_to_on_page():
    cast = _merge_cast([[{"name": "Vell", "presence": "referenced"}],
                        [{"name": "Vell", "presence": "on_page"}],
                        [{"name": "the Cartographer", "presence": "historical", "status": "deceased"}],
                        [{"name": "Corvin", "presence": "ghost"}]])
    b = by_name(cast)
    assert b["Vell"]["presence"] == "on_page"
    assert b["the Cartographer"]["presence"] == "historical" and b["the Cartographer"]["status"] == "deceased"
    assert b["Corvin"]["presence"] == "on_page"


# ── truncated model output ───────────────────────────────────────────────────

def test_cut_off_json_keeps_complete_characters_only():
    raw = ('[{"name": "Mira", "description": "has {braces} and \\"quotes\\""},'
           '{"name": "Hessa", "description": "maps"},{"name": "Cor')
    got = _salvage_json_objects(raw)
    assert [g["name"] for g in got] == ["Mira", "Hessa"]
    assert _salvage_json_objects("not json at all") == []


# ── router: generate / confirm / list ────────────────────────────────────────

@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)


def _stub_cast(monkeypatch, items):
    from services import ai_service

    async def fake(_chapters):
        return items

    monkeypatch.setattr(ai_service, "extract_cast", fake)


def test_generate_cast_presence_duplicates_counts_and_order(monkeypatch):
    from _phase3_helpers import two_authors
    _stub_cast(monkeypatch, [
        {"name": "Zed Minor", "role": "minor", "first_appearance": "Chapter 1"},
        {"name": "the Cartographer", "role": "supporting", "presence": "historical", "status": "deceased"},
        {"name": "Tomas", "role": "supporting", "_possible_duplicate_in_batch": "Tomas Reyne"},
        {"name": "Tomas Reyne", "role": "supporting", "first_appearance": "Chapter 2"},
        {"name": "Ana Lead", "role": "protagonist", "presence": "bogus"},
    ])
    with two_authors() as (db, a, _b, client):
        r = client.post(f"/api/stories/{a.sid}/characters/generate-cast", headers=a.headers, json={})
        assert r.status_code == 200, r.text
        sug = r.json()["suggestions"]
        order = [s["name"] for s in sug]
        assert order[0] == "Ana Lead"                         # protagonist first
        assert order[-1] == "the Cartographer"                # historical last
        b = {s["name"]: s for s in sug}
        assert b["Ana Lead"]["presence"] == "on_page"         # invalid value → on_page
        assert b["the Cartographer"]["presence"] == "historical"
        assert b["Tomas"]["possible_duplicate_in_suggestions"] == "Tomas Reyne"
        assert all(isinstance(s["mention_count"], int) for s in sug)
        # deterministic: same input, same order
        r2 = client.post(f"/api/stories/{a.sid}/characters/generate-cast", headers=a.headers, json={})
        assert [s["name"] for s in r2.json()["suggestions"]] == order


def test_mention_count_is_whole_word_and_alias_aware():
    from routers.characters import _count_mentions
    text = "Ash walked. The ashes cooled. ASH spoke. Captain Ashford left. Ash's coat."
    assert _count_mentions("Ash", [], text) == 3
    assert _count_mentions("Mara Halloran", ["Mara"], "Mara Halloran met Mara. Mara left.") == 3


def test_confirm_persists_presence_and_it_can_be_edited(monkeypatch):
    from _phase3_helpers import two_authors
    from models import Character
    with two_authors() as (db, a, _b, client):
        item = {"name": "the Cartographer", "role": "supporting", "status": "deceased",
                "presence": "historical", "description": "Hessa's sister.", "aliases": [],
                "evidence_snippet": "the Cartographer was my sister"}
        r = client.post(f"/api/stories/{a.sid}/characters/confirm-cast", headers=a.headers,
                        json={"suggestions": [item]})
        assert r.status_code == 201, r.text
        created = r.json()["created"][0]
        assert created["presence"] == "historical" and created["status"] == "deceased"
        cid = created["character_id"]
        bad = client.patch(f"/api/stories/{a.sid}/characters/{cid}", headers=a.headers, json={"presence": "ghost"})
        assert bad.status_code == 422
        ok = client.patch(f"/api/stories/{a.sid}/characters/{cid}", headers=a.headers, json={"presence": "referenced"})
        assert ok.status_code == 200 and ok.json()["presence"] == "referenced"
        db.expire_all()
        assert db.get(Character, cid).presence == "referenced"


def test_saved_characters_stay_alphabetical_unless_importance_is_chosen():
    from _phase3_helpers import two_authors
    from models import Character
    with two_authors() as (db, a, _b, client):           # Elara, Kira, Marn
        kira = db.query(Character).filter(Character.story_id == a.sid, Character.name == "Kira").one()
        kira.role = "protagonist"
        marn = db.query(Character).filter(Character.story_id == a.sid, Character.name == "Marn").one()
        marn.presence = "historical"
        db.commit()
        default = [c["name"] for c in client.get(f"/api/stories/{a.sid}/characters", headers=a.headers).json()]
        assert default == ["Elara", "Kira", "Marn"]
        imp = [c["name"] for c in client.get(f"/api/stories/{a.sid}/characters?order=importance", headers=a.headers).json()]
        assert imp == ["Kira", "Elara", "Marn"]
        assert client.get(f"/api/stories/{a.sid}/characters?order=random", headers=a.headers).status_code == 422


# ── Stage 12.3: CAST-H10 failure shape replayed deterministically ────────────
# The raw model output of probe run 7 (docs/testing/stage-12/tranche3/
# cast-variability-probe.json, the shape of every observed failure: runs 7, 8,
# 9, 23): the living antagonist labelled `historical`/`deceased`, the
# Cartographer omitted. CAST-H10 is accepted variability (owner, 2026-10-03);
# what must never happen is that it turns into a lost, merged or reordered-away
# character. These tests pin that without a model (owner-approved treatment,
# 2026-10-06).

CAST_H10_RAW_RUN7 = (
    '[{"name": "Mira Okoye", "presence": "on_page", "role": "protagonist", "status": "active"},'
    ' {"name": "Corvin Ashe", "presence": "on_page", "role": "supporting", "status": "active"},'
    ' {"name": "Hessa Lin", "presence": "on_page", "role": "supporting", "status": "active"},'
    ' {"name": "Magistrate Ondrej Vell", "presence": "historical", "role": "antagonist", "status": "deceased"}]'
)


def _replay_extract_cast(monkeypatch, raw):
    import asyncio
    from services import ai_service
    from routers.search import _html_to_plain
    from tests.fixtures.retrieval_fixture import CHAPTERS

    async def fake_complete(*_a, **_k):
        return raw

    monkeypatch.setattr(ai_service, "_complete", fake_complete)
    texts = [_html_to_plain(c["content"]) for c in CHAPTERS]
    return asyncio.run(ai_service.extract_cast(texts))


def test_cast_h10_failure_shape_keeps_every_character_identity(monkeypatch):
    from tests._cast_identity import identity_problems
    cast = _replay_extract_cast(monkeypatch, CAST_H10_RAW_RUN7)
    assert identity_problems(cast) == []
    vell = [c for c in cast if "ondrej vell" in c["name"].lower()]
    assert len(vell) == 1 and vell[0]["presence"] == "historical"   # label kept, character kept
    assert vell[0]["role"] == "antagonist"


def test_identity_check_catches_lost_merged_and_invented_characters():
    """The identity check itself must fail on the defects it exists for."""
    from tests._cast_identity import identity_problems
    good = [{"name": "Mira Okoye"}, {"name": "Corvin Ashe"}, {"name": "Hessa Lin"},
            {"name": "Ondrej Vell", "presence": "historical", "role": "antagonist"},
            {"name": "The Cartographer", "presence": "historical"}]
    assert identity_problems(good) == []
    assert any(p.startswith("LOST") for p in identity_problems(good[:3]))
    merged = good[:2] + [{"name": "Hessa Lin / Ondrej Vell"}]
    assert any(p.startswith("MERGED") for p in identity_problems(merged))
    invented = good + [{"name": "Captain Arlo Venn"}]
    assert any(p.startswith("INVENTED") for p in identity_problems(invented))
    dup = good + [{"name": "Hessa Lin"}]
    assert any(p.startswith("DUPLICATED") for p in identity_problems(dup))
    carto_on_page = good[:4] + [{"name": "The Cartographer", "presence": "on_page"}]
    assert any(p.startswith("CARTOGRAPHER ON PAGE") for p in identity_problems(carto_on_page))
    flagged = good[:3] + [{"name": "Ondrej Vell", "_possible_combined_with": "Corvin Ashe"}]
    assert any(p.startswith("MERGE FLAG") for p in identity_problems(flagged))


def test_generate_cast_lists_a_living_character_labelled_historical(monkeypatch):
    """Router side of CAST-H10: the mislabelled antagonist is still suggested
    (once, ordered with the off-page figures, not pre-selected by the UI —
    frontend/tests/studio/stage12.spec.ts), never dropped."""
    from _phase3_helpers import two_authors
    _stub_cast(monkeypatch, [
        {"name": "Mira Okoye", "role": "protagonist", "presence": "on_page", "first_appearance": "Chapter 1"},
        {"name": "Corvin Ashe", "role": "supporting", "presence": "on_page", "first_appearance": "Chapter 1"},
        {"name": "Hessa Lin", "role": "supporting", "presence": "on_page", "first_appearance": "Chapter 2"},
        {"name": "Magistrate Ondrej Vell", "role": "antagonist", "presence": "historical",
         "status": "deceased", "first_appearance": "Chapter 4"},
    ])
    with two_authors() as (db, a, _b, client):
        r = client.post(f"/api/stories/{a.sid}/characters/generate-cast", headers=a.headers, json={})
        assert r.status_code == 200, r.text
        sug = r.json()["suggestions"]
        names = [s["name"] for s in sug]
        assert sorted(names) == sorted(["Mira Okoye", "Corvin Ashe", "Hessa Lin", "Magistrate Ondrej Vell"])
        assert names[0] == "Mira Okoye"                        # protagonist first
        assert names[-1] == "Magistrate Ondrej Vell"           # off-page figures last
        assert {s["name"]: s for s in sug}["Magistrate Ondrej Vell"]["presence"] == "historical"
