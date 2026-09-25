"""
Phase 3 P3-08 — character and story-fact consistency (spec §26).

Builds a narrow, budget-capped STORY CONTEXT block from data the platform
already computes — characters, character intelligence, story memory
entries, world rules, timeline events and earlier-chapter summaries — and
runs the post-generation checks:

  Tier 0 (always, free)   character-name check — shared with P3-05, lives in
                          transform_preservation / the transform pipeline.
  Tier 1 (always, free)   knowledge-state check: a story fact recording
                          "X does not know Y" + an output where X appears
                          alongside a NEWLY introduced key term of Y.
  Tier 2 (opt-in, 1 LLM)  strict JSON judgement against the block; gated to
                          plans with strict_consistency (decision D6: pro+).

No new storage. Every source is Phase 1/2 data. Future chapters are never
included: every chapter-scoped query is bounded by the current chapter
number, and without a known chapter position no chapter-scoped evidence is
used at all. Each sub-builder is independently fail-soft (spec §11.4:
context assembly never fails a generation).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


def estimate_tokens(s: str) -> int:
    return len(s or "") // 4 + 1 if s else 0


def _cap(text: str, tokens: int) -> str:
    """Trim at a line boundary to fit the token cap."""
    if estimate_tokens(text) <= tokens:
        return text
    out, used = [], 0
    for line in text.splitlines():
        t = estimate_tokens(line + "\n")
        if used + t > tokens:
            break
        out.append(line)
        used += t
    return "\n".join(out)


# Per-sub-block caps (spec §P3-08 table), scaled if the total budget differs.
_SUB_CAPS = {"characters": 350, "psychology": 200, "facts": 250, "world": 120, "timeline": 80, "narrative": 200}
# Trim order when over budget: lowest importance first.
TRIM_ORDER = ("narrative", "timeline", "world", "psychology", "facts", "characters")


@dataclass
class ConsistencyContext:
    sections: dict[str, str] = field(default_factory=dict)   # name → rendered lines
    character_ids: list[str] = field(default_factory=list)
    character_names: list[str] = field(default_factory=list)
    facts_used: int = 0
    knowledge_facts: list[dict] = field(default_factory=list)   # [{entry_id, who, what}]
    degraded: list[str] = field(default_factory=list)
    available: bool = False

    def render(self) -> str:
        if not any(self.sections.values()):
            return ""
        titles = {
            "characters": "CHARACTERS IN THIS PASSAGE", "psychology": "CHARACTER STATE",
            "facts": "ESTABLISHED FACTS", "world": "WORLD RULES",
            "timeline": "TIMELINE", "narrative": "EARLIER IN THE STORY",
        }
        parts = ["STORY CONTEXT — facts already established. Do not contradict or extend these. "
                 "If the passage needs a fact that is not here, keep the existing wording rather "
                 "than inventing a detail."]
        for key in ("characters", "psychology", "facts", "world", "timeline", "narrative"):
            if self.sections.get(key):
                parts.append(f"{titles[key]}\n{self.sections[key]}")
        return "\n".join(parts)


def _reset(db) -> None:
    """A failed statement aborts the PostgreSQL transaction; roll back so the
    remaining sub-builders (and the caller) can keep using the session.
    Nothing is pending at this point — context assembly is read-only."""
    try:
        db.rollback()
    except Exception:
        pass


def names_in_text(story_id: str, text: str, db) -> list:
    from models import Character
    from services.ai_service import _make_name_pattern
    found = []
    for c in db.query(Character).filter(Character.story_id == story_id).all():
        pattern = _make_name_pattern(c.name, c.aliases or [])
        if pattern and pattern.search(text or ""):
            found.append(c)
    return found


def should_attach(tool: str, *, mode: str, has_names: bool, rules: dict) -> bool:
    """Activation policy (spec §P3-08): a grammar fix cannot break the
    timeline, so the block is only paid for when a transform plausibly
    touches characters or story facts."""
    if mode == "off" or tool in ("translate",):
        return False
    if mode == "strict":
        return True
    if tool in ("tone", "emotion", "age_adapt"):
        return has_names or rules.get("story_facts") is True
    if tool in ("style", "refine"):
        return has_names
    if tool == "author_style":
        return False
    return True  # continuation / outline / plot suggestions / segment regen


_KNOW_RE = re.compile(
    r"^\s*(?P<who>[A-Z][\w'-]+(?: [A-Z][\w'-]+)?)\s+(?:does not|doesn't|did not|didn't|never|has not|hasn't)\s+"
    r"(?:yet\s+)?(?:know|learn(?:ed|t)?|find out|realis(?:e|ed)|realiz(?:e|ed))\s+(?:about\s+|that\s+)?(?P<what>.+)$",
    re.IGNORECASE,
)


async def build_consistency_context(
    story_id: str, chapter_number: Optional[int], focus_text: str, db,
    token_budget: int = 1200,
) -> ConsistencyContext:
    from models import CharacterIntelligence, StoryMemoryEntry, StoryTimelineEvent, StoryWorldProfile
    ctx = ConsistencyContext()
    scale = token_budget / sum(_SUB_CAPS.values())
    caps = {k: max(40, int(v * scale)) for k, v in _SUB_CAPS.items()}

    # Characters present (name scan) + retrieved profiles.
    try:
        present = names_in_text(story_id, focus_text, db)
        ctx.character_ids = [c.character_id for c in present]
        ctx.character_names = [c.name for c in present]
        if present:
            from services.ai_service import retrieve_character_context
            blocks = await retrieve_character_context(
                story_id, focus_text, db, top_k=min(4, len(present) + 1),
                token_budget=caps["characters"],
                # Unknown position → no chapter-scoped evidence (0 excludes all).
                max_chapter_number=chapter_number if chapter_number is not None else 0,
            )
            ctx.sections["characters"] = _cap("\n".join(f"- {b.strip()}" for b in blocks if b.strip()),
                                              caps["characters"])
    except Exception as exc:
        logger.warning("[consistency] characters failed (%s)", type(exc).__name__)
        _reset(db)
        ctx.degraded.append("characters")

    # Character psychology for the characters actually present.
    try:
        if ctx.character_ids:
            lines = []
            rows = db.query(CharacterIntelligence).filter(
                CharacterIntelligence.story_id == story_id,
                CharacterIntelligence.character_id.in_(ctx.character_ids)).all()
            names = dict(zip(ctx.character_ids, ctx.character_names))
            for r in rows:
                bits = []
                if r.arc_stage:
                    bits.append(f"arc stage: {r.arc_stage}")
                if r.voice_markers:
                    bits.append("voice: " + "; ".join(str(v) for v in (r.voice_markers or [])[:3]))
                if r.fears:
                    bits.append("fears: " + "; ".join(str(v) for v in (r.fears or [])[:2]))
                if bits:
                    lines.append(f"- {names.get(r.character_id, 'Character')} — " + " · ".join(bits))
            ctx.sections["psychology"] = _cap("\n".join(lines), caps["psychology"])
    except Exception as exc:
        logger.warning("[consistency] psychology failed (%s)", type(exc).__name__)
        _reset(db)
        ctx.degraded.append("psychology")

    # Story facts: semantic search over active memory entries, bounded by chapter.
    try:
        from sqlalchemy import text as sql
        from services.ai_service import embed_text, vector_literal, vector_similarity
        has_any = db.query(StoryMemoryEntry.entry_id).filter(
            StoryMemoryEntry.story_id == story_id, StoryMemoryEntry.is_active.is_(True),
            StoryMemoryEntry.embedding.isnot(None)).first()
        if has_any:
            q = vector_literal(await embed_text(focus_text[:2000]))
            chapter_clause = ("AND (chapter_first_established IS NULL OR chapter_first_established <= :ch)"
                              if chapter_number is not None else "AND chapter_first_established IS NULL")
            params = {"q": q, "sid": story_id}
            if chapter_number is not None:
                params["ch"] = chapter_number
            rows = db.execute(sql(f"""
                SELECT entry_id, memory_type, content, chapter_first_established AS ch,
                       {vector_similarity('embedding')} AS score
                FROM story_memory_entries
                WHERE story_id = :sid AND is_active = true AND embedding IS NOT NULL {chapter_clause}
                ORDER BY ({vector_similarity('embedding')}) * 0.7 + COALESCE(importance, 0.5) * 0.3 DESC
                LIMIT 8
            """), params).fetchall()
            lines = []
            for r in rows:
                where = f" (ch. {r.ch})" if r.ch else ""
                lines.append(f"- [story fact] {str(r.content).strip()[:220]}{where}")
                m = _KNOW_RE.match(str(r.content).strip())
                if m:
                    ctx.knowledge_facts.append({"entry_id": r.entry_id, "who": m.group("who"),
                                                "what": m.group("what").rstrip(". ")})
            ctx.sections["facts"] = _cap("\n".join(lines), caps["facts"])
            ctx.facts_used = len(ctx.sections["facts"].splitlines()) if ctx.sections["facts"] else 0
    except Exception as exc:
        logger.warning("[consistency] facts failed (%s)", type(exc).__name__)
        _reset(db)
        ctx.degraded.append("facts")

    # World rules — direct.
    try:
        world = db.query(StoryWorldProfile).filter(StoryWorldProfile.story_id == story_id).first()
        if world and world.world_rules:
            rules = [r if isinstance(r, str) else (r.get("rule") or r.get("description") or "")
                     for r in world.world_rules if r]
            ctx.sections["world"] = _cap("\n".join(f"- {str(r).strip()[:200]}" for r in rules if str(r).strip()),
                                         caps["world"])
    except Exception as exc:
        logger.warning("[consistency] world failed (%s)", type(exc).__name__)
        _reset(db)
        ctx.degraded.append("world")

    # Timeline position — this chapter's events only.
    try:
        if chapter_number is not None:
            events = db.query(StoryTimelineEvent).filter(
                StoryTimelineEvent.story_id == story_id,
                StoryTimelineEvent.chapter_number == chapter_number).limit(4).all()
            lines = []
            for e in events:
                when = e.temporal_marker or e.story_date
                desc = (e.event_description or "").strip()[:160]
                if desc:
                    lines.append(f"- {when + ': ' if when else ''}{desc}")
            ctx.sections["timeline"] = _cap("\n".join(lines), caps["timeline"])
    except Exception as exc:
        logger.warning("[consistency] timeline failed (%s)", type(exc).__name__)
        _reset(db)
        ctx.degraded.append("timeline")

    # Nearby narrative — chapter summaries, never beyond the current chapter.
    try:
        if chapter_number is not None:
            from services.ai_service import retrieve_relevant_chunks
            summaries = await retrieve_relevant_chunks(focus_text[:2000], story_id, db, top_k=2,
                                                       max_chapter_number=chapter_number)
            lines = [f"- (ch. {s.get('chapter')}) {str(s.get('raw_summary') or '').strip()[:300]}"
                     for s in summaries if s.get("raw_summary")]
            ctx.sections["narrative"] = _cap("\n".join(lines), caps["narrative"])
    except Exception as exc:
        logger.warning("[consistency] narrative failed (%s)", type(exc).__name__)
        _reset(db)
        ctx.degraded.append("narrative")

    ctx.available = any(ctx.sections.values())
    return ctx


_STOPWORDS = frozenset(
    "the a an and or but of to in on at for with from by about that this what who his her their "
    "they them there was were is are has have had been yet".split()
)


def knowledge_violations(ctx: ConsistencyContext, source: str, output: str) -> list[dict]:
    """Tier 1 — high precision, low recall, zero cost. Flags only when the
    rewrite INTRODUCES a key term of the unknown fact (absent from the source)
    in a passage where that character appears."""
    warnings = []
    src_l, out_l = (source or "").lower(), (output or "").lower()
    for fact in ctx.knowledge_facts:
        who = fact["who"]
        if who.lower() not in out_l:
            continue
        terms = [w for w in re.findall(r"[a-zA-Z']{4,}", fact["what"].lower()) if w not in _STOPWORDS]
        new_terms = [t for t in terms if t in out_l and t not in src_l]
        if new_terms:
            warnings.append({
                "kind": "knowledge_violation", "severity": "soft",
                "message": f"Your story records that {who} does not know {fact['what']}. "
                           f"This rewrite may have {who} referring to it.",
                "entity": {"type": "story_fact", "id": fact["entry_id"]},
            })
    return warnings[:3]


def _coerce_issues(parsed):
    if not isinstance(parsed, dict) or not isinstance(parsed.get("issues"), list):
        return None, 1
    out, dropped = [], 0
    for it in parsed["issues"][:4]:
        if isinstance(it, dict) and str(it.get("message") or "").strip():
            out.append({"kind": "consistency", "severity": "soft",
                        "message": str(it["message"]).strip()[:300],
                        "entity": {"type": str(it.get("kind") or "fact")}})
        else:
            dropped += 1
    return out, dropped


async def strict_consistency_check(block: str, output: str) -> tuple[list[dict], bool]:
    """Tier 2 — one JSON-returning judgement (via complete_structured, the
    repo's structured-output contract) against the STORY CONTEXT. Returns
    (warnings, ran_ok). Never raises; never blocks."""
    if not block.strip():
        return [], False
    from services.ai_service import complete_structured
    system = (
        "You check a rewritten passage against established story context. Report ONLY clear "
        "contradictions of the context (a character acting against a recorded trait, a broken world "
        "rule, a contradicted fact). Do not report style issues. Return ONLY JSON: "
        '{"issues": [{"kind": "trait|world_rule|fact", "message": "one short sentence"}]} '
        'Return {"issues": []} when there is no clear contradiction.'
    )
    try:
        value, _meta = await complete_structured(
            system, f"{block}\n\nREWRITTEN PASSAGE:\n{output[:6000]}", coerce=_coerce_issues,
            temperature=0.1, max_tokens=300, label="strict_consistency")
    except Exception as exc:
        logger.warning("[consistency] strict check unavailable (%s)", type(exc).__name__)
        return [], False
    if value is None:
        return [], False
    return value, True
