"""
Unit tests for the Real-Time Voice Agent core (no DB, no LLM, no GPU).

Covers: capability/intent registry coverage, normalization, reference
resolution (B), safety/confirmation rules, and the multi-step planner (A) with a
stubbed Qwen — single-step, multi-step, invalid-graph fallback, and cycle
detection. Run: pytest backend/tests/test_voice_unit.py -q
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.voice import capabilities as cap
from services.voice import catalog, normalize, reference, safety, planner, intent
from services.voice.planner import TaskNode, ExecutionGraph


# ── Registry coverage (C) ─────────────────────────────────────────────────────

def test_registry_covers_all_phases():
    expected = {
        "project_mgmt", "chapter_mgmt", "character_mgmt", "character_voice_check",
        "intake_genre", "plot_assistant", "text_transform", "manuscript_import",
        "export", "search_replace", "plot_holes", "manuscript_report", "story_intel",
        "narrative_threads", "emotional_arc", "continuation", "duplicate_scenes",
        "style_drift", "story_bible", "outline", "continuity_check", "pacing_goals",
        "ocr_inject", "voice_note", "account",
    }
    assert expected <= set(cap.CAPABILITY_REGISTRY)


def test_every_action_has_client_call_and_intent_entry():
    for name, c in cap.CAPABILITY_REGISTRY.items():
        for action, spec in c.actions.items():
            assert spec.client_call == f"{name}.{action}"
            assert f"{name}.{action}" in catalog.INTENT_REGISTRY


def test_confirmation_defaults_by_action_type():
    assert cap.get_action("project_mgmt", "delete").needs_confirmation() is True   # destructive
    assert cap.get_action("export", "export").needs_confirmation() is True          # export
    assert cap.get_action("emotional_arc", "analyze").needs_confirmation() is False # analyze
    assert cap.get_action("plot_assistant", "brainstorm").needs_confirmation() is False  # generate


# ── Normalization + ordinals ──────────────────────────────────────────────────

def test_normalize_numbers_and_fillers():
    assert normalize.normalize_command("um, open chapter three") == "open chapter 3"
    assert "basically" not in normalize.normalize_command("basically make it darker")


def test_extract_ordinal():
    assert normalize.extract_ordinal("use the second option") == 1
    assert normalize.extract_ordinal("the last one") == -1
    assert normalize.extract_ordinal("no number here") is None


# ── Reference resolution (B) ──────────────────────────────────────────────────

class _Mem(dict):
    def get(self, k, d=None):  # noqa: D401
        return dict.get(self, k, d)


def _ctx(**kw):
    base = dict(selected_text=None, has_selection=False, chapter_id=None,
                active_character_id=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_reference_second_option():
    mem = _Mem(last_continuation=[{"text": "A"}, {"text": "B"}, {"text": "C"}])
    r = reference.resolve("use the second option", mem, _ctx())
    assert r.option_index == 1 and r.option_text == "B"


def test_reference_pronoun_uses_selection_then_memory():
    mem = _Mem(last_selected_text="old text")
    r = reference.resolve("make it darker", mem, _ctx(selected_text="live sel", has_selection=True))
    assert r.selected_text == "live sel"
    r2 = reference.resolve("make it darker", mem, _ctx())
    assert r2.selected_text == "old text"


def test_reference_same_character_and_chapter():
    mem = _Mem(last_character_id="char-7", last_chapter_id="chap-3")
    r = reference.resolve("check the same character", mem, _ctx())
    assert r.character_id == "char-7"
    r2 = reference.resolve("in that chapter", mem, _ctx())
    assert r2.chapter_id == "chap-3"


def test_reference_unresolved_when_no_memory():
    r = reference.resolve("use the third option", _Mem(), _ctx())
    assert "option" in r.unresolved


# ── Safety / confirmation (gate) ──────────────────────────────────────────────

def _node(cap_name, action):
    spec = cap.get_action(cap_name, action)
    return TaskNode(node_key="n", capability=cap_name, action=action,
                    action_type=spec.action_type, execution_locus=spec.execution_locus,
                    requires_confirmation=spec.needs_confirmation())


def test_safety_marks_destructive_and_export(monkeypatch):
    g = ExecutionGraph(nodes=[_node("project_mgmt", "delete")], is_multi_step=False)
    assert safety.apply(g, confidence=0.9) is True
    assert g.nodes[0].requires_confirmation is True


def test_safety_skips_safe_reads():
    g = ExecutionGraph(nodes=[_node("emotional_arc", "analyze")], is_multi_step=False)
    assert safety.apply(g, confidence=0.9) is False
    assert g.nodes[0].requires_confirmation is False


def test_safety_multistep_terminal_write_confirms():
    g = ExecutionGraph(
        nodes=[_node("pacing_goals", "get"), _node("text_transform", "apply_rewrite")],
        is_multi_step=True,
    )
    assert safety.apply(g, confidence=0.9) is True
    write = next(n for n in g.nodes if n.action == "apply_rewrite")
    assert write.requires_confirmation is True


# ── Planner (A) with stubbed Qwen ─────────────────────────────────────────────

def _stub_shortlist(monkeypatch, names):
    monkeypatch.setattr("services.voice.catalog.shortlist",
                        lambda q, k=8: [(n, 0.9) for n in names])


def _stub_complete(monkeypatch, payload_json: str):
    async def fake(*a, **k):
        return payload_json
    monkeypatch.setattr("services.ai_service._complete", fake)


@pytest.mark.asyncio
async def test_planner_single_step(monkeypatch):
    _stub_shortlist(monkeypatch, ["project_mgmt", "chapter_mgmt"])
    _stub_complete(monkeypatch,
                   '{"is_multi_step": false, "steps": [{"key":"n1",'
                   '"capability":"project_mgmt","action":"create",'
                   '"params":{"title":"The Silent Floor"},"depends_on":[]}]}')
    g = await planner.plan("create a thriller called The Silent Floor")
    assert len(g.nodes) == 1 and not g.is_multi_step
    assert g.nodes[0].capability == "project_mgmt" and g.nodes[0].action == "create"
    assert g.nodes[0].params.get("title") == "The Silent Floor"


@pytest.mark.asyncio
async def test_planner_multi_step_with_deps(monkeypatch):
    _stub_shortlist(monkeypatch, ["pacing_goals", "text_transform"])
    _stub_complete(monkeypatch,
                   '{"is_multi_step": true, "steps": ['
                   '{"key":"a","capability":"pacing_goals","action":"get","depends_on":[]},'
                   '{"key":"b","capability":"text_transform","action":"rewrite_section",'
                   '"params":{"goal":"tighten pacing"},"depends_on":["a"]},'
                   '{"key":"c","capability":"text_transform","action":"apply_rewrite",'
                   '"depends_on":["b"]}]}')
    g = await planner.plan("analyze pacing then rewrite the slow sections")
    assert g.is_multi_step and len(g.nodes) == 3
    order = [n.node_key for n in g.topo_order()]
    assert order.index("a") < order.index("b") < order.index("c")


@pytest.mark.asyncio
async def test_planner_invalid_falls_back_to_classifier(monkeypatch):
    _stub_shortlist(monkeypatch, ["export"])
    # planner returns junk; classify() then returns a valid single intent.
    calls = {"n": 0}

    async def fake_complete(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not json at all"
        return '{"capability":"export","action":"export","confidence":0.8,"params":{}}'
    monkeypatch.setattr("services.ai_service._complete", fake_complete)
    g = await planner.plan("export this story")
    assert len(g.nodes) == 1 and g.nodes[0].capability == "export"


def test_fast_route_high_precision():
    from services.voice.fastroute import fast_route
    cap, act, p = fast_route("Replace the name Raj with Arjun in chapter one")
    assert (cap, act) == ("search_replace", "replace")
    assert p["query"] == "Raj" and p["replacement"] == "Arjun"
    assert fast_route("Open chapter 3")[:2] == ("chapter_mgmt", "open")
    assert fast_route("Delete this story")[:2] == ("project_mgmt", "delete")
    assert fast_route("Export this story")[:2] == ("export", "export")
    cap, act, p = fast_route("Create a new thriller story called The Silent Floor")
    assert (cap, act) == ("project_mgmt", "create") and p["title"] == "The Silent Floor"
    # chained commands fall through to the LLM planner
    assert fast_route("analyze pacing then rewrite the slow sections") is None


@pytest.mark.asyncio
async def test_planner_fast_route_skips_llm(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("LLM should not be called for a fast-routed command")
    monkeypatch.setattr("services.ai_service._complete", boom)
    g = await planner.plan("Delete this story")
    assert len(g.nodes) == 1 and g.nodes[0].capability == "project_mgmt"
    assert g.nodes[0].action == "delete" and g.nodes[0].requires_confirmation is True


# ── Story-aware corrections, guards, clarification (the live-test fixes) ──────

def test_stt_english_default_config():
    from config import settings
    assert settings.voice_stt_language == "en"
    assert settings.voice_stt_auto_language is False  # no auto language switching


def test_story_vocabulary_correction_is_generic():
    from services.voice.vocabulary import _make_term, VocabTerm, _phonetic, correct_transcript
    # vocabulary built from arbitrary story data — no hardcoded names
    vocab = [
        _make_term("Mr. Dinesh", "character", "c1"),
        VocabTerm("Dinesh", "character", "c1", ["dinesh"], _phonetic("dinesh")),
        _make_term("The Silent Floor", "chapter", "ch1"),
    ]
    out, corr = correct_transcript("tell me about dynesh", vocab, min_score=84)
    assert any(c["to"] == "Dinesh" and c["ref_id"] == "c1" for c in corr)
    out2, corr2 = correct_transcript("open the silent flor", vocab, min_score=84)
    assert "The Silent Floor" in out2
    # common words are NOT rewritten to story terms
    out3, corr3 = correct_transcript("make this more emotional", vocab, min_score=84)
    assert corr3 == []


def test_phonetic_matching_resolves_misheard_names():
    import jellyfish
    assert jellyfish.metaphone("Dinesh") == jellyfish.metaphone("Dynesh")


def test_guards_question_and_compound():
    from services.voice.guards import is_question, is_compound, has_actionable_verb
    assert is_question("who is the villain?") is True
    assert is_question("make this darker") is False
    assert is_compound("analyze pacing then rewrite the slow parts") is True
    assert is_compound("find plot holes") is False
    assert has_actionable_verb("where does he appear") is False


def test_clarification_never_exposes_internal_ids():
    from services.voice.clarify import build_clarification
    q, opts = build_clarification(["character_id"], story_id=None, db=None)
    assert "character_id" not in q and "id" not in q.lower().split()
    assert q == "Which character?"
    q2, _ = build_clarification(["chapter_id"], story_id=None, db=None)
    assert "chapter_id" not in q2
    q3, _ = build_clarification(["text"], story_id="s", db=None)
    assert "text" not in q3.split("_") and "select" in q3.lower()


@pytest.mark.asyncio
async def test_questions_route_to_correct_feature_not_plot(monkeypatch):
    # Topic routing must NOT call the LLM and must hit the RIGHT feature.
    async def boom(*a, **k):
        raise AssertionError("LLM should not be called for a topic-routed question")
    monkeypatch.setattr("services.ai_service._complete", boom)

    cases = {
        "who is the antagonist in this story":            ("character_qa", "ask"),
        "what is the relationship between the two leads":  ("character_relationship", "ask"),
        "what should happen next in the story":            ("plot_assistant", "brainstorm"),
        "is the pacing too slow":                          ("pacing_goals", "get"),
        "are there any continuity issues":                 ("continuity_check", "analyze"),
        "what happens at the end of the story":            ("story_qa", "ask"),  # generic factual default
    }
    for cmd, (cap, act) in cases.items():
        g = await planner.plan(cmd)
        assert len(g.nodes) == 1 and not g.is_multi_step, cmd
        assert (g.nodes[0].capability, g.nodes[0].action) == (cap, act), \
            f"{cmd!r} -> {g.nodes[0].capability}.{g.nodes[0].action}"


@pytest.mark.asyncio
async def test_no_factual_question_routes_to_plot_assistant(monkeypatch):
    # Regression: plot_assistant must be reachable ONLY for brainstorming.
    async def fake(*a, **k):
        return '{"capability":"none","action":"","confidence":0.0}'
    monkeypatch.setattr("services.ai_service._complete", fake)
    for cmd in ["who is the killer", "what is the relationship between X and Y",
                "what happens in chapter two", "where does the hero appear"]:
        g = await planner.plan(cmd)
        assert not any(n.capability == "plot_assistant" for n in g.nodes), cmd


def test_qa_features_are_server_sync_with_adapters():
    from services.voice.capabilities import get_action
    from services.voice.adapters import SERVER_ADAPTERS
    for cap in ("story_qa", "character_qa", "character_relationship"):
        spec = get_action(cap, "ask")
        assert spec.execution_locus == "server" and spec.model_service
        assert (cap, "ask") in SERVER_ADAPTERS


def test_orchestrator_has_no_direct_model_calls():
    import inspect
    import services.voice.orchestrator as o
    src = inspect.getsource(o)
    assert "_complete" not in src and "embed_text" not in src and "get_bge" not in src


def test_text_transform_bound_to_ai_transform_feature():
    from services.voice.capabilities import CAPABILITY_REGISTRY, get_action
    assert CAPABILITY_REGISTRY["text_transform"].router == "ai_transform"
    for action in ("emotion", "tone", "refine"):
        spec = get_action("text_transform", action)
        assert spec.execution_locus == "client" and "ai_transform" in spec.model_service


@pytest.mark.asyncio
async def test_non_compound_collapses_to_single_step(monkeypatch):
    _stub_shortlist(monkeypatch, ["text_transform"])
    _stub_complete(monkeypatch,
                   '{"is_multi_step": true, "steps": ['
                   '{"key":"a","capability":"text_transform","action":"refine","depends_on":[]},'
                   '{"key":"b","capability":"text_transform","action":"tone","depends_on":["a"]}]}')
    g = await planner.plan("polish this paragraph")   # not compound
    assert len(g.nodes) == 1 and not g.is_multi_step


@pytest.mark.asyncio
async def test_compound_request_stays_multi_step(monkeypatch):
    _stub_shortlist(monkeypatch, ["pacing_goals", "text_transform"])
    _stub_complete(monkeypatch,
                   '{"is_multi_step": true, "steps": ['
                   '{"key":"a","capability":"pacing_goals","action":"get","depends_on":[]},'
                   '{"key":"b","capability":"text_transform","action":"rewrite_section","depends_on":["a"]}]}')
    g = await planner.plan("check the pacing then rewrite the slow sections")
    assert g.is_multi_step and len(g.nodes) == 2


def test_delete_chapter_is_destructive_fastroute():
    from services.voice.fastroute import fast_route
    cap, act, _ = fast_route("delete this chapter")
    assert (cap, act) == ("chapter_mgmt", "delete")
    from services.voice.capabilities import get_action
    assert get_action("chapter_mgmt", "delete").needs_confirmation() is True


# ── Selected-text transform fix (RAG misuse regression) ──────────────────────

def test_transform_intents_are_generic():
    from services.voice.fastroute import transform_action
    # generic intents (not hardcoded phrases), with a selection present
    assert transform_action("make this more emotional", True) == "emotion"
    assert transform_action("change the tone to be lighter", True) == "tone"
    assert transform_action("adapt this for a younger audience", True) == "age_adapt"
    assert transform_action("rewrite this paragraph", True) == "refine"
    assert transform_action("simplify this", True) == "refine"
    assert transform_action("make it more suspenseful", True) == "emotion"
    assert transform_action("translate this to french", True) == "translate"
    assert transform_action("make this gothic", True) == "style"
    # a factual question about tone is NOT a transform (no selection)
    assert transform_action("what is the tone of the story", False) is None


@pytest.mark.asyncio
async def test_selected_text_transform_routes_to_ai_transform_not_rag(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("LLM/RAG must not be consulted for a selected-text transform")
    monkeypatch.setattr("services.ai_service._complete", boom)
    for cmd in ["make this more emotional", "adapt this for a younger audience",
                "change the tone", "rewrite this paragraph", "make it more suspenseful"]:
        g = await planner.plan(cmd, has_selection=True)
        assert len(g.nodes) == 1, cmd
        n = g.nodes[0]
        assert n.capability == "text_transform", f"{cmd!r} -> {n.capability}"
        # never a RAG/Q&A/plot capability
        assert n.capability not in ("story_qa", "character_qa", "character_relationship", "plot_assistant")


def test_transform_uses_selected_text_only_not_memory_or_chapter():
    from services.voice.context import resolve_node_params
    from services.voice.planner import TaskNode
    from services.voice.capabilities import get_action

    def node():
        s = get_action("text_transform", "emotion")
        return TaskNode(node_key="n", capability="text_transform", action="emotion",
                        action_type=s.action_type, params={})

    class Refs:
        selected_text = None; character_id = None; character_name = None
        chapter_id = None; option_text = None
    class Mem(dict):
        def get(self, k, d=None): return dict.get(self, k, d)

    # WITH selection → uses it
    ctx = types.SimpleNamespace(story_id="s", selected_text="PICK ME", has_selection=True,
                                chapter_id="c", active_character_id=None, full_chapter_text="WHOLE CHAPTER")
    n = node()
    missing = resolve_node_params(n, ctx, Refs(), Mem(last_selected_text="OLD"), None)
    assert n.params.get("text") == "PICK ME" and missing == []

    # WITHOUT selection → does NOT borrow chapter text or stale memory → clarifies
    ctx2 = types.SimpleNamespace(story_id="s", selected_text=None, has_selection=False,
                                 chapter_id="c", active_character_id=None, full_chapter_text="WHOLE CHAPTER")
    n2 = node()
    missing2 = resolve_node_params(n2, ctx2, Refs(), Mem(last_selected_text="OLD"), None)
    assert n2.params.get("text") is None and "text" in missing2


def test_no_selection_transform_asks_to_select_first():
    from services.voice.clarify import build_clarification
    q, _ = build_clarification(["text"], story_id="s", db=None)
    assert "select" in q.lower() and "_id" not in q


@pytest.mark.asyncio
async def test_planner_drops_invalid_capability(monkeypatch):
    _stub_shortlist(monkeypatch, ["project_mgmt"])
    _stub_complete(monkeypatch,
                   '{"steps":[{"key":"n1","capability":"does_not_exist","action":"nope"}]}')
    # invalid step → no nodes → fallback classify (also invalid) → empty graph
    async def fake_complete(*a, **k):
        return '{"capability":"none","action":"","confidence":0.0}'
    monkeypatch.setattr("services.ai_service._complete", fake_complete)
    g = await planner.plan("xyzzy quantum banana sprocket")
    assert g.nodes == []
