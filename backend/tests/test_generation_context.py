"""
Stage 7 tasks 7.6 (P3-03 pins as context), 7.8 (P3-06 generate from a
version), 7.9 (P3-07 avoid-set), 7.10 (P3-08 consistency), 7.12 (P3-10 voice),
C7-6 (cross-user story_id on /api/ai/*) and product rule R1, through the real
/api/ai endpoints with a deterministic fake model. Asserts on what actually
reached the prompt and on persisted rows.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_generation_context.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import install_fake_model, pin_payload, tiny_plan, two_authors  # noqa: E402
from config import settings  # noqa: E402
from models import (  # noqa: E402
    AiGenerationPin, ChapterSummary, NoteCard, StoryDNA, StoryMemoryEntry, StoryWorldProfile,
)

TEXT = "Elara walked down the long corridor. She was tired, and she looked at every door."


@pytest.fixture(autouse=True)
def _no_background_embedding(monkeypatch):
    monkeypatch.setattr(settings, "pin_store_embedding", False)


def _echo(system, user, i):
    return "Elara crept down the corridor, counting doors she did not trust."


def _tone(client, author, controls=None, **extra):
    body = {"story_id": author.sid, "chapter_id": author.chapters[1].chapter_id, "text": TEXT, "tone": "dark"}
    if controls is not None:
        body["controls"] = controls
    body.update(extra)
    return client.post("/api/ai/tone", headers=author.headers, json=body)


# ── C7-6: ownership on every /api/ai endpoint that takes a story_id ──────────

@pytest.mark.parametrize("path,body", [
    ("/api/ai/refine", {"text": TEXT}),
    ("/api/ai/tone", {"text": TEXT, "tone": "dark"}),
    ("/api/ai/emotion", {"text": TEXT, "emotion": "fear"}),
    ("/api/ai/age-adapt", {"text": TEXT, "target_age": "adult"}),
    ("/api/ai/style", {"text": TEXT, "style": "noir"}),
    ("/api/ai/author-style", {"text": TEXT, "author": "austen"}),
    ("/api/ai/translate", {"text": TEXT, "target_language": "fr"}),
    ("/api/ai/suggestions", {"text": TEXT, "chapter_id": "x"}),
    ("/api/ai/compare-summary", {"text_a": "a", "text_b": "b"}),
    ("/api/ai/merge-versions", {"blocks": [{"text": "a"}]}),
])
def test_foreign_story_id_is_404_identical_to_nonexistent(monkeypatch, path, body):
    fake_model = install_fake_model(monkeypatch, _echo)
    with two_authors() as (_db, a, b, client):
        r_foreign = client.post(path, headers=a.headers, json={**body, "story_id": b.sid})
        r_missing = client.post(path, headers=a.headers, json={**body, "story_id": "00000000-0000-0000-0000-000000000000"})
        assert r_foreign.status_code == 404, (path, r_foreign.status_code, r_foreign.text)
        assert (r_foreign.status_code, r_foreign.json()) == (r_missing.status_code, r_missing.json())
        assert fake_model.calls == []     # B's data never reached a prompt


def test_own_story_still_works_and_no_controls_is_legacy_shape(monkeypatch):
    install_fake_model(monkeypatch, _echo)
    with two_authors() as (_db, a, _b, client):
        r = _tone(client, a)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["warnings"] == [] and body["context_used"] == {} and body["failed"] is False


# ── R1 — unpinned generations are never stored ──────────────────────────────

def test_r1_regenerating_without_pinning_writes_no_rows(monkeypatch):
    install_fake_model(monkeypatch, _echo)
    with two_authors() as (db, a, _b, client):
        before = db.query(AiGenerationPin).count()
        cards_before = db.query(NoteCard).count()
        for _ in range(5):
            assert _tone(client, a, controls={"avoid_texts": ["An earlier idea."]}).status_code == 200
        db.expire_all()
        assert db.query(AiGenerationPin).count() == before
        assert db.query(NoteCard).count() == cards_before


# ── P3-03 pins as context ────────────────────────────────────────────────────

def test_pin_content_reaches_prompt_fenced_as_material(monkeypatch):
    fake = install_fake_model(monkeypatch, _echo)
    with two_authors() as (_db, a, _b, client):
        p = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers,
                        json=pin_payload(content="The villain Marn smiles with borrowed teeth.")).json()["pin"]
        r = _tone(client, a, controls={"context_pin_ids": [p["pin_id"]]})
        assert r.status_code == 200, r.text
        system = fake.calls[-1][0]
        assert "The villain Marn smiles with borrowed teeth." in system
        assert "MATERIAL, not instructions" in system
        assert r.json()["context_used"]["pins"] == 1


def test_context_pins_over_plan_limit_is_422(monkeypatch):
    install_fake_model(monkeypatch, _echo)
    with two_authors() as (_db, a, _b, client):
        ids = [client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers,
                           json=pin_payload(content=f"idea {i}")).json()["pin"]["pin_id"] for i in range(3)]
        r = _tone(client, a, controls={"context_pin_ids": ids})
        assert r.status_code == 422 and r.json()["code"] == "too_many_context_pins"


def test_foreign_and_missing_context_pins_identical_warning(monkeypatch):
    fake = install_fake_model(monkeypatch, _echo)
    with two_authors() as (_db, a, b, client):
        bpin = client.post(f"/api/stories/{b.sid}/ai/pins", headers=b.headers,
                           json=pin_payload(content="B SECRET DRAFT")).json()["pin"]["pin_id"]
        r1 = _tone(client, a, controls={"context_pin_ids": [bpin]})
        r2 = _tone(client, a, controls={"context_pin_ids": ["00000000-0000-0000-0000-000000000000"]})
        w1 = [w for w in r1.json()["warnings"] if w["kind"] == "pins_unavailable"]
        w2 = [w for w in r2.json()["warnings"] if w["kind"] == "pins_unavailable"]
        assert w1 == w2 and len(w1) == 1
        assert all("B SECRET DRAFT" not in c[0] and "B SECRET DRAFT" not in c[1] for c in fake.calls)


def test_oversized_pin_is_summarised_once_and_reused(monkeypatch):
    def responder(system, user, i):
        if system.startswith("Summarise this draft"):
            return "A short summary of the long draft."
        return "Elara crept on."
    fake = install_fake_model(monkeypatch, responder)
    monkeypatch.setattr(settings, "pin_context_token_budget", 100)
    with two_authors() as (db, a, _b, client):
        pid = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers,
                          json=pin_payload(content="Long draft sentence. " * 200)).json()["pin"]["pin_id"]
        for _ in range(2):
            r = _tone(client, a, controls={"context_pin_ids": [pid]})
            assert r.status_code == 200
        summaries = [c for c in fake.calls if c[0].startswith("Summarise this draft")]
        assert len(summaries) == 1                       # cached in pins.summary
        assert "A short summary of the long draft." in fake.calls[-1][0]
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).one().summary


def test_prompt_stays_within_model_window_at_studio_maximum(monkeypatch):
    fake = install_fake_model(monkeypatch, lambda s, u, i: "A short summary." if s.startswith("Summarise") else "ok")
    with two_authors(plan_a="studio") as (_db, a, _b, client):
        ids = [client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers,
                           json=pin_payload(content=f"Idea {i}. " + "Detail " * 400)).json()["pin"]["pin_id"] for i in range(8)]
        big_text = ("Elara walked. " * 600)[:8000]
        r = client.post("/api/ai/tone", headers=a.headers, json={
            "story_id": a.sid, "chapter_id": a.chapters[0].chapter_id, "text": big_text, "tone": "dark",
            "controls": {"context_pin_ids": ids, "avoid_texts": ["x " * 120] * 8, "style_match": "strong",
                         "local_context": {"before": "w " * 500, "after": "w " * 500}, "instruction": "i " * 290}})
        assert r.status_code == 200, r.text
        system, user, _t = fake.calls[-1]
        est = (len(system) + len(user)) // 4 + 1
        max_out = len(big_text.split()) * 2 + 150
        assert est + max_out < settings.max_model_len, (est, max_out)
        assert r.json()["context_used"]["tokens_estimate"] <= settings.generation_context_token_budget


# ── P3-06 generate from a version ────────────────────────────────────────────

def test_base_pin_becomes_source_draft_with_intent(monkeypatch):
    fake = install_fake_model(monkeypatch, lambda s, u, i: "The corridor breathed. Elara counted four doors.")
    with two_authors() as (_db, a, _b, client):
        p = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers,
                        json=pin_payload(content="The corridor breathed. Elara counted four doors.",
                                         source_excerpt="The corridor was long.")).json()["pin"]
        r = _tone(client, a, controls={"base_pin_id": p["pin_id"], "derivation": "variation"})
        assert r.status_code == 200, r.text
        system, user, temp = fake.calls[-1]
        assert user.startswith("The corridor breathed.") and "ORIGINAL PASSAGE" in user
        assert "variation, not an edit" in system and temp == 0.8
        # The model echoed the draft → anti-echo warning (P3-11 reused by P3-06).
        assert any(w["kind"] == "echo" for w in r.json()["warnings"])
        # Locks cannot be combined with a base version.
        r = _tone(client, a, controls={"base_pin_id": p["pin_id"]}, locked_ranges=[{"start": 0, "end": 5}])
        assert r.status_code == 422 and r.json()["code"] == "locks_with_base_version"
        # Custom intent needs its instruction.
        r = _tone(client, a, controls={"base_pin_id": p["pin_id"], "derivation": "custom"})
        assert r.status_code == 422 and r.json()["code"] == "derivation_param_required"


def test_all_eight_derivation_intents_are_accepted(monkeypatch):
    install_fake_model(monkeypatch, lambda s, u, i: "A fresh take on the corridor.")
    from schemas import DERIVATION_INTENTS
    with two_authors() as (_db, a, _b, client):
        pid = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers,
                          json=pin_payload(content="Base draft.")).json()["pin"]["pin_id"]
        for intent in DERIVATION_INTENTS:
            r = _tone(client, a, controls={"base_pin_id": pid, "derivation": intent, "derivation_param": "calm"})
            assert r.status_code == 200, (intent, r.text)


# ── P3-07 avoid-set ──────────────────────────────────────────────────────────

def test_avoid_block_is_gisted_capped_and_flags_repeats(monkeypatch):
    fake = install_fake_model(monkeypatch, lambda s, u, i: "Elara learns a prophecy foretells the heir's return to the tower.")
    with two_authors() as (_db, a, _b, client):
        avoid = ["Elara learns a prophecy foretells the heir's return to the tower. It is old."] + [f"Idea {i}." for i in range(7)]
        r = _tone(client, a, controls={"avoid_texts": avoid})
        system = fake.calls[-1][0]
        assert "ALREADY EXPLORED" in system and "It is old." not in system       # gist = first sentence
        assert any(w["kind"] == "near_duplicate" for w in r.json()["warnings"])   # informative only
        assert r.status_code == 200 and len([c for c in fake.calls]) == 1         # D12: no auto-retry by default
        r = _tone(client, a, controls={"avoid_texts": ["x"] * 9})
        assert r.status_code == 422                                              # > 8 items rejected


def test_duplicate_auto_retry_when_opted_in(monkeypatch):
    replies = iter(["Elara hears a prophecy foretell the heir's return.", "Elara watches a thief steal the crown at midnight."])
    fake = install_fake_model(monkeypatch, lambda s, u, i: next(replies))
    with two_authors() as (_db, a, _b, client):
        client.patch(f"/api/stories/{a.sid}/ai/preferences", headers=a.headers, json={"pin_prefs": {"duplicate_auto_retry": True}})
        r = _tone(client, a, controls={"avoid_texts": ["Elara hears a prophecy foretell the heir's return."]})
        assert len(fake.calls) == 2 and "thief" in r.json()["transformed"]
        assert fake.calls[1][2] == pytest.approx(0.5 + settings.duplicate_retry_temp_step)


# ── P3-08 consistency ────────────────────────────────────────────────────────

def _seed_story_intelligence(db, author, chapter_number=2):
    from services.ai_service import embed_text_sync
    db.add(StoryMemoryEntry(story_id=author.sid, memory_type="character", memory_key=f"k1-{author.sid}",
                            content="Kira does not know about the sealed letter.", chapter_first_established=1,
                            importance=0.9, embedding=embed_text_sync("Kira does not know about the sealed letter.")))
    db.add(StoryMemoryEntry(story_id=author.sid, memory_type="plot", memory_key=f"k2-{author.sid}",
                            content="FUTURE: Elara dies in the fire.", chapter_first_established=3,
                            importance=1.0, embedding=embed_text_sync("Elara dies in the fire corridor")))
    db.add(StoryWorldProfile(story_id=author.sid, world_rules=["Blood magic costs the caster a memory."]))
    for ch in author.chapters:
        db.add(ChapterSummary(chapter_id=ch.chapter_id, story_id=author.sid, chapter_number=ch.chapter_number,
                              raw_summary=f"SUMMARY-CH{ch.chapter_number}: Elara searches the corridor.",
                              embedding=embed_text_sync(f"Elara searches the corridor chapter {ch.chapter_number}")))
    db.commit()


def test_consistency_block_grounded_and_never_includes_future_chapters(monkeypatch):
    fake = install_fake_model(monkeypatch, lambda s, u, i: "Kira read the sealed letter aloud while Elara walked.")
    with two_authors() as (db, a, _b, client):
        _seed_story_intelligence(db, a)
        r = _tone(client, a, controls={})       # chapter 2
        assert r.status_code == 200, r.text
        system = fake.calls[-1][0]
        assert "STORY CONTEXT" in system and "Blood magic costs the caster a memory." in system
        assert "Kira does not know about the sealed letter." in system
        assert "FUTURE: Elara dies" not in system and "SUMMARY-CH3" not in system
        kinds = {w["kind"] for w in r.json()["warnings"]}
        assert "knowledge_violation" in kinds                     # Tier 1
        kv = next(w for w in r.json()["warnings"] if w["kind"] == "knowledge_violation")
        assert kv["entity"]["type"] == "story_fact" and kv["severity"] == "soft"
        assert r.json()["transformed"]                              # never hard-blocked


def test_no_intelligence_degrades_with_honest_chip(monkeypatch):
    install_fake_model(monkeypatch, _echo)
    with two_authors() as (_db, a, _b, client):
        # No known character in the passage and no intelligence rows, but the
        # author enforced story facts → the block is attempted, finds nothing,
        # and SAYS so instead of pretending the output was grounded.
        r = _tone(client, a, controls={"preserve": {"story_facts": True}},
                  text="The rain kept falling on the empty harbour all night long.")
        assert r.status_code == 200, r.text
        assert any(w["kind"] == "grounding_unavailable" for w in r.json()["warnings"])


def test_strict_mode_is_plan_gated(monkeypatch):
    def responder(system, user, i):
        if "check a rewritten passage" in system:
            return '{"issues": [{"kind": "world_rule", "message": "Magic was used with no cost."}]}'
        return "Elara used blood magic freely."
    fake = install_fake_model(monkeypatch, responder)
    with two_authors(plan_b="pro") as (db, a, b, client):
        _seed_story_intelligence(db, a)
        _seed_story_intelligence(db, b)
        ra = _tone(client, a, controls={"consistency": "strict"})
        assert any(w["kind"] == "strict_unavailable" for w in ra.json()["warnings"])
        assert not any("check a rewritten passage" in c[0] for c in fake.calls)
        rb = _tone(client, b, controls={"consistency": "strict"})
        assert any(w["kind"] == "consistency" for w in rb.json()["warnings"])
        assert rb.json()["context_used"]["strict_check"] is True


def test_consistency_skipped_for_translate_and_when_off(monkeypatch):
    from services.consistency import should_attach
    assert should_attach("translate", mode="auto", has_names=True, rules={}) is False
    assert should_attach("tone", mode="off", has_names=True, rules={}) is False
    assert should_attach("style", mode="auto", has_names=False, rules={}) is False
    assert should_attach("tone", mode="auto", has_names=False, rules={"story_facts": True}) is True


# ── P3-10 voice ──────────────────────────────────────────────────────────────

def test_voice_levels(monkeypatch):
    fake = install_fake_model(monkeypatch, _echo)
    with two_authors() as (db, a, _b, client):
        r = _tone(client, a, controls={"style_match": "light"})
        assert any(w["kind"] == "voice_fingerprint_unavailable" for w in r.json()["warnings"])
        db.add(StoryDNA(story_id=a.sid, pov_style="third person limited", tense="past",
                        sentence_rhythm="short, clipped", vocabulary_tier="plain", prose_style="sparse tags"))
        db.add(NoteCard(story_id=a.sid, user_id=a.uid, content="SAMPLE-VOICE: Rain. Then nothing.", card_type="style_sample"))
        db.commit()
        _tone(client, a, controls={"style_match": "light"})
        light = fake.calls[-1][0]
        assert "AUTHOR VOICE" in light and "short, clipped" in light and "SAMPLE-VOICE" not in light
        _tone(client, a, controls={"style_match": "strong", "local_context": {"before": "BEFORE-CTX", "after": "AFTER-CTX"}})
        strong = fake.calls[-1][0]
        assert "SAMPLE-VOICE" in strong and "BEFORE-CTX" in strong
        _tone(client, a, controls={"style_match": "off"})
        assert "AUTHOR VOICE" not in fake.calls[-1][0]


def test_light_is_the_default_and_costs_about_90_tokens(monkeypatch):
    fake = install_fake_model(monkeypatch, _echo)
    with two_authors() as (db, a, _b, client):
        db.add(StoryDNA(story_id=a.sid, pov_style="third person limited", tense="past",
                        sentence_rhythm="short, clipped; frequent fragments", vocabulary_tier="plain, concrete",
                        prose_style="sparse dialogue tags; physical detail over interiority"))
        db.commit()
        _tone(client, a, controls={})
        system = fake.calls[-1][0]
        start = system.index("AUTHOR VOICE")
        block = system[start:].split("\n\n")[0]
        tokens = len(block) // 4 + 1
        assert 30 <= tokens <= 150, tokens


# ── P3-05 preferences + per-request override ─────────────────────────────────

def test_project_defaults_persist_and_request_override_wins(monkeypatch):
    fake = install_fake_model(monkeypatch, _echo)
    with two_authors() as (_db, a, _b, client):
        r = client.patch(f"/api/stories/{a.sid}/ai/preferences", headers=a.headers,
                         json={"preserve_rules": {"tense": True}, "preserve_tone": False})
        assert r.status_code == 200 and r.json()["preserve_rules"]["tense"] is True
        assert client.get(f"/api/stories/{a.sid}/ai/preferences", headers=a.headers).json()["preserve_tone"] is False
        _tone(client, a, controls={})
        assert "Keep the narration in" in fake.calls[-1][0]
        _tone(client, a, controls={"preserve": {"tense": False}})
        assert "Keep the narration in" not in fake.calls[-1][0]


def test_name_change_is_repaired_once_then_reported_with_autofix(monkeypatch):
    fake = install_fake_model(monkeypatch, lambda s, u, i: "Elarah walked down the corridor, tired, looking at doors.")
    with two_authors() as (_db, a, _b, client):
        r = _tone(client, a, controls={})
        body = r.json()
        assert len(fake.calls) == 2                                  # exactly one repair retry
        assert fake.calls[1][2] == pytest.approx(0.4)                # temperature − 0.1
        assert body["preservation_violations"] == ["Elara"]
        assert body["name_autofix"] == [{"replace": "Elarah", "with": "Elara"}]
        w = next(x for x in body["warnings"] if x["kind"] == "name_changed")
        assert w["severity"] == "hard" and w["autofix"] == [{"replace": "Elarah", "with": "Elara"}]
        assert body["transformed"].startswith("Elarah")              # never silently rewritten
