"""
AI Service — vLLM + BGE-M3

Text generation  →  vLLM serving Qwen2.5-7B-Instruct (OpenAI-compatible API)
Embeddings       →  BGE-M3 via sentence-transformers (in-process, CUDA or CPU)
OCR              →  see ocr_service.py

vLLM is a separate process started by start.sh before FastAPI boots.
The OpenAI async client connects to it at localhost:8080/v1.
Models stay permanently loaded in GPU VRAM — no cold starts after warmup.
"""

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Optional

from openai import AsyncOpenAI, APIConnectionError, APIStatusError
from sentence_transformers import SentenceTransformer

from config import settings
from exceptions import AIResponseTruncatedError, AIServiceUnavailableError

logger = logging.getLogger(__name__)

# ── Singletons ────────────────────────────────────────────────────────────────

_vllm_client: AsyncOpenAI | None = None
_bge_model: SentenceTransformer | None = None
_bge_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bge")


def get_vllm_client() -> AsyncOpenAI:
    global _vllm_client
    if _vllm_client is None:
        _vllm_client = AsyncOpenAI(
            base_url=settings.vllm_base_url,
            api_key="vllm-local",   # vLLM ignores the key when no auth is set
            timeout=120.0,
            max_retries=1,
        )
    return _vllm_client


def get_bge() -> SentenceTransformer:
    global _bge_model
    if _bge_model is None:
        _bge_model = SentenceTransformer(settings.bge_path, device=settings.bge_device)
    return _bge_model


# ── pgvector / embedding helpers — SINGLE SOURCE OF TRUTH ──────────────────────
#
# Every raw pgvector query MUST build its distance/similarity term with these
# helpers, and MUST format the query vector with vector_literal(). This exists
# because the same two mistakes kept recurring across copy-pasted queries:
#
#   1. Writing `embedding <=> :q::vector` inline. SQLAlchemy's text() bind parser
#      does NOT recognise a bind (`:q`) immediately followed by `::`, so the
#      literal `:q` leaks to Postgres → "syntax error at or near ':'". The
#      CAST(:q AS vector) form binds correctly. (Verified on SQLAlchemy 2.0.x.)
#   2. Calling the async embed_text() without await in a sync code path, which
#      silently produces an un-awaited coroutine used as data. Sync code MUST use
#      embed_text_sync(); async code uses `await embed_text()`.
#
# Keep these the only place that knows the cast syntax — fix once, fixed forever.

def embed_text_sync(text: str) -> list[float]:
    """Synchronous BGE-M3 embedding for non-async code paths (routers/helpers
    that are plain `def`). Async paths should use `await embed_text()` instead,
    which offloads to a worker thread."""
    return get_bge().encode(text, normalize_embeddings=True).tolist()


def vector_literal(embedding) -> str:
    """Format an embedding as a pgvector text literal: '[0.1,0.2,...]'.
    Bind this string as the query parameter used by vector_distance()."""
    return "[" + ",".join(str(float(v)) for v in embedding) + "]"


def vector_distance(column: str, param: str = "q") -> str:
    """Canonical pgvector cosine-DISTANCE SQL fragment (smaller = closer).
    Use in WHERE/ORDER BY. Never write `:param::vector` by hand — see the
    module comment above for why that breaks."""
    return f"{column} <=> CAST(:{param} AS vector)"


def vector_similarity(column: str, param: str = "q") -> str:
    """Canonical pgvector cosine-SIMILARITY SQL fragment (1 - distance; larger =
    closer). Use in SELECT. See vector_distance() for the cast rationale."""
    return f"1 - ({vector_distance(column, param)})"


# ── Core inference primitives ─────────────────────────────────────────────────

async def _complete(
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 512,
    response_format: Optional[dict] = None,
) -> str:
    """
    Non-streaming completion. Use for structured JSON outputs.

    response_format — optional OpenAI-style hint passed straight to vLLM, e.g.
    ``{"type": "json_object"}`` to enable guided JSON decoding so the model is
    constrained to emit syntactically valid JSON. This is the robust way to get
    parseable JSON instead of relying solely on best-effort text repair.

    Raises AIServiceUnavailableError on connection errors or vLLM 5xx responses.
    """
    text, _finish_reason = await _complete_ex(
        system, user, temperature=temperature, max_tokens=max_tokens,
        response_format=response_format,
    )
    return text


async def _complete_ex(
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 512,
    response_format: Optional[dict] = None,
) -> tuple[str, Optional[str]]:
    """
    Same as _complete(), but also returns vLLM's ``finish_reason``.

    ``finish_reason == "length"`` means generation stopped because it hit
    max_tokens — the output is truncated and any JSON in it is incomplete.
    Callers that parse structured output need this to tell a truncated
    generation apart from a model that simply produced malformed JSON: the
    first is a budget problem with a clear remedy, the second is not.

    _complete() delegates here, so every existing call site is unaffected.
    """
    kwargs: dict = {}
    if response_format is not None:
        kwargs["response_format"] = response_format
    try:
        resp = await get_vllm_client().chat.completions.create(
            model=settings.vllm_model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **kwargs,
        )
        return resp.choices[0].message.content.strip(), resp.choices[0].finish_reason
    except APIConnectionError as exc:
        logger.warning("[ai_service] vLLM connection error: %s", exc)
        raise AIServiceUnavailableError() from exc
    except APIStatusError as exc:
        if exc.status_code in (429, 500, 502, 503, 504):
            logger.warning("[ai_service] vLLM status %d: %s", exc.status_code, exc)
            raise AIServiceUnavailableError() from exc
        raise


# ── Degraded-output contract (task 3.4) ───────────────────────────────────────
#
# Structured AI features used to do one of two things when the model returned a
# shape they did not expect, and both lied to the author:
#
#   hard-fail      — raise, discarding findings that DID parse (plot holes)
#   silent-fallback— return [] as if the manuscript were clean (continuity)
#
# The contract replaces both: coerce what came back, salvage the entries that
# are usable, reprompt ONCE if nothing survived, and hand the caller the result
# plus an honest account of how degraded it is. Raising is reserved for the case
# where there is genuinely nothing to show.
#
# One implementation, reused by every structured call site, so task 3.5's audit
# has a single thing to point every remaining hard-fail at.

_STRICTER_JSON_RETRY = (
    "\n\nIMPORTANT: your previous response could not be parsed. "
    "Return ONLY the JSON structure described above — no prose, no explanation, "
    "no markdown fences, nothing before or after the JSON."
)


@dataclass(frozen=True)
class DegradedMeta:
    """How much to trust a structured result. ``reason`` is author-facing."""
    degraded:  bool
    reason:    Optional[str] = None
    attempts:  int = 1
    discarded: int = 0


# ── Parser observability (task 3.5) ───────────────────────────────────────────
#
# Counters per feature, so degradation is measurable in production rather than
# inferred from complaints: how often output parses cleanly, how often entries
# have to be salvaged, how often a reprompt is needed, how often both attempts
# fail. A rising salvage rate on one feature is the early warning that its
# prompt or its model has drifted.
#
# METADATA ONLY. Model output is never counted, quoted or logged here — it is
# derived from the author's manuscript, and a log line is the easiest place for
# manuscript text to leak out of the system. Lengths and outcomes only.

PARSE_CLEAN      = "clean"        # parsed first time, nothing discarded
PARSE_SALVAGED   = "salvaged"     # usable result, some entries unreadable
PARSE_TRUNCATED  = "truncated"    # usable result, generation cut off
PARSE_REPROMPTED = "reprompted"   # needed the second attempt
PARSE_FAILED     = "failed"       # nothing usable after both attempts

_parse_metrics: dict[str, dict[str, int]] = {}


def _record_parse_metric(feature: str, outcome: str, *, attempts: int, discarded: int) -> None:
    """Count one structured-parse result and emit a machine-readable log line."""
    bucket = _parse_metrics.setdefault(
        feature,
        {PARSE_CLEAN: 0, PARSE_SALVAGED: 0, PARSE_TRUNCATED: 0,
         PARSE_REPROMPTED: 0, PARSE_FAILED: 0, "calls": 0, "entries_discarded": 0},
    )
    bucket["calls"] += 1
    bucket[outcome] = bucket.get(outcome, 0) + 1
    bucket["entries_discarded"] += discarded

    log = logger.warning if outcome in (PARSE_FAILED, PARSE_REPROMPTED) else logger.info
    log("[ai_service] parse_metric feature=%s outcome=%s attempts=%d discarded=%d calls=%d",
        feature, outcome, attempts, discarded, bucket["calls"])


def parser_metrics() -> dict[str, dict[str, int]]:
    """Snapshot of parse outcomes per feature. Counters only — no content."""
    return {feature: dict(counts) for feature, counts in _parse_metrics.items()}


async def complete_structured(
    system: str,
    user: str,
    *,
    coerce,
    temperature: float = 0.0,
    max_tokens: int = 800,
    label: str = "structured",
) -> tuple[Any, DegradedMeta]:
    """
    Run a structured generation under the degraded-output contract.

    ``coerce(parsed) -> (value, discarded)`` accepts whatever ``_extract_json``
    produced and returns the usable value (or ``None`` if nothing is usable)
    plus how many entries it had to throw away. Feature-specific shape knowledge
    lives there; this function owns only the policy.

    Returns ``(value, meta)``. ``value`` is ``None`` only when both attempts
    produced nothing usable — the caller decides whether that is an error.

    Exactly one reprompt. Two attempts is a structural maximum, not a tuning
    knob: a model that cannot produce the shape twice will not produce it on the
    fifth try, and the author is waiting.
    """
    raw, finish_reason = await _complete_ex(system, user, temperature=temperature,
                                            max_tokens=max_tokens)
    value, discarded = coerce(_extract_json(raw, None))
    truncated = finish_reason == "length"

    if value is not None:
        if discarded or truncated:
            reason = _degraded_reason(discarded, truncated)
            _record_parse_metric(label, PARSE_TRUNCATED if truncated else PARSE_SALVAGED,
                                 attempts=1, discarded=discarded)
            return value, DegradedMeta(True, reason, 1, discarded)
        _record_parse_metric(label, PARSE_CLEAN, attempts=1, discarded=0)
        return value, DegradedMeta(False, None, 1, 0)

    # Nothing usable — one stricter retry before giving up.
    # Length and finish_reason only: the response is derived from the author's
    # manuscript and must not be written to a log.
    logger.warning("[ai_service] %s unparseable (finish_reason=%s, chars=%d), retrying once",
                   label, finish_reason, len(raw or ""))
    raw2, finish_reason2 = await _complete_ex(system + _STRICTER_JSON_RETRY, user,
                                              temperature=temperature, max_tokens=max_tokens)
    value, discarded = coerce(_extract_json(raw2, None))
    truncated = finish_reason2 == "length"

    if value is None:
        logger.warning("[ai_service] %s unparseable after retry (finish_reason=%s, chars=%d)",
                       label, finish_reason2, len(raw2 or ""))
        _record_parse_metric(label, PARSE_FAILED, attempts=2, discarded=0)
        return None, DegradedMeta(
            True,
            "The AI response could not be read, even after a retry. Please try again.",
            2, 0,
        )

    _record_parse_metric(label, PARSE_REPROMPTED, attempts=2, discarded=discarded)
    return value, DegradedMeta(
        True, _degraded_reason(discarded, truncated, retried=True), 2, discarded,
    )


def _degraded_reason(discarded: int, truncated: bool, retried: bool = False) -> str:
    """Author-facing explanation. Plain language, no internals."""
    parts = []
    if truncated:
        parts.append("the AI response was cut off before it finished")
    if discarded:
        parts.append(f"{discarded} result{'s' if discarded > 1 else ''} could not be read")
    if retried and not parts:
        parts.append("the AI needed a second attempt")
    detail = " and ".join(parts) if parts else "some results could not be read"
    return f"These results are incomplete — {detail}."


async def _complete_json(
    system: str,
    user: str,
    fallback,
    temperature: float = 0.0,
    max_tokens: int = 800,
):
    """
    Completion that must return JSON, hardened in two layers:

      1. Ask vLLM for guided JSON output (``response_format={"type":"json_object"}``)
         so the model is constrained to emit syntactically valid JSON. This alone
         eliminates the most common malformations (e.g. partially-quoted array
         items like ``"Title" by Author`` that balance braces but fail to parse).
      2. Parse with the tolerant ``_extract_json`` repair pass as defence-in-depth.

    If the running vLLM build rejects ``response_format`` (older builds), we fall
    back to a plain completion + ``_extract_json`` so the feature never hard-fails
    purely because of the structured-output hint.

    Returns the parsed object, or ``fallback`` when every layer fails. Never
    raises for malformed content (only AIServiceUnavailableError propagates).
    """
    try:
        raw = await _complete(system, user, temperature=temperature,
                              max_tokens=max_tokens,
                              response_format={"type": "json_object"})
    except APIStatusError as exc:
        # response_format unsupported on this build → retry without it.
        if exc.status_code == 400:
            logger.info("[ai_service] guided JSON unsupported (400) — retrying plain")
            raw = await _complete(system, user, temperature=temperature, max_tokens=max_tokens)
        else:
            raise
    except TypeError:
        # Very old openai client without response_format kwarg.
        raw = await _complete(system, user, temperature=temperature, max_tokens=max_tokens)

    return _extract_json(raw, fallback), raw


async def _stream_generate(
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 800,
) -> AsyncGenerator[str, None]:
    """
    Streaming completion. Yields token strings as vLLM produces them.
    Raises AIServiceUnavailableError on connection errors before streaming starts.
    """
    try:
        stream = await get_vllm_client().chat.completions.create(
            model=settings.vllm_model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
    except APIConnectionError as exc:
        logger.warning("[ai_service] vLLM stream connection error: %s", exc)
        raise AIServiceUnavailableError() from exc
    except APIStatusError as exc:
        if exc.status_code in (429, 500, 502, 503, 504):
            logger.warning("[ai_service] vLLM stream status %d: %s", exc.status_code, exc)
            raise AIServiceUnavailableError() from exc
        raise

    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token


def _strip_code_fences(text: str) -> str:
    """Remove a leading ```json / ``` fence and its closing ``` if present."""
    t = text.strip()
    if t.startswith("```"):
        # Drop the opening fence line (``` or ```json) and the trailing fence.
        t = re.sub(r'^```[a-zA-Z0-9_-]*\s*\n?', '', t)
        t = re.sub(r'\n?```\s*$', '', t)
    return t.strip()


def _balanced_json_spans(text: str) -> list[str]:
    """
    Return every top-level balanced {...} or [...] span in `text`, in order,
    using a depth counter that is aware of string literals and escapes. Far more
    robust than a greedy regex, which over-matches when the model emits prose or
    multiple JSON objects. Returning all spans lets the caller skip a stray
    {placeholder} in surrounding prose and still find the real JSON.
    """
    spans: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "{[":
            open_ch, close_ch = ch, ("}" if ch == "{" else "]")
            depth = 0
            in_str = False
            escape = False
            j = i
            while j < n:
                c = text[j]
                if in_str:
                    if escape:
                        escape = False
                    elif c == "\\":
                        escape = True
                    elif c == '"':
                        in_str = False
                elif c == '"':
                    in_str = True
                elif c == open_ch:
                    depth += 1
                elif c == close_ch:
                    depth -= 1
                    if depth == 0:
                        spans.append(text[i:j + 1])
                        break
                j += 1
            i = j + 1
        else:
            i += 1
    return spans


def _extract_json(text: str, fallback):
    """
    Robustly extract a JSON object/array from an LLM response.

    Handles, in order:
      1. clean JSON                          → direct parse
      2. ```json fenced ``` blocks           → fence strip + parse
      3. JSON embedded in surrounding prose  → balanced-brace span + parse
      4. trailing commas (a common LLM tic)  → strip + retry

    Returns `fallback` only when every strategy fails, and logs the raw head of
    the response so failures are diagnosable instead of silent.
    """
    if not text or not text.strip():
        logger.debug("[ai_service] empty model response — using fallback")
        return fallback

    candidates: list[str] = []
    stripped = _strip_code_fences(text)
    candidates.append(stripped)
    # Try every balanced span (over stripped text, then raw) so a stray
    # {placeholder} in prose doesn't block the real JSON object/array.
    for span in _balanced_json_spans(stripped) + _balanced_json_spans(text):
        if span not in candidates:
            candidates.append(span)

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            # Retry after removing trailing commas: {"a":1,}  /  [1,2,]
            repaired = re.sub(r',\s*([}\]])', r'\1', cand)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                continue

    # Metadata only — model output is derived from the author's manuscript and
    # must never be written to a log (task 3.5).
    logger.warning("[ai_service] failed to parse model output as JSON (chars=%d)", len(text or ""))
    return fallback


def _close_unterminated_json_array(text: str) -> Optional[list]:
    """
    Recover the ONE observed malformation: a complete JSON array whose final
    ``]`` is missing.

    Deliberately not a JSON repair engine. Every condition below must hold or
    this returns None and the caller falls through to a regeneration:

      * the payload starts with ``[``           — it is an array, not prose
      * it does NOT already end with ``]``      — otherwise there is nothing to fix
      * it ends with ``}``                      — the last element is complete;
                                                  a payload cut mid-object is a
                                                  different failure and is not
                                                  guessed at here
      * appending exactly one ``]`` makes it parse, and yields a list

    The only mutation is appending the missing terminator. No content is
    altered, no quotes balanced, no commas inserted, nothing truncated.

    Why this exists: Qwen intermittently ends a well-formed suggestion array
    without its closing bracket while reporting finish_reason="stop", roughly
    1000 tokens below the cap — measured at ~11% of long continuations. The
    alternative recovery is a full regeneration costing ~50s, which on this
    single-GPU deployment pushes a request close to the proxy timeout. This
    check costs microseconds and handles the case exactly.
    """
    stripped = _strip_code_fences(text).strip()
    if not stripped.startswith("[") or stripped.endswith("]") or not stripped.endswith("}"):
        return None
    try:
        parsed = json.loads(stripped + "]")
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _strip_html(html: str) -> str:
    """Remove HTML tags, collapse to single line — for summary generation."""
    text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()


def _html_to_plain(html: str) -> str:
    """
    Convert TipTap HTML to plain text preserving paragraph structure.
    </p> and <br> become newlines so paragraph-aware chunking can split correctly.
    Used for chunk generation — NOT for summary generation.
    """
    text = re.sub(r'</p>|<br\s*/?>|</h[1-6]>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in text.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def _chunk_text(text: str, target_words: int = 350, overlap_paras: int = 2) -> list[str]:
    """
    Split plain text (with newline-separated paragraphs) into overlapping chunks
    of approximately target_words words each.

    Splits at paragraph boundaries so chunks don't break mid-sentence.
    overlap_paras trailing paragraphs from the previous chunk carry into the next
    to preserve context across boundaries.

    target_words=350 keeps each chunk well under BGE-M3's optimal 512-token range.

    Scales automatically:
      3-chapter draft  →  ~8 chunks
      60-chapter novel →  ~580 chunks   (all embedded; cosine search in <100 ms)
      200k-word novel  →  ~570 chunks
    """
    paras = [p.strip() for p in text.split('\n') if p.strip()]
    if not paras:
        return [text.strip()] if text.strip() else []

    chunks: list[str] = []
    buf:    list[str] = []
    buf_wc: int       = 0

    for para in paras:
        para_wc = len(para.split())

        if buf_wc + para_wc > target_words and buf:
            chunks.append('\n'.join(buf))
            # carry last N paragraphs into next chunk for continuity
            buf    = buf[-overlap_paras:]
            buf_wc = sum(len(p.split()) for p in buf)

        buf.append(para)
        buf_wc += para_wc

    if buf:
        chunks.append('\n'.join(buf))

    return chunks or [text.strip()]


# ── Warmup (called at FastAPI startup) ───────────────────────────────────────

async def warmup():
    """
    Send a minimal request to vLLM so the model is hot in KV cache
    before the first real user request arrives.
    """
    get_bge()   # load BGE-M3 into memory
    await _complete("You are ready.", "Reply OK.", temperature=0.0, max_tokens=5)


# ── Genre Detection ───────────────────────────────────────────────────────────

async def detect_genre(description: str, audience_hint: Optional[str] = None) -> dict:
    """
    Quick Story Intelligence analysis from a story description, run at intake
    time before any chapters exist.

    Returns the original base fields (genre, sub_genre, tone, audience, structure,
    conflict, themes, writing_direction, confidence) for backwards compatibility,
    PLUS richer intelligence fields:
      secondary_genres   — other genres the story blends in (string array)
      comparable_titles  — comp titles for positioning (string array)
      marketing_category — bookstore/marketing shelf (string)
      emotional_arc      — the intended emotional journey (string)
      narrative_pov      — likely point of view / tense (string)
      pacing             — pacing expectation (string)
      content_warnings   — sensitive content flags (string array)
      intelligence_notes — 1-2 sentence craft-level direction (string)

    Unknown fields come back as "" or [] — never invented.
    """
    audience = audience_hint or "Adult"
    system = (
        "You are a senior literary analyst and acquiring editor. Analyse the story description "
        "and produce a rich genre & story-intelligence profile.\n\n"
        "Return ONLY a valid JSON object with these exact keys:\n"
        '  "genre": primary genre (string)\n'
        '  "sub_genre": most specific sub-genre (string)\n'
        '  "tone": dominant tones (array of strings)\n'
        '  "audience": target audience (string)\n'
        '  "structure": suggested narrative structure (string)\n'
        '  "conflict": the core emotional/dramatic direction (string)\n'
        '  "themes": thematic hints (array of strings)\n'
        '  "writing_direction": craft guidance for the author (string)\n'
        '  "secondary_genres": other genres the story blends (array of strings; [] if none)\n'
        '  "comparable_titles": 2-4 comparable published titles (array of strings; [] if unsure)\n'
        '  "marketing_category": the shelf/marketing category (string)\n'
        '  "emotional_arc": the intended emotional journey for the reader (string)\n'
        '  "narrative_pov": likely point of view and tense, e.g. "Third-person past" (string)\n'
        '  "pacing": pacing expectation, e.g. "Slow-burn", "Fast-paced" (string)\n'
        '  "content_warnings": sensitive-content flags (array of strings; [] if none)\n'
        '  "intelligence_notes": 1-2 sentences of distinctive craft-level direction (string)\n'
        '  "confidence": overall confidence (float 0-1)\n\n'
        "Rules:\n"
        "- Base every field on the description. Do NOT fabricate comp titles or warnings; "
        'use [] or "" when genuinely unsure.\n'
        "- Every array element MUST be exactly ONE complete double-quoted JSON string "
        'with no unquoted text. For comparable_titles, write each as a single string '
        'like "Title by Author" — never put the author outside the quotes.\n'
        "- Output ONLY the JSON object — no markdown fences, no prose."
    )
    result, raw = await _complete_json(
        system,
        f"Description: {description}\nAudience: {audience}",
        fallback=None,
        max_tokens=800,
    )
    if result is None or not isinstance(result, dict):
        logger.warning("[ai_service] detect_genre invalid JSON (chars=%d)", len(raw or ""))
        raise ValueError(
            "Genre detection failed: the AI model returned invalid output. "
            "Please try again."
        )

    # Normalise so downstream code and the response schema always see safe types.
    def _str(key: str) -> str:
        v = result.get(key, "")
        return str(v).strip() if v is not None else ""

    def _list(key: str) -> list:
        v = result.get(key, [])
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    try:
        confidence = float(result.get("confidence", 0.85))
    except (TypeError, ValueError):
        confidence = 0.85

    return {
        "genre":              _str("genre"),
        "sub_genre":          _str("sub_genre"),
        "tone":               _list("tone"),
        "audience":           _str("audience") or audience,
        "structure":          _str("structure"),
        "conflict":           _str("conflict"),
        "themes":             _list("themes"),
        "writing_direction":  _str("writing_direction"),
        "secondary_genres":   _list("secondary_genres"),
        "comparable_titles":  _list("comparable_titles"),
        "marketing_category": _str("marketing_category"),
        "emotional_arc":      _str("emotional_arc"),
        "narrative_pov":      _str("narrative_pov"),
        "pacing":             _str("pacing"),
        "content_warnings":   _list("content_warnings"),
        "intelligence_notes": _str("intelligence_notes"),
        "confidence":         max(0.0, min(1.0, confidence)),
    }


# ── Text Refinement ───────────────────────────────────────────────────────────

_REFINE_MODE = {
    "standard":  "general prose quality and clarity",
    "literary":  "literary richness, voice, and imagery",
    "grammar":   "grammar, punctuation, and sentence structure only",
    "dialogue":  "natural-sounding dialogue and speech rhythm",
}


async def refine_text(text: str, mode: str = "standard", context: str = "", genre_context: str = "") -> str:
    desc = _REFINE_MODE.get(mode, "general prose quality")
    system = _with_genre(
        f"You are a professional fiction editor specialising in {desc}. "
        "Improve the text while preserving the author's voice. Return ONLY the improved text.",
        genre_context,
    )
    ctx = f"\n\nManuscript context:\n{context}" if context else ""
    return await _complete(system, text + ctx, temperature=0.3, max_tokens=len(text.split()) * 2 + 150)


async def stream_refine(text: str, mode: str = "standard", context: str = "", genre_context: str = "") -> AsyncGenerator[str, None]:
    desc = _REFINE_MODE.get(mode, "general prose quality")
    system = _with_genre(
        f"You are a professional fiction editor specialising in {desc}. "
        "Improve the text while preserving the author's voice. Return ONLY the improved text.",
        genre_context,
    )
    ctx = f"\n\nManuscript context:\n{context}" if context else ""
    async for token in _stream_generate(system, text + ctx, temperature=0.3, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Tone Transformation ────────────────────────────────────────────────────────

def _with_genre(system: str, genre_context: str) -> str:
    """Prepend the story's genre profile to a system prompt when available."""
    return f"{genre_context}\n\n{system}" if genre_context else system


async def transform_tone(text: str, tone: str, context: str = "", genre_context: str = "") -> str:
    system = _with_genre(
        f"You are a literary writing coach. Rewrite the passage in a {tone} tone. "
        "Keep all events and characters identical — only change style, word choice, and mood. "
        "Return ONLY the rewritten passage.",
        genre_context,
    )
    ctx = f"\n\nStory context:\n{context}" if context else ""
    return await _complete(system, text + ctx, temperature=0.5, max_tokens=len(text.split()) * 2 + 150)


async def stream_tone(text: str, tone: str, context: str = "", genre_context: str = "") -> AsyncGenerator[str, None]:
    system = _with_genre(
        f"You are a literary writing coach. Rewrite the passage in a {tone} tone. "
        "Keep all events and characters identical — only change style, word choice, and mood. "
        "Return ONLY the rewritten passage.",
        genre_context,
    )
    ctx = f"\n\nStory context:\n{context}" if context else ""
    async for token in _stream_generate(system, text + ctx, temperature=0.5, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Emotion Rewriting ─────────────────────────────────────────────────────────

async def rewrite_emotion(text: str, emotion: str, intensity: str = "medium", genre_context: str = "") -> str:
    system = _with_genre(
        f"You are a fiction editor. Rewrite the passage so it deeply conveys {emotion} at "
        f"{intensity} intensity using sensory detail and interiority — not emotional labels. "
        "Return ONLY the rewritten passage.",
        genre_context,
    )
    return await _complete(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150)


async def stream_emotion(text: str, emotion: str, intensity: str = "medium", genre_context: str = "") -> AsyncGenerator[str, None]:
    system = _with_genre(
        f"You are a fiction editor. Rewrite the passage so it deeply conveys {emotion} at "
        f"{intensity} intensity using sensory detail and interiority — not emotional labels. "
        "Return ONLY the rewritten passage.",
        genre_context,
    )
    async for token in _stream_generate(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Age Adaptation ─────────────────────────────────────────────────────────────

_AGE_GUIDE = {
    "children": "children aged 5–10 — simple vocabulary, short sentences, no violence or adult themes",
    "ya":       "young adult readers aged 10–18 — age-appropriate complexity and themes",
    "adult":    "adult readers — full vocabulary and thematic depth",
}


async def adapt_for_age(text: str, target_age: str, context: str = "", genre_context: str = "") -> str:
    guide = _AGE_GUIDE.get(target_age, _AGE_GUIDE["adult"])
    system = _with_genre(
        f"You are an editor. Adapt the text for {guide}. "
        "Preserve the story meaning. Return ONLY the adapted text.",
        genre_context,
    )
    ctx = f"\n\nContext:\n{context}" if context else ""
    return await _complete(system, text + ctx, temperature=0.3, max_tokens=len(text.split()) * 2 + 150)


async def stream_age_adapt(text: str, target_age: str, context: str = "", genre_context: str = "") -> AsyncGenerator[str, None]:
    guide = _AGE_GUIDE.get(target_age, _AGE_GUIDE["adult"])
    system = _with_genre(
        f"You are an editor. Adapt the text for {guide}. "
        "Preserve the story meaning. Return ONLY the adapted text.",
        genre_context,
    )
    ctx = f"\n\nContext:\n{context}" if context else ""
    async for token in _stream_generate(system, text + ctx, temperature=0.3, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Style Transformation ───────────────────────────────────────────────────────

async def transform_style(text: str, style: str, genre_context: str = "") -> str:
    system = _with_genre(
        f"Rewrite the passage in the literary style of {style} — capturing their characteristic "
        "sentence structure, diction, rhythm, and voice. Return ONLY the rewritten passage.",
        genre_context,
    )
    return await _complete(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150)


async def stream_style(text: str, style: str, genre_context: str = "") -> AsyncGenerator[str, None]:
    system = _with_genre(
        f"Rewrite the passage in the literary style of {style} — capturing their characteristic "
        "sentence structure, diction, rhythm, and voice. Return ONLY the rewritten passage.",
        genre_context,
    )
    async for token in _stream_generate(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Author-Inspired Style Rewrite ──────────────────────────────────────────────
#
# This module is the SAFETY AUTHORITY for the author-style feature. The frontend
# list is convenience only; what is actually allowed is decided here.
#
#   * Named authors are offered ONLY when their work is firmly public domain.
#   * Generic style categories are always safe.
#   * Authors whose work is NOT uniformly public domain (or who are/were modern)
#     are mapped to a SAFE GENERIC DESCRIPTOR rather than to "imitate <author>",
#     so users get the stylistic intent without copyright/style-infringement risk.
#   * Unknown / arbitrary author strings degrade to a generic literary influence —
#     they are NEVER passed verbatim into an "imitate X" instruction.

# key -> (label, descriptor used in the prompt, public_domain, group)
_AUTHOR_STYLES: dict[str, dict] = {
    # ── Public-domain authors (named influence permitted) ──────────────────────
    "shakespeare":   {"label": "William Shakespeare", "descriptor": "William Shakespeare — Elizabethan dramatic cadence, rich metaphor, blank-verse rhythm and heightened poetic diction", "public_domain": True,  "group": "public_domain"},
    "austen":        {"label": "Jane Austen",          "descriptor": "Jane Austen — witty free-indirect discourse, balanced ironic sentences and drawing-room social observation", "public_domain": True,  "group": "public_domain"},
    "dickens":       {"label": "Charles Dickens",      "descriptor": "Charles Dickens — vivid characterful description, long cumulative sentences, social texture and warm comic detail", "public_domain": True,  "group": "public_domain"},
    "poe":           {"label": "Edgar Allan Poe",      "descriptor": "Edgar Allan Poe — gothic dread, first-person psychological intensity, ornate vocabulary and mounting unease", "public_domain": True,  "group": "public_domain"},
    "bronte":        {"label": "The Brontës",          "descriptor": "the Brontës — passionate Romantic interiority, moody landscape imagery and intense emotional sincerity", "public_domain": True,  "group": "public_domain"},
    "twain":         {"label": "Mark Twain",           "descriptor": "Mark Twain — plain-spoken vernacular voice, dry humor and shrewd colloquial rhythm", "public_domain": True,  "group": "public_domain"},
    # ── Generic style categories (always safe) ─────────────────────────────────
    "generic_poetic":    {"label": "Generic poetic",    "descriptor": "a lyrical poetic style — musical rhythm, vivid imagery and figurative language", "public_domain": True, "group": "generic"},
    "generic_cinematic": {"label": "Generic cinematic", "descriptor": "a cinematic style — present, visual scene-setting, sharp sensory beats and momentum", "public_domain": True, "group": "generic"},
    "generic_literary":  {"label": "Generic literary",  "descriptor": "an elevated literary-fiction style — layered introspection, precise diction and controlled rhythm", "public_domain": True, "group": "generic"},
    "generic_minimalist":{"label": "Spare / minimalist","descriptor": "a spare, understated minimalist style — short declarative sentences, restraint and subtext (in the tradition of plain modern prose)", "public_domain": True, "group": "generic"},
    "generic_stream":    {"label": "Stream of consciousness", "descriptor": "a stream-of-consciousness literary style — fluid interior monologue, associative rhythm and shifting perception", "public_domain": True, "group": "generic"},
    "generic_mystery":   {"label": "Classic mystery",   "descriptor": "a classic whodunit mystery style — measured clue-laying, controlled suspense and crisp deductive narration", "public_domain": True, "group": "generic"},
}

# Modern / living or not-uniformly-public-domain authors requested by users are
# redirected to a SAFE generic descriptor (no named imitation of in-copyright work).
_AUTHOR_ALIASES: dict[str, str] = {
    "hemingway":         "generic_minimalist",
    "ernest hemingway":  "generic_minimalist",
    "woolf":             "generic_stream",
    "virginia woolf":    "generic_stream",
    "christie":          "generic_mystery",
    "agatha christie":   "generic_mystery",
}

_GENERIC_FALLBACK_KEY = "generic_literary"

_AUTHOR_SAFETY_CLAUSE = (
    "Produce ORIGINAL prose that is merely INSPIRED BY this style. "
    "Preserve the original meaning, plot, characters, dialogue intent and events exactly. "
    "Do NOT reproduce, quote, or closely imitate any copyrighted text or any specific "
    "published passage; influence the rhythm, diction and mood only. "
    "Return ONLY the rewritten passage."
)


def _resolve_author_style(author: str) -> dict:
    """Resolve a requested author into a safe {key, label, descriptor, public_domain}.

    Order: exact catalog key → alias redirect → generic literary fallback.
    Guarantees the descriptor is always copyright-safe.
    """
    key = (author or "").strip().lower().replace(" ", "_")
    if key in _AUTHOR_STYLES:
        entry = _AUTHOR_STYLES[key]
        return {"key": key, **entry}
    raw = (author or "").strip().lower()
    if raw in _AUTHOR_ALIASES:
        alias_key = _AUTHOR_ALIASES[raw]
        return {"key": alias_key, **_AUTHOR_STYLES[alias_key]}
    fb = _AUTHOR_STYLES[_GENERIC_FALLBACK_KEY]
    return {"key": _GENERIC_FALLBACK_KEY, **fb}


def author_style_catalog() -> list[dict]:
    """Return the public catalog of selectable author/style options (server-authoritative)."""
    return [
        {"id": key, "label": e["label"], "description": e["descriptor"],
         "public_domain": e["public_domain"], "group": e["group"]}
        for key, e in _AUTHOR_STYLES.items()
    ]


def _author_style_system(author: str, genre_context: str) -> str:
    resolved = _resolve_author_style(author)
    return _with_genre(
        "You are a literary writing coach. Rewrite the passage so it is influenced by "
        f"the style of {resolved['descriptor']}. {_AUTHOR_SAFETY_CLAUSE}",
        genre_context,
    )


async def rewrite_in_author_style(text: str, author: str, genre_context: str = "") -> str:
    system = _author_style_system(author, genre_context)
    return await _complete(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150)


async def stream_author_style(text: str, author: str, genre_context: str = "") -> AsyncGenerator[str, None]:
    system = _author_style_system(author, genre_context)
    async for token in _stream_generate(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Translation ────────────────────────────────────────────────────────────────

async def translate_text(text: str, target_language: str, source_language: str = "en") -> str:
    system = (
        f"You are a professional literary translator. Translate from {source_language} to "
        f"{target_language}, preserving tone, style, and literary quality. Return ONLY the translation."
    )
    return await _complete(system, text, temperature=0.2, max_tokens=len(text.split()) * 3 + 200)


async def stream_translate(text: str, target_language: str, source_language: str = "en") -> AsyncGenerator[str, None]:
    system = (
        f"You are a professional literary translator. Translate from {source_language} to "
        f"{target_language}, preserving tone, style, and literary quality. Return ONLY the translation."
    )
    async for token in _stream_generate(system, text, temperature=0.2, max_tokens=len(text.split()) * 3 + 200):
        yield token


# ── Cast Extraction ────────────────────────────────────────────────────────────

_CAST_SYSTEM = (
    'You are a literary analyst building a character bible from a manuscript.\n'
    'Extract every named character and every significant recurring person from the '
    'story text below, with as much grounded detail as the text supports.\n\n'
    'Return ONLY a valid JSON array. Each element must be an object with these exact keys:\n'
    '  "name": canonical full name (string)\n'
    '  "role": one of "protagonist", "antagonist", "supporting", "minor"\n'
    '  "status": one of "active", "deceased", "unknown"\n'
    '  "aliases": other names/nicknames/titles this character is called by (array of strings; [] if none)\n'
    '  "description": 1-2 sentence summary of who this character is (string)\n'
    '  "age": age or life-stage if stated or strongly implied, else "" (string, e.g. "early 30s", "teenager")\n'
    '  "appearance": physical description grounded in the text, else "" (string)\n'
    '  "personality": personality/temperament grounded in behaviour and dialogue, else "" (string)\n'
    '  "goals": what the character is actively trying to achieve, else "" (string)\n'
    '  "motivations": why they pursue those goals — their drives/fears, else "" (string)\n'
    '  "backstory": established history/origin revealed in the text, else "" (string)\n'
    '  "arc_notes": how the character changes or what unfolds across chapters, else "" (string)\n'
    '  "traits": 3-8 personality adjectives drawn from the text (array of strings; [] if unclear)\n'
    '  "first_appearance": chapter where the character first appears (e.g. "Chapter 1")\n'
    '  "evidence_snippet": short quote or close paraphrase confirming this character (max 80 words)\n'
    '  "confidence": "high" if clearly named and present; "uncertain" if inferred or ambiguous\n\n'
    'Rules:\n'
    '- Include named individuals AND named groups/collectives that act as characters.\n'
    '- Include unnamed but significant recurring characters by their role (e.g. "Ravi\'s Mother").\n'
    '- Extract ALL evidence available — fill appearance/personality/goals/motivations/backstory '
    'whenever the text supports them. Do not leave a field empty if the text gives evidence for it.\n'
    '- Do NOT invent facts. If a field is genuinely not established in the text, use "" (or [] for arrays).\n'
    '- Do NOT invent characters absent from the text.\n'
    '- Return [] if no characters are found.\n'
    '- Output ONLY the JSON array — no preamble, no markdown fences, no trailing prose.'
)

_CAST_COMPLETION_TOKENS = 1500   # headroom for the JSON array of one window
_ROLE_PRIORITY   = {"protagonist": 3, "antagonist": 2, "supporting": 1, "minor": 0}
_STATUS_PRIORITY = {"deceased": 2, "active": 1, "unknown": 0}

# Honorifics/titles stripped before matching name variants across windows so
# "Captain Mara Halloran", "Captain Mara" and "Mara" collapse to one character.
_NAME_TITLES = frozenset({
    "captain", "capt", "dr", "mr", "mrs", "ms", "miss", "sir", "lord", "lady",
    "master", "mistress", "prof", "professor", "father", "sister", "brother",
    "king", "queen", "prince", "princess", "general", "colonel", "major",
    "sergeant", "admiral", "commander", "lieutenant", "uncle", "aunt",
})


def _name_tokens(name: str) -> frozenset:
    """Lowercased significant name tokens with titles/punctuation removed."""
    toks = [t.strip(".,'\"-").lower() for t in str(name).split()]
    return frozenset(t for t in toks if t and t not in _NAME_TITLES)


_qwen_tokenizer = None
_qwen_tokenizer_unavailable = False


def count_tokens(text: str) -> int:
    """
    Count tokens the way the serving model counts them.

    Uses the real Qwen tokenizer, already on disk beside the weights — no new
    dependency and no download. Exists because context budgets built on
    character counts are guesses: prose, names and markup tokenise at very
    different rates, and a budget that is wrong in the optimistic direction
    shows up as a vLLM 400 (context length exceeded) mid-generation.

    Falls back to a deliberately PESSIMISTIC estimate if the tokenizer cannot
    be loaded — over-estimating costs a little unused context, under-estimating
    costs a failed generation.
    """
    global _qwen_tokenizer, _qwen_tokenizer_unavailable
    if not text:
        return 0
    if _qwen_tokenizer is None and not _qwen_tokenizer_unavailable:
        try:
            from transformers import AutoTokenizer
            _qwen_tokenizer = AutoTokenizer.from_pretrained(
                settings.qwen_path, local_files_only=True,
            )
            logger.info("[ai_service] Qwen tokenizer loaded for context measurement")
        except Exception as exc:
            _qwen_tokenizer_unavailable = True
            logger.warning("[ai_service] Qwen tokenizer unavailable (%s) — "
                           "context budgets fall back to estimation", exc)
    if _qwen_tokenizer is not None:
        return len(_qwen_tokenizer.encode(text))
    # ~1.6 tokens/word is above the English average (~1.3); punctuation and
    # newlines are counted separately so structured context is not undercounted.
    return int(len(text.split()) * 1.6) + text.count("\n") + 8


def _cast_window_word_budget() -> int:
    """
    Words of story text per LLM pass, derived from the model context window so
    we never exceed it. Tokens ≈ 1.3×words for English; we divide by 1.5 for a
    safety margin (names/markup tokenise heavier). Reserves room for the system
    prompt and the JSON completion.
    """
    max_ctx = getattr(settings, "max_model_len", 8192) or 8192
    system_overhead = 1000  # system prompt + framing + safety margin
    input_token_budget = max_ctx - _CAST_COMPLETION_TOKENS - system_overhead
    words = int(input_token_budget / 1.5)
    return max(800, words)


def _build_cast_windows(chapter_texts: list, words_per_window: int) -> list[str]:
    """
    Pack chapter texts into windows of ~words_per_window words each, preserving
    chapter labels so the model can report first_appearance. A chapter larger
    than one window is split across windows (marked '(cont.)'). Small chapters
    are combined so we make as few passes as possible.
    """
    windows: list[str] = []
    cur_parts: list[str] = []
    cur_wc = 0

    for idx, text in enumerate(chapter_texts, 1):
        words = (text or "").split()
        if not words:
            continue
        pos = 0
        while pos < len(words):
            space = words_per_window - cur_wc
            if space <= 0:                       # current window full → flush
                windows.append("\n\n".join(cur_parts))
                cur_parts, cur_wc = [], 0
                space = words_per_window
            take = min(space, len(words) - pos)
            seg_words = words[pos:pos + take]
            label = f"=== Chapter {idx} ===" + ("" if pos == 0 else " (continued)")
            cur_parts.append(f"{label}\n{' '.join(seg_words)}")
            cur_wc += take
            pos += take

    if cur_parts:
        windows.append("\n\n".join(cur_parts))
    return windows


def _merge_cast(window_results: list[list]) -> list:
    """
    Merge per-window character lists into one deduplicated cast.

    Characters are keyed by canonical name (case-insensitive). For each repeated
    character, text fields take the richer (longer) non-empty value, aliases and
    traits are unioned, role/status take the more central/definite value, and
    confidence is "high" if any window was confident.
    """
    entries: list[dict] = []   # each: {..character.., "_tokens": frozenset}

    def _richer(a, b) -> str:
        a = (str(a).strip() if a is not None else "")
        b = (str(b).strip() if b is not None else "")
        return a if len(a) >= len(b) else b

    def _norm_list(v) -> list[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    def _find(tokens: frozenset, name: str):
        """Match an existing entry whose name is the same character: identical
        tokens, or one token-set is a subset of the other (e.g. {mara} vs
        {mara, halloran}). Empty token-sets fall back to exact name match."""
        if not tokens:
            return next((e for e in entries if e["name"].lower() == name.lower()), None)
        for e in entries:
            et = e["_tokens"]
            if et and (tokens <= et or et <= tokens):
                return e
        return None

    text_fields = ("description", "appearance", "personality", "goals",
                   "motivations", "backstory", "arc_notes", "age", "evidence_snippet")

    for lst in window_results:
        if not isinstance(lst, list):
            continue
        for ch in lst:
            if not isinstance(ch, dict):
                continue
            name = str(ch.get("name", "")).strip()
            if not name:
                continue
            tokens = _name_tokens(name)
            existing = _find(tokens, name)
            if existing is None:
                entries.append({
                    "name": name,
                    "role": ch.get("role", "supporting"),
                    "status": ch.get("status", "active"),
                    "aliases": _norm_list(ch.get("aliases")),
                    "traits": _norm_list(ch.get("traits")),
                    "first_appearance": str(ch.get("first_appearance", "")).strip(),
                    "confidence": ch.get("confidence", "high"),
                    "_tokens": tokens,
                    **{f: str(ch.get(f, "") or "").strip() for f in text_fields},
                })
            else:
                m = existing
                # Keep the most complete name as canonical; demote the other to alias.
                if len(tokens) > len(m["_tokens"]):
                    if m["name"].lower() != name.lower():
                        m["aliases"] = sorted(set(m["aliases"]) | {m["name"]})
                    m["name"], m["_tokens"] = name, tokens
                elif name.lower() != m["name"].lower():
                    m["aliases"] = sorted(set(m["aliases"]) | {name})
                for f in text_fields:
                    m[f] = _richer(m.get(f), ch.get(f))
                m["aliases"] = sorted((set(m["aliases"]) | set(_norm_list(ch.get("aliases")))) - {m["name"]})
                m["traits"] = sorted(set(m["traits"]) | set(_norm_list(ch.get("traits"))))
                if _ROLE_PRIORITY.get(ch.get("role", ""), -1) > _ROLE_PRIORITY.get(m["role"], -1):
                    m["role"] = ch.get("role")
                if _STATUS_PRIORITY.get(ch.get("status", ""), -1) > _STATUS_PRIORITY.get(m["status"], -1):
                    m["status"] = ch.get("status")
                if ch.get("confidence") == "high":
                    m["confidence"] = "high"

    for e in entries:
        e.pop("_tokens", None)
    return entries


async def extract_cast(chapter_texts: list) -> list:
    """
    Extract named characters and significant recurring persons from the WHOLE
    story, together with as much grounded profile detail as the text supports.

    The story is split into context-window-sized passes (so we never exceed the
    model's max context length), each pass is analysed concurrently, and the
    per-window results are merged per character. This lets long manuscripts
    (many chapters of several thousand words) be analysed in full.

    chapter_texts: list of plain-text strings, one per chapter (cleaned).
    Returns a list of dicts with keys: name, role, status, description, aliases,
    first_appearance, evidence_snippet, confidence, age, appearance, personality,
    goals, motivations, backstory, arc_notes, traits.

    Profile fields are extracted from evidence only. Unknown fields are returned
    as "" (or [] for traits) — never invented.
    """
    words_per_window = _cast_window_word_budget()
    windows = _build_cast_windows(chapter_texts, words_per_window)
    if not windows:
        logger.debug("[ai_service] extract_cast: no chapter text supplied")
        return []

    total_words = sum(len((t or "").split()) for t in chapter_texts)
    logger.info("[ai_service] extract_cast: analysing %d words across %d "
          f"window(s) of ~{words_per_window} words (model ctx="
          f"{getattr(settings, 'max_model_len', 8192)})")

    async def _run_window(i: int, body: str):
        try:
            raw = await _complete(
                _CAST_SYSTEM, f"Story text:\n\n{body}",
                temperature=0.1, max_tokens=_CAST_COMPLETION_TOKENS,
            )
        except Exception as exc:
            logger.warning("[ai_service] extract_cast window %d/%d LLM failed: %r", i+1, len(windows), exc)
            return exc  # surfaced below so we can distinguish "all failed"
        parsed = _extract_json(raw, None)
        if not isinstance(parsed, list):
            logger.warning("[ai_service] extract_cast window %d/%d non-array JSON (chars=%d)",
                           i + 1, len(windows), len(raw or ""))
            return None
        logger.debug("[ai_service] extract_cast window %d/%d → %d character(s)", i+1, len(windows), len(parsed))
        return parsed

    results = await asyncio.gather(*[_run_window(i, w) for i, w in enumerate(windows)])

    parsed_lists = [r for r in results if isinstance(r, list)]
    errors       = [r for r in results if isinstance(r, Exception)]

    if not parsed_lists:
        # Nothing usable came back. Distinguish transport failure from bad output
        # so the router can map it to the right status / message.
        if errors:
            raise errors[0]
        raise ValueError(
            "Cast generation failed: the AI model returned output that could not be "
            "parsed as JSON. Please try again."
        )

    cast = _merge_cast(parsed_lists)
    logger.info(
        "[ai_service] extract_cast merged into %d unique character(s) from %d/%d successful window(s)",
        len(cast), len(parsed_lists), len(windows),
    )
    return cast


# ── AI Suggestions ─────────────────────────────────────────────────────────────

async def generate_suggestions(text: str, story_context: str = "", genre: str = "") -> list:
    system = (
        "You are a literary coach giving manuscript feedback. Analyse the excerpt and return ONLY "
        "a JSON array of exactly 4 objects: {id: int, category: string, text: string, reason: string}. "
        "Categories: Prose Quality | Show Don't Tell | Dialogue | Pacing | Characterisation | Structure."
    )
    parts = []
    if genre:
        parts.append(f"Genre: {genre}")
    if story_context:
        parts.append(f"Story context: {story_context}")
    parts.append(f"Excerpt:\n{text}")
    result, meta = await complete_structured(
        system, "\n\n".join(parts),
        coerce=coerce_text_suggestions,
        temperature=0.0, max_tokens=600, label="writing_suggestions",
    )
    if result is None:
        raise ValueError(
            "Writing suggestions could not be generated. Please try again."
        )
    return result


# ── Plot Assistant — intent detection ─────────────────────────────────────────

async def detect_query_intent(question: str) -> str:
    """
    Classify the user's question into one of three modes using Qwen.

    Returns:
      "qa"         — factual/recall question about existing story content
                     (who, what, when, where, why, what happened, explain X)
      "creative"   — request for new ideas, plot development, creative help
                     (suggest, what should happen, plot twist, make X more Y)
      "mixed"      — contains both factual and creative elements
                     (who is X and how can I develop them further?)

    Falls back to "creative" if Qwen returns something unexpected.
    """
    system = (
        "You are a writing assistant classifier. Classify the writer's question into exactly one "
        "of three categories and return ONLY the single word, nothing else:\n\n"
        "  qa        — The writer is asking a FACTUAL question about their existing story content. "
        "Examples: 'Who is X?', 'What happened in chapter 2?', 'What is the coconut tree dispute?', "
        "'Why is Ravi chairman?', 'What are the unresolved issues?'\n\n"
        "  creative  — The writer is asking for NEW ideas, plot developments, or creative help. "
        "Examples: 'What should happen next?', 'Suggest a plot twist', 'Give me conflict ideas', "
        "'How can I make this scene more intense?', 'What should Ravi do now?'\n\n"
        "  mixed     — The question has BOTH a factual component AND a creative/suggestion component. "
        "Examples: 'Who is Mr. Dinesh and how can I develop him further?', "
        "'What happened with the parking issue and what twist can I add?'\n\n"
        "Return ONLY one word: qa, creative, or mixed."
    )
    raw = await _complete(system, f"Question: {question}", temperature=0.0, max_tokens=10)
    token = raw.strip().lower().split()[0] if raw.strip() else "creative"
    intent = token if token in ("qa", "creative", "mixed") else "creative"
    logger.debug("[ai_service] intent: question=%r → intent=%r", question[:60], intent)
    return intent


# ── Character RAG ─────────────────────────────────────────────────────────────

def _format_character_for_prompt(character, profile, story_passages=None) -> str:
    """
    Format a character + profile as a compact, structured Qwen context block.

    story_passages: optional list of (chapter_number, excerpt_text) tuples
    providing story-grounded evidence for this character.

    raw_notes is included only as a fallback when ALL structured fields are empty
    and no story passages are available.
    """
    traits_str = ", ".join(profile.traits or []) if profile else ""
    lines = [f"## Character: {character.name}"]
    meta = f"Role: {character.role} | Status: {character.status}"
    if traits_str:
        meta += f" | Traits: {traits_str}"
    lines.append(meta)

    if profile:
        structured_fields = [
            ("Age",         profile.age),
            ("Appearance",  profile.appearance),
            ("Personality", profile.personality),
            ("Goals",       profile.goals),
            ("Motivations", profile.motivations),
            ("Backstory",   profile.backstory[:400] if len(profile.backstory or "") > 400
                            else (profile.backstory or "")),
            ("Arc Notes",   profile.arc_notes),
        ]
        has_structured = False
        for label, value in structured_fields:
            if value and value.strip():
                lines.append(f"{label}: {value.strip()}")
                has_structured = True

        # Include raw_notes only as fallback when all structured fields are empty
        # AND no story passages are available
        if not has_structured and not story_passages and profile.raw_notes and profile.raw_notes.strip():
            lines.append(f"Notes: {profile.raw_notes.strip()[:300]}")

    # Story evidence — most valuable for grounding LLM answers in actual text
    if story_passages:
        for ch_num, excerpt in story_passages[:2]:
            lines.append(f"Story evidence (Ch{ch_num}): {excerpt[:200].strip()}")

    return "\n".join(lines)


async def retrieve_character_context(
    story_id: str,
    question: str,
    db,
    top_k: int = 5,
    token_budget: int = 1200,
) -> list[str]:
    """
    Hybrid character retrieval for Plot Assistant context injection.

    Retrieval signals (combined, highest score wins):
      1. Name-mention boost — exact name/alias match in question text
      2. Profile embedding cosine — BGE-M3 similarity on author-written profile text
      3. Mention embedding cosine — BGE-M3 similarity on story-grounded character passages

    Each retrieved character is formatted with their profile AND up to 2 recent
    story evidence passages, giving the LLM both author intent and story grounding.

    Returns [] when no characters exist for the story.
    """
    from models import Character, CharacterProfile

    characters = (
        db.query(Character)
        .filter(Character.story_id == story_id)
        .all()
    )
    if not characters:
        return []

    # ── Signal 1: Name-mention detection ─────────────────────────────────────
    name_mentioned_ids: list[str] = []
    for char in characters:
        pattern = _make_name_pattern(char.name, char.aliases or [])
        if pattern and pattern.search(question):
            name_mentioned_ids.append(char.character_id)

    # ── Signal 2 + 3: Dual embedding cosine similarity ────────────────────────
    profiles_map = {
        p.character_id: p
        for p in db.query(CharacterProfile)
        .filter(CharacterProfile.story_id == story_id)
        .all()
    }
    char_map = {c.character_id: c for c in characters}

    cosine_scored: list[tuple[float, str]] = []
    if any(
        (p.embedding is not None or p.mention_embedding is not None)
        for p in profiles_map.values()
    ):
        from sqlalchemy import text
        q_emb = await embed_text(question)
        q_vec_str = vector_literal(q_emb)

        score_rows = db.execute(
            text(f"""
                SELECT character_id,
                       CASE WHEN embedding IS NOT NULL
                            THEN {vector_similarity('embedding')}
                            ELSE 0.0 END AS profile_score,
                       CASE WHEN mention_embedding IS NOT NULL
                            THEN {vector_similarity('mention_embedding')}
                            ELSE 0.0 END AS mention_score
                FROM character_profiles
                WHERE story_id = :story_id
            """),
            {"q": q_vec_str, "story_id": story_id},
        ).fetchall()

        scored_ids: set[str] = set()
        for row in score_rows:
            best_score = max(
                float(row.profile_score) * 0.4,   # 40% weight for profile
                float(row.mention_score)  * 0.6,   # 60% weight for story evidence
            )
            cosine_scored.append((best_score, row.character_id))
            scored_ids.add(row.character_id)

        for char in characters:
            if char.character_id not in scored_ids:
                cosine_scored.append((0.0, char.character_id))

        cosine_scored.sort(key=lambda x: x[0], reverse=True)

    # ── Merge: name-mentioned first, then top cosine ──────────────────────────
    selected: list[str] = list(name_mentioned_ids)
    for _, char_id in cosine_scored:
        if char_id not in selected:
            selected.append(char_id)
        if len(selected) >= top_k:
            break

    # ── Format with story evidence and token budget ───────────────────────────
    result: list[str] = []
    tokens_used = 0

    for char_id in selected:
        char    = char_map.get(char_id)
        profile = profiles_map.get(char_id)
        if not char:
            continue

        # Get story evidence passages for this character
        story_passages = _get_recent_mentions(char_id, story_id, db, top_k=2)

        if not profile:
            block = f"## Character: {char.name}\nRole: {char.role} | Status: {char.status}"
            if story_passages:
                block += "\n" + "\n".join(
                    f"Story evidence (Ch{n}): {exc[:200]}" for n, exc in story_passages
                )
        else:
            block = _format_character_for_prompt(char, profile, story_passages=story_passages)

        block_tokens = len(block.split()) * 4 // 3
        if tokens_used + block_tokens > token_budget:
            break
        result.append(block)
        tokens_used += block_tokens

    if result:
        logger.info(f"[char_rag_v2] story={story_id[:8]}... — "
            f"{len(result)}/{len(characters)} character(s) injected "
            f"({tokens_used}≈tok, name_boost={len(name_mentioned_ids)}, "
            f"has_mention_emb={sum(1 for p in profiles_map.values() if p.mention_embedding is not None)})")
    return result


# ── Note RAG ──────────────────────────────────────────────────────────────────

async def retrieve_note_context(
    story_id: str,
    question: str,
    db,
    top_k: int = 3,
    token_budget: int = 500,
) -> list[str]:
    """
    Semantic retrieval of StoryNotes and NoteCards for Plot Assistant injection.

    Uses BGE-M3 cosine similarity against embedded title+content.  Records with
    no embedding (created before Task 8 or embed still pending) are silently
    skipped — the function degrades to [] rather than crashing.

    Returns a list of formatted context strings, each representing one note/card,
    capped by token_budget.
    """
    from sqlalchemy import text

    q_emb = await embed_text(question)
    q_vec_str = vector_literal(q_emb)

    rows = db.execute(
        text(f"""
            SELECT 'note' AS kind, note_id AS record_id, title, content,
                   NULL AS card_type,
                   {vector_similarity('embedding')} AS score
            FROM story_notes
            WHERE story_id = :story_id AND embedding IS NOT NULL
            UNION ALL
            SELECT 'card', card_id, title, content, card_type,
                   {vector_similarity('embedding')} AS score
            FROM note_cards
            WHERE story_id = :story_id AND embedding IS NOT NULL
            ORDER BY score DESC
            LIMIT :limit
        """),
        {"q": q_vec_str, "story_id": story_id, "limit": top_k},
    ).fetchall()

    if not rows:
        return []

    result: list[str] = []
    tokens_used = 0
    for row in rows:
        if row.kind == "note":
            title = row.title.strip() if row.title and row.title.strip() else "Story Note"
            body  = row.content[:400].strip() if row.content else ""
            block = f"## Story Note: {title}\n{body}"
        else:
            card_type = row.card_type or "general"
            title = row.title.strip() if row.title and row.title.strip() else f"{card_type.title()} Card"
            body  = row.content[:300].strip() if row.content else ""
            block = f"## {card_type.title()} Card: {title}\n{body}"

        block_tokens = len(block.split()) * 4 // 3
        if tokens_used + block_tokens > token_budget:
            break
        result.append(block)
        tokens_used += block_tokens

    if result:
        logger.info(f"[note_rag] story={story_id[:8]}... — "
            f"{len(result)}/{len(rows)} note(s) injected ({tokens_used}≈tok)")
    return result


# ── Plot Assistant — direct Q&A answer ────────────────────────────────────────

async def answer_story_question(
    question: str,
    text_chunks: list,
    genre_profile: dict = None,
    current_chapter: str = "",
    character_context: list[str] = None,
    note_context: list[str] = None,
    genre_context: str = "",
) -> str:
    """
    Answer a factual question about the story using top-k semantically retrieved
    paragraph-level chunks from chapter_chunks.

    character_context is a list of pre-formatted character profile strings from
    retrieve_character_context().  It is injected only when present, keeping the
    chunk budget for non-character questions fully intact.

    note_context is a list of pre-formatted story note / note card strings from
    retrieve_note_context().  Injected after character context when present.
    """
    system = (
        "You are a story knowledge assistant. Answer the writer's question using "
        "ONLY the retrieved story passages and character profiles provided below — "
        "do not invent any characters, events, or details absent from the context.\n\n"
        "• Short factual questions (Who is X? Where is Y?): 1–3 sentences.\n"
        "• List/summary questions (What happened? What problems? What events?): "
        "read every passage and list ALL distinct items you find — do not stop early."
    )

    parts = [f"Question: {question}"]

    # Prefer the rich shared genre-context block; fall back to a one-line genre.
    if genre_context:
        parts.append(genre_context)
    elif genre_profile:
        g = genre_profile.get("genre", "")
        sg = genre_profile.get("sub_genre", "")
        if g:
            parts.append(f"Story genre: {g}{(' / ' + sg) if sg else ''}")

    if character_context:
        parts.append(
            "Relevant character profiles:\n\n" + "\n\n".join(character_context)
        )

    if note_context:
        parts.append(
            "Author's notes (story notes and research cards):\n\n"
            + "\n\n".join(note_context)
        )

    if text_chunks:
        total_words = sum(c["word_count"] for c in text_chunks)
        passage_blocks = []
        for i, c in enumerate(text_chunks, 1):
            passage_blocks.append(
                f"--- Passage {i} | Chapter {c['chapter']} "
                f"| relevance {c['score']:.2f} ---\n"
                f"{c['text']}"
            )
        parts.append(
            f"Retrieved story passages "
            f"({len(text_chunks)} passages · {total_words} words · "
            f"semantic search via BGE-M3):\n\n"
            + "\n\n".join(passage_blocks)
        )
        user_prompt = "\n\n".join(parts)
        total_chars  = len(system) + len(user_prompt)
        logger.info(f"[qa_answer] {len(text_chunks)} chunk(s), {total_words} words, "
            f"char_ctx={len(character_context or [])}, "
            f"prompt≈{total_chars//4} tokens, max_tokens=900")
    else:
        parts.append(
            "No indexed story passages found for this story. "
            "The author needs to save their chapters and run sync-summaries "
            "so the content can be indexed."
        )
        user_prompt = "\n\n".join(parts)
        logger.info("[qa_answer] No chunks available — answering without story context")

    if current_chapter:
        parts.append(f"Current chapter (last 600 chars):\n{current_chapter[-600:]}")
        user_prompt = "\n\n".join(parts)

    return await _complete(system, user_prompt, temperature=0.0, max_tokens=900)


# ── Plot Assistant — plot suggestions ─────────────────────────────────────────

async def generate_plot_suggestions(
    question: str,
    current_chapter: str = "",
    summaries: list = None,
    character_profiles: list = None,
    genre_profile: dict = None,
    retrieved_chunks: list = None,
    note_context: list[str] = None,
    intel_context: dict = None,
    genre_context: str = "",
) -> list:
    """
    Generate 4 plot suggestions grounded in story context.

    retrieved_chunks — BGE-M3 semantic search results from chapter_summaries.
    If present, they are injected directly into the Qwen prompt so the LLM
    can reason about actual saved story content.
    """
    system = (
        "You are a narrative consultant with deep knowledge of this specific story. "
        "Given the plot question and the story context provided below, suggest 4 concrete, "
        "story-aware plot developments that reference the actual characters, locations, and events "
        "established in the story. Do NOT invent characters or settings that are absent from the "
        "context. Return ONLY a JSON array: [{id: int, text: string, rationale: string}]."
    )
    parts = [f"Plot question: {question}"]

    # Prefer the rich shared genre-context block; fall back to a one-line genre.
    if genre_context:
        parts.append(genre_context)
    elif genre_profile:
        parts.append(
            f"Genre: {genre_profile.get('genre', '')} — "
            f"{genre_profile.get('sub_genre', '')} | "
            f"Tone: {genre_profile.get('tone', '')}"
        )

    # Prefer BGE-M3 retrieved chunks over raw summary list when both are available
    if retrieved_chunks:
        chunk_blocks = []
        for c in retrieved_chunks:
            chars = ", ".join(c.get("characters") or []) or "none listed"
            locs  = ", ".join(c.get("locations")  or []) or "none listed"
            chunk_blocks.append(
                f"--- Chapter {c['chapter']} (relevance {c['score']:.2f}) ---\n"
                f"Summary: {c['raw_summary']}\n"
                f"Characters present: {chars}\n"
                f"Locations: {locs}"
            )
        parts.append(
            "Retrieved story context (BGE-M3 semantic search over saved chapters):\n"
            + "\n\n".join(chunk_blocks)
        )
    elif summaries:
        parts.append(
            "Recent chapter summaries:\n"
            + "\n".join(str(s) for s in (summaries or [])[-5:])
        )

    if character_profiles:
        # character_profiles is a list[str] of pre-formatted context blocks
        # produced by retrieve_character_context() — never raw ORM objects.
        parts.append("Relevant characters:\n\n" + "\n\n".join(character_profiles))

    if note_context:
        parts.append(
            "Author's notes (story notes and research cards):\n\n"
            + "\n\n".join(note_context)
        )

    # Intelligence context from Story Intelligence System (P29)
    if intel_context:
        intel_parts = []
        if intel_context.get("story_premise"):
            intel_parts.append(f"Story premise: {intel_context['story_premise']}")
        if intel_context.get("central_question"):
            intel_parts.append(f"Central question: {intel_context['central_question']}")
        if intel_context.get("primary_theme"):
            intel_parts.append(f"Theme: {intel_context['primary_theme']}")
        if intel_context.get("primary_conflict"):
            intel_parts.append(f"Primary conflict: {intel_context['primary_conflict']}")
        if intel_context.get("critical_issues"):
            intel_parts.append(f"Known issues to avoid: {', '.join(intel_context['critical_issues'][:3])}")
        if intel_context.get("unresolved_threads"):
            intel_parts.append(f"Unresolved threads: {', '.join(intel_context['unresolved_threads'][:3])}")
        if intel_context.get("memory_hits"):
            mem_blocks = [f"  • {h['content']}" for h in intel_context["memory_hits"][:6]]
            intel_parts.append("Relevant story knowledge:\n" + "\n".join(mem_blocks))
        if intel_parts:
            parts.append("Story intelligence context:\n" + "\n".join(intel_parts))

    if current_chapter:
        parts.append(f"Current chapter excerpt (last 600 chars):\n{current_chapter[-600:]}")

    context_status = (
        f"retrieved_chunks={len(retrieved_chunks) if retrieved_chunks else 0}, "
        f"summaries={len(summaries) if summaries else 0}, "
        f"current_chapter={'yes' if current_chapter else 'no'}"
    )
    logger.info("[ai_service] plot_suggestions: calling Qwen — %s", context_status)

    result, meta = await complete_structured(
        system, "\n\n".join(parts),
        coerce=coerce_text_suggestions,
        temperature=0.0, max_tokens=800, label="plot_suggestions",
    )
    if result is None:
        raise ValueError(
            "Plot suggestions could not be generated. Please try again."
        )
    return result


# ── Plot Hole Detection — strategy dispatcher ─────────────────────────────────
#
# Each strategy receives the same list[dict] of structured chapter data and
# returns {"issues": [...], "note": str, "chapters_analyzed": int}.
#
# The dispatcher selects the strategy by name.  Adding a new strategy requires
# only: (a) write the strategy function, (b) register it in _PLOT_HOLE_STRATEGIES.
# The endpoint, response schema, and frontend are never touched.
#
# Current:
#   single_pass — one Qwen call, up to _PLOT_HOLE_MAX_CHAPTERS chapters
#
# Reserved (not yet implemented):
#   batched             — overlapping windows merged; removes the chapter cap
#   hierarchical        — summary-of-summaries pass then targeted deep pass
#   deep_audit          — paragraph-chunk retrieval to verify each suspected issue
#   multi_book_analysis — cross-story / book-series analysis

_PLOT_HOLE_MAX_CHAPTERS = 60   # single_pass per-call limit; batched/hierarchical lift this


def coerce_text_suggestions(parsed) -> tuple[Optional[list], int]:
    """
    Coerce a list of writing/plot suggestions ({id, text, rationale}-ish).

    Shared by generate_suggestions and generate_plot_suggestions: both ask for a
    bare array of objects carrying a text field. An entry with no text is
    dropped — a suggestion with nothing to suggest is not a suggestion.
    """
    items = _issue_list_from(parsed, "suggestions")
    if items is None:
        return None, 0

    kept, discarded = [], 0
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict):
            discarded += 1
            continue
        text = str(item.get("text") or item.get("suggestion") or "").strip()
        if not text:
            discarded += 1
            continue
        entry = dict(item)
        entry["text"] = text
        entry.setdefault("id", position)
        # Both consumers build a Pydantic model straight from this dict — the
        # plot assistant indexes id/text/rationale directly, and ai_transform
        # does Suggestion(**s) where category and reason are required. A model
        # omitting any of them used to be a 500. Presentation fields only; the
        # text above carries the meaning and is never invented.
        explanation = str(item.get("rationale") or item.get("reason") or "")
        entry["rationale"] = explanation
        entry["reason"]    = explanation
        entry.setdefault("category", "general")
        kept.append(entry)
    return kept, discarded


def coerce_copyright_findings(parsed) -> tuple[Optional[dict], int]:
    """Coerce a copyright-risk response — {findings: [...], overall_risk: ...}."""
    findings = _issue_list_from(parsed, "findings")
    if findings is None:
        return None, 0

    kept, discarded = [], 0
    for item in findings:
        if not isinstance(item, dict):
            discarded += 1
            continue
        if not str(item.get("description") or "").strip():
            discarded += 1
            continue
        kept.append(item)

    overall = ""
    if isinstance(parsed, dict):
        overall = str(parsed.get("overall_risk") or "").lower()
    return {
        "findings":     kept,
        "overall_risk": overall if overall in _RISK_LEVELS else "",
    }, discarded


def coerce_manuscript_report(parsed) -> tuple[Optional[dict], int]:
    """
    Coerce a manuscript-report pass. Unlike the findings lists, this is a
    composite object: partial is genuinely useful (character arcs without
    pacing still tells the author something), so any recognised key survives.
    """
    if not isinstance(parsed, dict):
        return None, 0
    keys = ("character_arcs", "pacing", "unresolved_threads", "strengths", "improvements")
    present = {k: parsed[k] for k in keys if k in parsed}
    if not present:
        return None, 0
    return present, len(keys) - len(present)


def coerce_chapter_summary(parsed) -> tuple[Optional[dict], int]:
    """
    Coerce a chapter summary.

    This one matters more than the rest: chapter summaries are written at
    INDEX time and are the evidence every retrieval, grounding and continuity
    feature stands on. A summary that fails here is not one missing panel — it
    is a chapter that is invisible to the whole system until it is re-indexed.

    ``raw_summary`` is the load-bearing field and is required; the structured
    lists are defaulted to empty when absent, and normalised to lists when the
    model returns a bare string. Each missing field counts as a discard so the
    caller can see how thin the summary is.
    """
    if not isinstance(parsed, dict):
        return None, 0

    raw_summary = str(parsed.get("raw_summary") or "").strip()
    if not raw_summary:
        return None, 0

    def _as_list(value) -> list:
        if isinstance(value, list):
            return [v for v in value if v not in (None, "")]
        if isinstance(value, str) and value.strip():
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    list_fields = ("key_events", "characters_present", "locations", "timeline_markers")
    discarded = sum(1 for f in list_fields if not _as_list(parsed.get(f)))
    result = {f: _as_list(parsed.get(f)) for f in list_fields}
    result["emotional_tone"]  = str(parsed.get("emotional_tone") or "")
    result["chapter_purpose"] = str(parsed.get("chapter_purpose") or "")
    result["raw_summary"]     = raw_summary
    if not result["emotional_tone"]:
        discarded += 1
    if not result["chapter_purpose"]:
        discarded += 1
    return result, discarded


def _issue_list_from(parsed, key: str) -> Optional[list]:
    """
    Find the findings array in whatever shape the model returned.

    Accepts the documented ``{key: [...]}``, a bare array, or a wrapper object
    with exactly one array in it — the three shapes a model actually produces
    when it drifts. Anything else is unusable, and saying so is the point:
    guessing between several arrays would be inventing structure.
    """
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        if isinstance(parsed.get(key), list):
            return parsed[key]
        arrays = [v for v in parsed.values() if isinstance(v, list)]
        if len(arrays) == 1:
            return arrays[0]
    return None


def _chapter_numbers(value) -> list[int]:
    """Chapter references as ints, from a list, a single number, or "3, 7"."""
    if isinstance(value, (int, float)):
        return [int(value)]
    if isinstance(value, str):
        return [int(x) for x in re.findall(r"\d+", value)]
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_chapter_numbers(v))
        return out
    return []


def coerce_plot_hole_result(parsed) -> tuple[Optional[dict], int]:
    """
    Coerce a plot-hole response, salvaging every usable finding.

    Defaults only *presentation* fields — id, severity, suggestion. A finding
    with no description is dropped rather than given one: inventing the meaning
    of a finding would be worse than losing it.
    """
    issues_raw = _issue_list_from(parsed, "issues")
    if issues_raw is None:
        return None, 0

    kept, discarded = [], 0
    for position, item in enumerate(issues_raw, 1):
        if not isinstance(item, dict):
            discarded += 1
            continue
        description = str(item.get("description") or "").strip()
        if not description:
            discarded += 1
            continue
        severity = str(item.get("severity") or "").lower()
        kept.append({
            "issue_id":    item["issue_id"] if isinstance(item.get("issue_id"), int) else position,
            "type":        str(item.get("type") or "continuity_break"),
            "severity":    severity if severity in ("high", "medium", "low") else "medium",
            "chapters":    _chapter_numbers(item.get("chapters")),
            "description": description,
            "suggestion":  str(item.get("suggestion") or ""),
        })

    note = parsed.get("note", "") if isinstance(parsed, dict) else ""
    return {"issues": kept, "note": str(note or "")}, discarded


def coerce_continuity_issues(parsed) -> tuple[Optional[list], int]:
    """Coerce a continuity response. Same rules as plot holes; different fields."""
    issues_raw = _issue_list_from(parsed, "issues")
    if issues_raw is None:
        return None, 0

    kept, discarded = [], 0
    for item in issues_raw:
        if not isinstance(item, dict):
            discarded += 1
            continue
        description = str(item.get("description") or "").strip()
        if not description:
            discarded += 1
            continue
        severity = str(item.get("severity") or "").lower()
        kept.append({
            "type":            str(item.get("type") or "continuity_break"),
            "description":     description,
            "chapter_refs":    _chapter_numbers(item.get("chapter_refs")),
            "severity":        severity if severity in ("high", "medium", "low") else "medium",
            "resolution_hint": str(item.get("resolution_hint") or ""),
        })
    return kept, discarded


async def _strategy_single_pass(chapters: list[dict]) -> dict:
    """
    Single Qwen call over up to _PLOT_HOLE_MAX_CHAPTERS structured chapter entries.

    chapters: [{chapter, events, characters, locations, timeline, purpose}]
    Returns:  {"issues": [...], "note": str, "chapters_analyzed": int}
    """
    capped   = chapters[:_PLOT_HOLE_MAX_CHAPTERS]
    cap_note = (
        f"60-chapter cap applied — chapters {_PLOT_HOLE_MAX_CHAPTERS + 1}+ not scanned "
        "in this pass. A batched analysis strategy will remove this limitation."
        if len(chapters) > _PLOT_HOLE_MAX_CHAPTERS else ""
    )

    system = (
        "You are a manuscript consistency analyst. Analyze the chapter-by-chapter story data "
        "below and identify potential plot holes and narrative inconsistencies.\n\n"
        "Analyze for:\n"
        "1. CHARACTER_INCONSISTENCY — a character described as dead/absent appears active later\n"
        "2. LOCATION_INCONSISTENCY  — characters in impossible or contradictory locations\n"
        "3. TIMELINE_INCONSISTENCY  — events that contradict the established chronology\n"
        "4. UNRESOLVED_THREAD       — a significant conflict or setup never addressed again\n"
        "5. CONTINUITY_BREAK        — a fact, object, or state changes without explanation\n"
        "6. CHARACTER_DISAPPEARANCE — a named character introduced then never mentioned again\n\n"
        "CRITICAL RULES:\n"
        "- Only report issues with CONCRETE cross-chapter evidence from the data provided.\n"
        "- Do NOT invent issues. If no evidence exists, return an empty issues array.\n"
        "- Every issue must cite the specific chapter numbers where the contradiction occurs.\n\n"
        'Return ONLY valid JSON:\n'
        '{"issues": [{"issue_id": int, "type": str, "severity": "high|medium|low", '
        '"chapters": [int], "description": str, "suggestion": str}], '
        '"note": "one-sentence summary or No issues detected."}'
    )

    lines = []
    for c in capped:
        events   = "; ".join(c["events"])     if c.get("events")     else "—"
        chars    = ", ".join(c["characters"]) if c.get("characters") else "—"
        locs     = ", ".join(c["locations"])  if c.get("locations")  else "—"
        timeline = "; ".join(c["timeline"])   if c.get("timeline")   else "—"
        purpose  = (c.get("purpose") or "").strip() or "—"
        lines.append(
            f"Ch{c['chapter']} | Events: {events} | "
            f"Characters: {chars} | Locations: {locs} | "
            f"Timeline: {timeline} | Purpose: {purpose}"
        )

    result, meta = await complete_structured(
        system,
        "Story chapters:\n\n" + "\n".join(lines),
        coerce=coerce_plot_hole_result,
        temperature=0.0,
        max_tokens=1400,
        label="plot_holes",
    )

    if result is None:
        # Nothing usable survived two attempts — the only case that still fails.
        raise ValueError(
            "Plot hole analysis could not be completed. Please try again."
        )

    return {
        "issues":            result["issues"],
        "note":              cap_note or result.get("note", ""),
        "chapters_analyzed": len(capped),
        "degraded":          meta.degraded,
        "degraded_reason":   meta.reason,
    }


# Strategy registry — register new strategies here; nothing else changes.
_PLOT_HOLE_STRATEGIES: dict[str, Callable] = {
    "single_pass": _strategy_single_pass,
    # "batched":             _strategy_batched,        # future
    # "hierarchical":        _strategy_hierarchical,   # future
    # "deep_audit":          _strategy_deep_audit,     # future
    # "multi_book_analysis": _strategy_multi_book,     # future
}


async def detect_plot_holes(
    story_id:  str,
    summaries: list[dict],
    strategy:  str = "single_pass",
) -> dict:
    """
    Dispatch to the named analysis strategy and return normalised results.

    summaries — structured chapter data from the router:
                [{chapter, events, characters, locations, timeline, purpose}]
    strategy  — analysis strategy name (default "single_pass")
                Future strategies added to _PLOT_HOLE_STRATEGIES are immediately
                selectable by passing strategy="batched" etc. from the router.

    Returns dict with: issues (list), note (str), chapters_analyzed (int)
    """
    fn = _PLOT_HOLE_STRATEGIES.get(strategy)
    if fn is None:
        raise ValueError(
            f"Unknown analysis strategy: {strategy!r}. "
            f"Available: {list(_PLOT_HOLE_STRATEGIES)}"
        )

    logger.info(f"[plot_holes] story={story_id[:8]}... "
        f"strategy={strategy!r} total_chapters={len(summaries)}")
    result = await fn(summaries)
    logger.info(f"[plot_holes] done — "
        f"{result['chapters_analyzed']} analyzed, "
        f"{len(result['issues'])} issue(s) found")
    return result


# ── Copyright / Plagiarism Risk Detection ──────────────────────────────────────
#
# Heuristic risk guidance — NOT legal advice. The model reasons from training
# knowledge, not a database of copyrighted works, so it cannot guarantee detection.
# We always attach a non-legal-advice disclaimer and score low/medium/high (never
# numeric certainty).

_RISK_LEVELS = ("low", "medium", "high")

COPYRIGHT_DISCLAIMER = (
    "This is automated copyright/plagiarism RISK guidance to help you make your "
    "writing more original — not legal advice, and not a guarantee. It cannot "
    "detect every similarity and may flag generic tropes. Consult a qualified "
    "professional for legal questions."
)

_COPYRIGHT_SYSTEM = (
    "You are a copyright and originality risk analyst for fiction writers. "
    "Assess whether the author's text appears too similar to existing, well-known "
    "stories, books, characters, plots, worlds, or famous scenes.\n\n"
    "Classify each finding's risk_type as ONE of:\n"
    "  direct_text       — wording/phrasing close to a known published passage\n"
    "  plot              — plot/structure close to a specific known work\n"
    "  character         — a character closely resembling a known copyrighted one\n"
    "  world_building     — setting/world closely resembling a known franchise\n"
    "  scene             — a specific famous scene closely reproduced\n"
    "  style_imitation    — imitation of a specific living/in-copyright author's style\n"
    "  trope_overuse      — heavy reliance on generic, overused tropes\n\n"
    "CRITICAL RULES:\n"
    "- Do NOT claim legal certainty. This is risk guidance, not legal advice.\n"
    "- Clearly distinguish a GENERIC, unprotectable trope (is_generic_trope=true) "
    "from a SERIOUS, specific similarity to a particular work (is_generic_trope=false).\n"
    "- Only report findings you can justify from the text provided.\n"
    "- For every finding give a concrete rewrite_suggestion that increases originality.\n\n"
    "Score risk_score and overall_risk as one of: low | medium | high.\n"
    'Return ONLY valid JSON:\n'
    '{"overall_risk": "low|medium|high", '
    '"findings": [{"risk_type": str, "risk_score": "low|medium|high", '
    '"description": str, "problematic_excerpt": str, "is_generic_trope": bool, '
    '"rewrite_suggestion": str}], '
    '"note": "one-sentence summary"}'
)

_COPYRIGHT_MAX_CHARS = 12000  # keep the prompt well within context


def _normalize_risk(value, default: str = "low") -> str:
    v = str(value or "").strip().lower()
    return v if v in _RISK_LEVELS else default


async def analyze_copyright_risk(
    scope: str,
    text: str,
    genre_context: str = "",
) -> dict:
    """Analyze text for copyright/plagiarism risk.

    scope  — "selection" | "chapter" | "project" (informational; the router
             assembles `text` for project scope from chapter summaries).
    text   — the prose (or structured digest) to assess. Trimmed to a safe cap.

    Returns: {overall_risk, findings[], note, disclaimer}. `findings` is always a
    list of dicts with normalized risk levels. Raises AIServiceUnavailableError
    (via _complete) when vLLM is down; raises ValueError on unparseable output.
    """
    clipped = (text or "").strip()[:_COPYRIGHT_MAX_CHARS]
    system = _with_genre(_COPYRIGHT_SYSTEM, genre_context)
    user = f"Scope: {scope}\n\nText to analyze:\n\n{clipped}"

    result, parse_meta = await complete_structured(
        system, user,
        coerce=coerce_copyright_findings,
        temperature=0.0, max_tokens=1600, label="copyright_risk",
    )
    if result is None:
        raise ValueError(
            "Copyright risk analysis could not be completed. Please try again."
        )

    findings = []
    for i, f in enumerate(result.get("findings", []) or []):
        if not isinstance(f, dict):
            continue
        findings.append({
            "finding_id":          i + 1,
            "risk_type":           str(f.get("risk_type", "trope_overuse")),
            "risk_score":          _normalize_risk(f.get("risk_score")),
            "description":         str(f.get("description", "")),
            "problematic_excerpt": str(f.get("problematic_excerpt", "") or ""),
            "is_generic_trope":    bool(f.get("is_generic_trope", False)),
            "rewrite_suggestion":  str(f.get("rewrite_suggestion", "")),
        })

    # Derive overall risk: trust the model unless it omitted it — then take the max
    # finding level so the headline never under-reports.
    overall = _normalize_risk(result.get("overall_risk"), default="")
    if not overall:
        overall = "low"
        for f in findings:
            if f["risk_score"] == "high":
                overall = "high"; break
            if f["risk_score"] == "medium":
                overall = "medium"

    return {
        "overall_risk": overall,
        "findings":     findings,
        "note":         str(result.get("note", "") or ""),
        "disclaimer":   COPYRIGHT_DISCLAIMER,
    }


# ── Full Manuscript Analysis ──────────────────────────────────────────────────
#
# Same strategy-dispatcher pattern as plot hole detection.
# To add a new strategy: (a) write the function, (b) register it in
# _MANUSCRIPT_STRATEGIES.  The endpoint, response schema, and frontend never change.
#
# Current:
#   summary_pass — one Qwen call; rich format (raw_summary) for ≤20 ch,
#                  structured-only for >20 ch; caps at _MANUSCRIPT_MAX_CHAPTERS
#
# Reserved:
#   deep_pass   — per-dimension multi-call (arcs | pacing | threads separately)
#   multi_pass  — iterative refinement with a second verification pass
#   multi_book  — cross-story / book-series analysis

_MANUSCRIPT_MAX_CHAPTERS = 60    # summary_pass per-call limit
_MANUSCRIPT_RICH_CUTOFF  = 20    # chapters ≤ this get raw_summary for deeper arc analysis


async def _strategy_manuscript_summary_pass(chapters: list[dict]) -> dict:
    """
    Adaptive Qwen call for full manuscript editorial analysis.

    ≤ _MANUSCRIPT_RICH_CUTOFF chapters: includes raw_summary (richer arc analysis).
    > _MANUSCRIPT_RICH_CUTOFF chapters: structured fields only (scalable to cap).
    Caps at _MANUSCRIPT_MAX_CHAPTERS.

    chapters: [{chapter, events, characters, locations, tone, purpose, word_count, raw_summary}]
    Returns:  {character_arcs, pacing, unresolved_threads, strengths, improvements,
               note, mode_note, chapters_analyzed, word_count_total}
    """
    capped   = chapters[:_MANUSCRIPT_MAX_CHAPTERS]
    rich     = len(capped) <= _MANUSCRIPT_RICH_CUTOFF
    cap_note = (
        f"Chapter cap applied — chapters {_MANUSCRIPT_MAX_CHAPTERS + 1}+ not analyzed in this pass."
        if len(chapters) > _MANUSCRIPT_MAX_CHAPTERS else ""
    )
    mode_note = (
        f"Rich analysis (raw summaries included, {len(capped)} chapters)."
        if rich else
        f"Structured analysis ({len(capped)} chapters — raw summaries excluded to fit context window)."
    )

    system = (
        "You are a developmental editor producing an editorial analysis report.\n\n"
        "Given the chapter-by-chapter manuscript data below, return a structured analysis.\n\n"
        "ANALYZE THESE DIMENSIONS:\n"
        "1. CHARACTER_ARCS — for each character appearing in ≥2 chapters: their journey and arc "
        "completeness.\n"
        "   - appears_in MUST be in ascending order.\n"
        "   - arc_summary: 1-2 sentences on how the character changes from first to last appearance.\n"
        "   - completeness: 'complete' (arc resolved), 'partial' (arc in progress), "
        "'unresolved' (arc set up but never developed).\n"
        "   - CITE the actual chapter numbers from the data.\n"
        "2. PACING — identify slow chapters (few events, low word count, transitional) and "
        "intense chapters (many events, high emotion/conflict).\n"
        "   - slow_chapters and intense_chapters MUST be actual chapter numbers from the data.\n"
        "3. UNRESOLVED_THREADS — significant conflicts, mysteries, or subplots set up but never "
        "resolved.\n"
        "   - introduced_in: the chapter number where the thread is first established.\n"
        "   - chapters: ALL chapter numbers (ascending) where this thread appears.\n"
        "4. STRENGTHS — 2-4 specific observations about what this manuscript does well.\n"
        "   - chapters: the actual chapter numbers that demonstrate this strength.\n"
        "5. IMPROVEMENTS — 2-4 specific, actionable revision suggestions.\n"
        "   - chapters: the actual chapter numbers that motivated this recommendation.\n\n"
        "RULES:\n"
        "- Every chapter reference MUST be an actual chapter number from the data below.\n"
        "- Do NOT invent chapter numbers or make generic observations without chapter evidence.\n"
        "- Cite specific chapters for every finding.\n\n"
        'Return ONLY valid JSON:\n'
        '{"character_arcs": [{"name": str, "appears_in": [int], "arc_summary": str, '
        '"completeness": "complete|partial|unresolved"}], '
        '"pacing": {"slow_chapters": [int], "intense_chapters": [int], "assessment": str}, '
        '"unresolved_threads": [{"description": str, "introduced_in": int, "chapters": [int]}], '
        '"strengths": [{"text": str, "chapters": [int]}], '
        '"improvements": [{"text": str, "chapters": [int]}], '
        '"note": "one-sentence summary"}'
    )

    lines = []
    for c in capped:
        events  = "; ".join(c.get("events",     []) or []) or "—"
        chars   = ", ".join(c.get("characters", []) or []) or "—"
        tone    = c.get("tone",    "") or "—"
        purpose = c.get("purpose", "") or "—"
        wc      = c.get("word_count", 0) or 0
        line    = (
            f"Ch{c['chapter']} (WC:{wc}) | Events: {events} | "
            f"Characters: {chars} | Tone: {tone} | Purpose: {purpose}"
        )
        if rich and c.get("raw_summary"):
            line += f"\nSummary: {c['raw_summary']}"
        lines.append(line)

    separator = "\n\n" if rich else "\n"
    result, parse_meta = await complete_structured(
        system,
        "Manuscript chapters:\n\n" + separator.join(lines),
        coerce=coerce_manuscript_report,
        temperature=0.1, max_tokens=1800, label="manuscript_report",
    )
    if result is None:
        raise ValueError(
            "Manuscript analysis could not be completed. Please try again."
        )

    wc_total = sum(c.get("word_count", 0) or 0 for c in capped)
    return {
        "character_arcs":     result.get("character_arcs",     []),
        "pacing":             result.get("pacing", {"slow_chapters": [], "intense_chapters": [], "assessment": ""}),
        "unresolved_threads": result.get("unresolved_threads", []),
        "strengths":          result.get("strengths",          []),
        "improvements":       result.get("improvements",       []),
        "note":               cap_note or result.get("note", ""),
        "mode_note":          mode_note,
        "chapters_analyzed":  len(capped),
        "word_count_total":   wc_total,
    }


# Strategy registry — register new strategies here; nothing else changes.
_MANUSCRIPT_STRATEGIES: dict[str, Callable] = {
    "summary_pass": _strategy_manuscript_summary_pass,
    # "deep_pass":  _strategy_manuscript_deep_pass,   # future
    # "multi_pass": _strategy_manuscript_multi_pass,  # future
    # "multi_book": _strategy_manuscript_multi_book,  # future
}


async def analyze_manuscript(
    story_id:  str,
    chapters:  list[dict],
    strategy:  str = "summary_pass",
) -> dict:
    """
    Dispatch to the named manuscript analysis strategy and return results.

    chapters — structured chapter data from the router:
               [{chapter, events, characters, tone, purpose, word_count, raw_summary}]
    strategy — analysis strategy name (default "summary_pass")
               Future strategies added to _MANUSCRIPT_STRATEGIES are immediately
               selectable from the router without endpoint or schema changes.

    Returns dict with: character_arcs, pacing, unresolved_threads, strengths,
                       improvements, note, mode_note, chapters_analyzed, word_count_total
    """
    fn = _MANUSCRIPT_STRATEGIES.get(strategy)
    if fn is None:
        raise ValueError(
            f"Unknown manuscript strategy: {strategy!r}. "
            f"Available: {list(_MANUSCRIPT_STRATEGIES)}"
        )

    logger.info(f"[manuscript] story={story_id[:8]}... "
        f"strategy={strategy!r} total_chapters={len(chapters)}")
    result = await fn(chapters)
    logger.info(f"[manuscript] done — "
        f"{result['chapters_analyzed']} analyzed, "
        f"{len(result.get('character_arcs', []))} arc(s), "
        f"{len(result.get('unresolved_threads', []))} thread(s)")
    return result


# ── OCR text cleanup (called by ocr_service after GOT-OCR2.0) ────────────────

async def clean_ocr_text(raw_text: str) -> tuple[str, str]:
    """
    Returns (cleaned_text, note_type).

    Safety guard: if raw_text is empty or too short, return immediately
    without calling Qwen. This prevents Qwen from generating a "no text
    to clean" filler response that would be shown as the extracted text.
    """
    if not raw_text or len(raw_text.strip()) < 5:
        logger.warning(f"[clean_ocr_text] raw_text too short ({len(raw_text.strip())} chars) — "
            "skipping Qwen call.")
        return ("", "other")

    clean_system = (
        "You are an OCR post-processor for handwritten writer's notes. "
        "Your ONLY task is to fix spacing between words, fix punctuation, join broken lines that "
        "belong together, and improve readability. "
        "CRITICAL RULE: Do NOT change, correct, or rewrite any proper nouns — character names, "
        "place names, organisation names, or unique story-specific terms must be preserved exactly "
        "as they appear in the OCR text, even if they look misspelled. "
        "Return ONLY the cleaned text, nothing else."
    )
    cleaned = await _complete(clean_system, f"Raw OCR:\n{raw_text}", temperature=0.0, max_tokens=400)

    type_system = (
        "Classify this writer's note into one of: character, plot, setting, dialogue, theme, research, other. "
        "Return only the single lowercase word."
    )
    raw_type = await _complete(type_system, cleaned, temperature=0.0, max_tokens=5)
    valid = {"character", "plot", "setting", "dialogue", "theme", "research", "other"}
    note_type = raw_type.strip().lower().split()[0] if raw_type.strip() else "other"
    return cleaned, note_type if note_type in valid else "other"


# ── OCR story-context suggestions — entity-safe architecture ─────────────────
#
# Three-layer safety model:
#
#   Layer 1 — Entity Registry
#     Built from ChapterSummary.characters_present + locations across all
#     indexed chapters.  Schema: {canonical_form: entity_type}.
#
#   Layer 2 — Protected Span Detection
#     Sliding n-gram window (1–6 words) over the OCR text.
#     A span is PROTECTED when it matches any registry entity at:
#       ① Exact match (case-insensitive)
#       ② Normalized match (strip punctuation, lowercase)
#       ③ High-similarity ≥ 0.90 (recognizable form of the entity)
#     Protected = "already a valid story entity form — do not suggest replacing it."
#
#   Layer 3 — Post-Filter Gate (runs after Qwen output)
#     Rule 1: suggestion.original is in the protected set → DISCARD
#     Rule 2: suggestion.original has ≥ 0.90 similarity to any registry entity
#             → DISCARD (it is already a valid entity form, just short)
#     Rule 3: suggestion.suggested is not in the registry
#             → DISCARD (Qwen hallucinated a non-entity)
#
# This guarantees the system never suggests replacing one valid entity with
# another valid entity, for any story, any author, any manuscript.
# ─────────────────────────────────────────────────────────────────────────────


def _build_entity_registry(
    story_id: str, db
) -> tuple[dict[str, str], dict[str, int], int]:
    """
    Build the entity registry from all chapter summaries for a story.

    Returns:
        registry          — {canonical_form: entity_type}
        term_chapter_count — {term: number_of_chapters_where_it_appears}
        n_summaries        — total number of chapter summaries found
    """
    from models import ChapterSummary

    summaries = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == story_id)
        .all()
    )

    registry: dict[str, str] = {}
    term_chapter_count: dict[str, int] = {}

    for s in summaries:
        seen_in_chapter: set[str] = set()
        for name in (s.characters_present or []):
            t = name.strip()
            if len(t) >= 2:
                registry[t] = "character"
                if t not in seen_in_chapter:
                    term_chapter_count[t] = term_chapter_count.get(t, 0) + 1
                    seen_in_chapter.add(t)
        for loc in (s.locations or []):
            t = loc.strip()
            if len(t) >= 2:
                registry[t] = "location"
                if t not in seen_in_chapter:
                    term_chapter_count[t] = term_chapter_count.get(t, 0) + 1
                    seen_in_chapter.add(t)

    return registry, term_chapter_count, max(1, len(summaries))


def _normalize_span(s: str) -> str:
    """Lowercase and strip punctuation for normalized entity comparison."""
    import re
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def _find_protected_spans(
    raw_text: str,
    registry: dict[str, str],
    threshold: float = 0.90,
) -> set[str]:
    """
    Scan the OCR text for spans that already match a known registry entity.
    Returns a set of lowercase span strings that are PROTECTED.

    A span is protected when it matches any entity at one of three levels:
      ① Exact match (case-insensitive)
      ② Normalized match (punctuation stripped, lowercased)
      ③ High-similarity SequenceMatcher ratio ≥ threshold

    Uses a sliding n-gram window (1–6 words) over the OCR text so that
    multi-word entities like "B-204 Uncle" or "Green Street" are detected
    as protected spans, not just as individual protected words.
    """
    from difflib import SequenceMatcher

    if not registry or not raw_text.strip():
        return set()

    normalized_registry = {_normalize_span(e): e for e in registry}
    words = raw_text.split()
    protected: set[str] = set()

    for n in range(1, 7):  # 1-gram through 6-gram
        for i in range(len(words) - n + 1):
            span       = " ".join(words[i: i + n])
            span_lower = span.lower()
            span_norm  = _normalize_span(span)

            for entity, canon in normalized_registry.items():
                # ① Exact (case-insensitive)
                if span_lower == entity:
                    protected.add(span_lower)
                    break
                # ② Normalized
                if span_norm == entity:
                    protected.add(span_lower)
                    break
                # ③ High-similarity
                ratio = SequenceMatcher(None, span_lower, entity).ratio()
                if ratio >= threshold:
                    protected.add(span_lower)
                    break

    return protected


def _apply_entity_safety_filter(
    suggestions: list[dict],
    registry: dict[str, str],
    protected: set[str],
) -> list[dict]:
    """
    Apply three entity-safety rules to a list of candidate suggestions.
    Any suggestion that fails a rule is silently discarded.

    Rule 1: original span is in the protected set.
            → The OCR text is already a valid entity form — discard.

    Rule 2: original span has ≥ 0.90 similarity to any registry entity.
            → Even if not in the exact protected set, it is recognizably
              a valid entity form — discard.

    Rule 3: suggested replacement is not a registry entity.
            → Qwen generated a non-entity replacement — discard.
    """
    from difflib import SequenceMatcher

    registry_lower = {e.lower(): e for e in registry}
    safe: list[dict] = []

    for s in suggestions:
        orig_lower = s["original"].lower()
        sugg_lower = s["suggested"].lower()

        # Rule 1 — original is a known-protected span
        if orig_lower in protected:
            logger.info(f"[entity_safety] Discarded '{s['original']}' → '{s['suggested']}': "
                "original is a protected entity span (Rule 1)")
            continue

        # Rule 2 — original is a high-similarity form of any registry entity
        max_sim = max(
            (SequenceMatcher(None, orig_lower, e).ratio() for e in registry_lower),
            default=0.0,
        )
        if max_sim >= 0.90:
            logger.info(f"[entity_safety] Discarded '{s['original']}' → '{s['suggested']}': "
                f"original matches registry entity at {max_sim:.2f} (Rule 2)")
            continue

        # Rule 3 — suggested replacement must be a known registry entity
        sugg_in_registry = any(
            SequenceMatcher(None, sugg_lower, e).ratio() >= 0.90
            for e in registry_lower
        )
        if not sugg_in_registry:
            logger.info(f"[entity_safety] Discarded '{s['original']}' → '{s['suggested']}': "
                "suggested term is not a registry entity (Rule 3)")
            continue

        safe.append(s)

    return safe


def _suggest_difflib(
    raw_text: str,
    registry: dict[str, str],
    protected: set[str],
    term_chapter_count: dict[str, int],
    n_summaries: int,
) -> list[dict]:
    """
    Entity-safe difflib fallback for OCR suggestions.

    Uses SequenceMatcher to identify OCR tokens that are likely corrupted
    forms of known story entities.  Derives story vocabulary from the
    pre-built entity registry (no additional DB query).

    Entity safety:
      Any OCR token that appears in the protected set (already matches a
      known entity at ≥ 0.90 similarity) is skipped — it does not need
      correction and must not be replaced with a different entity.

    Ranking:
      1. String similarity    — SequenceMatcher char ratio (primary)
      2. Manuscript frequency — term_chapter_count / n_summaries × 0.2 boost
      3. Context frequency    — +0.1 boost if token appears ≥ 2 times in image
      4. Phrase-level depth   — phrase suggestions emitted before single-word

    Output: phrase suggestions first, single-word second, cap 8.
    No LLM. No story-specific terms hardcoded.
    """
    import re
    from difflib import SequenceMatcher

    if not raw_text or not raw_text.strip() or not registry:
        return []

    # Derive character and location sets from the pre-built registry
    story_chars: set[str] = {e for e, t in registry.items() if t == "character" and len(e) >= 3}
    story_locs:  set[str] = {e for e, t in registry.items() if t == "location"  and len(e) >= 3}

    if not story_chars and not story_locs:
        return []

    COMMON_GENERIC: set[str] = {
        "chapter", "scene", "paragraph", "page", "draft", "version",
        "association", "society", "community", "committee", "council",
        "board", "club", "group", "party", "team", "league", "union",
        "federation", "institute", "organisation", "organization",
        "secretary", "treasurer", "president", "chairman", "chairwoman",
        "manager", "director", "officer", "member", "leader", "head",
        "chief", "general", "captain", "commissioner", "administrator",
        "phone", "mobile", "message", "email", "letter", "note", "notice",
        "report", "memo", "document", "file", "record", "form", "circular",
        "street", "road", "lane", "avenue", "drive", "court", "place",
        "park", "area", "zone", "district", "region", "block", "sector",
        "colony", "locality", "neighborhood", "neighbourhood",
        "hall", "building", "house", "home", "office", "room", "floor",
        "apartment", "flat", "complex", "center", "centre", "campus",
        "estate", "compound",
        "event", "meeting", "gathering", "function", "ceremony",
        "occasion", "session", "conference", "seminar", "festival",
        "idea", "plan", "issue", "problem", "matter", "situation",
        "case", "reason", "result", "cause", "solution", "answer",
        "complaint", "request", "proposal", "agenda",
        "person", "people", "man", "woman", "boy", "girl", "child",
        "neighbor", "neighbour", "resident", "residents", "citizen",
        "family", "friend", "colleague", "companion", "visitor", "guest",
        "doctor", "teacher", "engineer", "lawyer", "police", "agent",
        "staff", "worker", "employee", "volunteer", "contractor",
        "water", "food", "money", "work", "business", "company",
        "book", "story", "news", "paper", "list", "item", "topic",
        "project", "program", "programme", "scheme", "initiative",
        "morning", "evening", "afternoon", "night", "time", "year",
        "month", "week", "day", "hour", "minute",
    }

    NOT_PROPER: set[str] = {
        "The", "A", "An",
        "I", "It", "He", "She", "We", "They", "You",
        "Me", "Him", "Her", "Us", "Them", "His", "Its", "Our", "Your", "Their", "My",
        "Was", "Were", "Is", "Are", "Has", "Have", "Had", "Does", "Do",
        "Will", "Would", "Could", "Should",
        "And", "But", "Or", "So", "Yet", "For", "Nor",
        "As", "At", "By", "In", "Of", "On", "To", "Up", "Via",
        "When", "Where", "Why", "How", "What", "Who", "Which",
        "This", "That", "These", "Those",
        "While", "Then", "Now", "Here", "There", "Still", "Just", "Also", "Not",
        "Mr", "Mrs", "Ms", "Dr", "Prof", "Sir",
    }

    PHRASE_STOP: set[str] = {
        "the", "a", "an", "of", "in", "at", "for", "and", "or", "to",
        "by", "is", "was", "as", "why", "what", "who", "how", "when",
        "where", "it", "its", "this", "that", "but", "so", "yet", "not",
        "he", "she", "we", "they", "i", "me", "him", "her", "us", "them",
        "his", "our", "your", "their", "my",
        "while", "then", "now", "here", "there", "still", "just", "also",
        "more", "some", "one", "two", "three",
    }

    def _sim(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _ms_freq(term: str) -> float:
        return term_chapter_count.get(term, 0) / n_summaries

    def _literal_word_in_term(ocr_word: str, story_term: str) -> bool:
        ow = ocr_word.lower()
        return ow in {w.lower().strip(".,()") for w in story_term.split()}

    def _best_word_coverage(ocr_phrase: str, story_phrase: str) -> float:
        ow = [w.lower() for w in ocr_phrase.split() if w.lower() not in PHRASE_STOP and len(w) >= 3]
        sw = [w.lower() for w in story_phrase.split() if len(w) >= 2]
        if not ow or not sw:
            return 0.0
        return sum(max(_sim(o, s) for s in sw) for o in ow) / len(ow)

    def _meaningful_match_count(ocr_phrase: str, story_phrase: str) -> int:
        ow = [w.lower() for w in ocr_phrase.split() if w.lower() not in PHRASE_STOP and len(w) >= 3]
        sw = [w.lower() for w in story_phrase.split() if len(w) >= 2]
        if not ow or not sw:
            return 0
        return sum(1 for o in ow if max(_sim(o, s) for s in sw) >= 0.50)

    def _has_content(phrase: str) -> bool:
        return sum(1 for w in phrase.lower().split() if w not in PHRASE_STOP and len(w) >= 3) >= 2

    def _subsentence_ngrams(line: str, n: int) -> list[str]:
        parts = re.split(r"[.!?;#]+", line)
        result: list[str] = []
        for part in parts:
            words = re.sub(r"[^\w\s]", " ", part).split()
            result.extend(" ".join(words[i: i + n]) for i in range(max(0, len(words) - n + 1)))
        return result

    seen: set[str] = set()
    all_vocab = [("character name", story_chars), ("location", story_locs)]
    raw_lower_words = raw_text.lower().split()

    # ── Strategy 1: phrase-level n-gram (preferred) ───────────────────────────
    phrase_story_terms = [
        (label, term)
        for label, vocab in all_vocab
        for term in vocab
        if len(term.split()) >= 3
    ]
    phrase_suggestions: list[dict] = []

    if phrase_story_terms:
        best_per_term: dict[str, tuple[str, float, str]] = {}
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        for line in lines:
            for n in range(2, 6):
                for ngram in _subsentence_ngrams(line, n):
                    if not _has_content(ngram):
                        continue
                    nl = ngram.lower()
                    if nl in seen or nl in protected:  # entity-safety gate
                        continue
                    for label, term in phrase_story_terms:
                        char_sim   = _sim(ngram, term)
                        word_cov   = _best_word_coverage(ngram, term)
                        base_score = max(char_sim, word_cov)
                        if base_score < 0.65 or base_score >= 1.0:
                            continue
                        if _meaningful_match_count(ngram, term) < 2:
                            continue
                        score = min(1.0, base_score * (1 + 0.2 * _ms_freq(term)))
                        prev  = best_per_term.get(term)
                        if prev is None or score > prev[1]:
                            best_per_term[term] = (ngram, score, label)

        for term, (ngram, score, label) in sorted(
            best_per_term.items(), key=lambda kv: -kv[1][1]
        ):
            nl = ngram.lower()
            if nl in seen or nl in protected:  # entity-safety gate
                continue
            seen.add(nl)
            phrase_suggestions.append({
                "original":   ngram,
                "suggested":  term,
                "reason":     f"Phrase-level match — possible {label} from your manuscript.",
                "confidence": round(score, 2),
            })

    # ── Strategy 2: single capitalised word ───────────────────────────────────
    word_suggestions: list[dict] = []
    single_caps = [
        w for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", raw_text)
        if w not in NOT_PROPER and w.lower() not in COMMON_GENERIC
    ]

    for word in single_caps:
        wl = word.lower()
        if wl in seen or wl in protected:  # entity-safety gate
            continue

        ctx_count = raw_lower_words.count(wl)
        ctx_bonus = 0.1 if ctx_count >= 2 else 0.0

        best_term  = None
        best_score = 0.0
        best_label = ""
        for label, vocab in all_vocab:
            for term in vocab:
                if len(term.split()) > 1 and _literal_word_in_term(word, term):
                    continue
                base_sim = _sim(word, term)
                if 0.60 <= base_sim < 1.0:
                    score = min(1.0, base_sim * (1 + 0.2 * _ms_freq(term)) + ctx_bonus)
                    if score > best_score:
                        best_score = score
                        best_term  = term
                        best_label = label
        if best_term:
            seen.add(wl)
            word_suggestions.append({
                "original":   word,
                "suggested":  best_term,
                "reason":     f"Possible {best_label} — similar term in your manuscript.",
                "confidence": round(best_score, 2),
            })

    phrase_suggestions.sort(key=lambda x: -x["confidence"])
    word_suggestions.sort(key=lambda x: -x["confidence"])
    # Apply entity-safety post-filter as an extra safety net, then return.
    raw_out = (phrase_suggestions + word_suggestions)[:8]
    return _apply_entity_safety_filter(raw_out, registry, protected)


async def generate_ocr_suggestions(raw_text: str, story_id: str, db) -> list[dict]:
    """
    Entity-safe OCR correction suggestions.

    Step 1 — Entity Registry (from ChapterSummary):
      Build {canonical_entity: type} from all indexed chapters.

    Step 2 — Protected Span Detection:
      Slide a 1–6 word window over the OCR text.  Any span that matches a
      registry entity at exact / normalized / high-similarity (≥ 0.90) level
      is added to the protected set.  Protected spans will never receive a
      replacement suggestion — they are already valid story entities.

    Step 3A — BGE-M3 + Qwen (when chapters are indexed):
      Retrieve the top-4 most relevant chapter chunks via BGE-M3.
      Build a Qwen prompt that includes the entity registry AND the protected
      spans explicitly.  Qwen is instructed not to suggest corrections for
      any protected span and not to replace one entity with another.
      Qwen output is then validated through _apply_entity_safety_filter.

    Step 3B — Difflib fallback (when no chapters are indexed):
      _suggest_difflib() with the same registry and protected set.
      Protected spans are skipped in both phrase and single-word strategies.

    All three entity-safety rules are enforced at every step:
      Rule 1: suggestion.original is in protected → DISCARD
      Rule 2: suggestion.original has ≥ 0.90 similarity to any entity → DISCARD
      Rule 3: suggestion.suggested is not in the entity registry → DISCARD

    All suggestions remain optional — Apply/Ignore workflow, never auto-applied.
    No story-specific terms hardcoded anywhere.
    """
    if not raw_text or not raw_text.strip():
        return []

    # Step 1: Entity registry
    registry, term_chapter_count, n_summaries = _build_entity_registry(story_id, db)
    if not registry:
        logger.info("[ocr_suggestions] No entities in registry yet — no suggestions generated")
        return []

    # Step 2: Protected spans
    protected = _find_protected_spans(raw_text, registry)
    if protected:
        sample = list(protected)[:6]
        logger.info(f"[ocr_suggestions] {len(protected)} protected span(s): {sample}")

    # Step 3A: BGE-M3 retrieval + Qwen
    try:
        chunks = await retrieve_chunks_from_store(raw_text, story_id, db, top_k=4)
    except Exception as exc:
        logger.warning(f"[ocr_suggestions] BGE-M3 retrieval failed ({exc}) — using difflib fallback")
        chunks = []

    if not chunks:
        logger.info("[ocr_suggestions] No indexed chunks — using difflib fallback")
        return _suggest_difflib(raw_text, registry, protected, term_chapter_count, n_summaries)

    # Build entity registry section for Qwen
    chars = sorted(e for e, t in registry.items() if t == "character")
    locs  = sorted(e for e, t in registry.items() if t == "location")
    reg_block = ""
    if chars:
        reg_block += f"Characters: {', '.join(chars[:25])}\n"
    if locs:
        reg_block += f"Locations:  {', '.join(locs[:25])}\n"

    # Build protected spans section for Qwen
    if protected:
        prot_block = "\n".join(f"  • {span}" for span in sorted(protected)[:20])
    else:
        prot_block = "  (none)"

    context_blocks = "\n\n".join(
        f"[Chapter {c['chapter']} | relevance {c['score']:.2f}]\n{c['text'][:400]}"
        for c in chunks
    )

    system = (
        "You are an OCR correction assistant for a handwritten manuscript.\n\n"
        "ENTITY SAFETY RULES — these override everything else:\n"
        "1. PROTECTED SPANS listed below already match known manuscript entities.\n"
        "   You MUST NOT suggest any correction for a protected span.\n"
        "2. Never replace one valid entity with a different valid entity.\n"
        "   Example of a forbidden suggestion: 'B-204 Uncle' → 'Mr. Dinesh'\n"
        "   (both are valid entities; swapping them corrupts the manuscript).\n"
        "3. A correction is only valid when the OCR token is NOT a protected span\n"
        "   and shows clear character-level corruption of a registry entity\n"
        "   (e.g. letter substitution, insertion, deletion, OCR noise).\n"
        "4. The suggested replacement MUST appear in the ENTITY REGISTRY below.\n"
        "5. Never suggest corrections for common English words.\n"
        "6. Return ONLY valid JSON — a list of objects with keys:\n"
        '   "original" (OCR word/phrase), "suggested" (exact registry entity),\n'
        '   "reason" (one sentence), "confidence" (float 0.0–1.0).\n'
        "7. Return [] if no safe corrections exist.\n"
        "8. Maximum 6 suggestions. These are shown to the author — never auto-applied."
    )

    user_prompt = (
        f"ENTITY REGISTRY:\n{reg_block}\n"
        f"PROTECTED SPANS (do NOT suggest corrections for these):\n{prot_block}\n\n"
        f"OCR EXTRACTED TEXT:\n{raw_text}\n\n"
        f"MANUSCRIPT CONTEXT (BGE-M3 semantic search):\n{context_blocks}"
    )

    try:
        raw_response = await _complete(system, user_prompt, temperature=0.0, max_tokens=600)
        suggestions  = _extract_json(raw_response, [])
    except Exception as exc:
        logger.warning(f"[ocr_suggestions] Qwen call failed ({exc}) — using difflib fallback")
        return _suggest_difflib(raw_text, registry, protected, term_chapter_count, n_summaries)

    if not isinstance(suggestions, list):
        logger.info("[ocr_suggestions] Qwen returned non-list — using difflib fallback")
        return _suggest_difflib(raw_text, registry, protected, term_chapter_count, n_summaries)

    # Validate structure
    validated: list[dict] = []
    for s in suggestions[:6]:
        if not isinstance(s, dict):
            continue
        if not all(k in s for k in ("original", "suggested", "reason", "confidence")):
            continue
        try:
            conf = float(s["confidence"])
        except (ValueError, TypeError):
            conf = 0.5
        validated.append({
            "original":   str(s["original"]),
            "suggested":  str(s["suggested"]),
            "reason":     str(s["reason"]),
            "confidence": round(min(1.0, max(0.0, conf)), 2),
        })

    # Apply entity-safety post-filter (three rules)
    safe = _apply_entity_safety_filter(validated, registry, protected)
    logger.info(f"[ocr_suggestions] {len(safe)} safe suggestion(s) "
        f"(Qwen: {len(validated)}, after safety filter: {len(safe)})")
    return safe


# ── Embeddings (BGE-M3) ───────────────────────────────────────────────────────

async def embed_text(text: str) -> list[float]:
    loop = asyncio.get_event_loop()

    def _sync() -> list[float]:
        return get_bge().encode(text, normalize_embeddings=True).tolist()

    return await loop.run_in_executor(_bge_executor, _sync)


# ── Character Mention Indexing ─────────────────────────────────────────────────

import re as _re

def _make_name_pattern(name: str, aliases: list) -> _re.Pattern:
    """
    Build a case-insensitive regex pattern to detect character name/aliases in text.
    Handles possessives ("Ravi's"), word boundaries, and multi-word names.
    """
    candidates = [name.strip()] + [a.strip() for a in (aliases or []) if a.strip()]
    # Sort longest first so multi-word names match before single-word components
    candidates = sorted(set(candidates), key=len, reverse=True)
    patterns = []
    for n in candidates:
        escaped = _re.escape(n)
        # \b boundary + optional possessive suffix
        patterns.append(r'\b' + escaped + r"(?:'s|s')?\b")
    return _re.compile('|'.join(patterns), _re.IGNORECASE | _re.UNICODE) if patterns else None


async def index_character_mentions(
    chapter_id: str,
    story_id: str,
    chapter_number: int,
    db,
) -> dict:
    """
    Scan all chunks of a chapter for character name/alias occurrences.
    Records a CharacterMention row for each (character, chunk) pair where the
    character is mentioned.  Also sets chunk.character_ids and updates
    chapter_summaries.character_ids.

    Clears old mentions for this chapter before re-indexing (idempotent).
    Returns {character_id: mention_count} for logging.
    """
    from models import Character, ChapterChunk, ChapterSummary, CharacterMention

    # Clear old mentions for this chapter (idempotent re-indexing)
    db.query(CharacterMention).filter(CharacterMention.chapter_id == chapter_id).delete()
    db.commit()

    # Load characters and build name → (character_id, pattern) index
    characters = db.query(Character).filter(Character.story_id == story_id).all()
    if not characters:
        return {}

    char_patterns = []
    for char in characters:
        pattern = _make_name_pattern(char.name, char.aliases or [])
        if pattern:
            char_patterns.append((char.character_id, pattern))

    # Load all chunks for this chapter
    chunks = (
        db.query(ChapterChunk)
        .filter(ChapterChunk.chapter_id == chapter_id)
        .order_by(ChapterChunk.chunk_index)
        .all()
    )

    if not chunks:
        return {}

    # For each chunk, find which characters are mentioned
    mention_counts: dict[str, int] = {}
    chapter_character_ids: set[str] = set()

    for chunk in chunks:
        chars_in_chunk: set[str] = set()
        for char_id, pattern in char_patterns:
            if pattern.search(chunk.text):
                chars_in_chunk.add(char_id)
                mention_counts[char_id] = mention_counts.get(char_id, 0) + 1

        if not chars_in_chunk:
            chunk.character_ids = []
            continue

        # Update chunk metadata
        chunk.character_ids = list(chars_in_chunk)
        chapter_character_ids.update(chars_in_chunk)

        # Record a mention row for each character found in this chunk
        for char_id in chars_in_chunk:
            co_ids = [c for c in chars_in_chunk if c != char_id]
            db.add(CharacterMention(
                character_id     = char_id,
                story_id         = story_id,
                chapter_id       = chapter_id,
                chunk_id         = chunk.chunk_id,
                chapter_number   = chapter_number,
                passage_text     = chunk.text,
                mention_type     = "reference",
                co_character_ids = co_ids,
            ))

    # Update chapter summary character_ids
    summary = db.query(ChapterSummary).filter(
        ChapterSummary.chapter_id == chapter_id
    ).first()
    if summary:
        summary.character_ids = list(chapter_character_ids)

    db.commit()

    if mention_counts:
        logger.info(f"[mention_index] ch{chapter_number} ({chapter_id[:8]}...): "
            f"{sum(mention_counts.values())} mention(s) for "
            f"{len(mention_counts)} character(s): "
            f"{ {k[:6]: v for k, v in mention_counts.items()} }")
    return mention_counts


async def update_mention_embedding(character_id: str, story_id: str, db) -> bool:
    """
    Compute a story-grounded BGE-M3 embedding from the character's mentions.
    Selects up to 10 diverse mentions (spread across chapters) and embeds
    the concatenated passage texts.

    Returns True if embedding was updated, False if no mentions exist.
    """
    from models import CharacterMention, CharacterProfile

    # Fetch mentions ordered by chapter so we can sample diverse chapters
    all_mentions = (
        db.query(CharacterMention)
        .filter(
            CharacterMention.character_id == character_id,
            CharacterMention.story_id     == story_id,
        )
        .order_by(CharacterMention.chapter_number, CharacterMention.mention_id)
        .all()
    )

    if not all_mentions:
        return False

    # Select up to 10 diverse mentions: at most 2 per chapter
    selected = []
    chapter_counts: dict[int, int] = {}
    for m in all_mentions:
        ch = m.chapter_number
        if chapter_counts.get(ch, 0) < 2:
            selected.append(m)
            chapter_counts[ch] = chapter_counts.get(ch, 0) + 1
        if len(selected) >= 10:
            break

    # Build combined text — truncate each passage to ~120 words to stay in BGE-M3 range
    parts = []
    for m in selected:
        words = m.passage_text.split()
        excerpt = " ".join(words[:120]) if len(words) > 120 else m.passage_text
        parts.append(f"[Ch{m.chapter_number}] {excerpt}")

    combined = "\n".join(parts)
    if not combined.strip():
        return False

    emb = await embed_text(combined)

    profile = db.query(CharacterProfile).filter(
        CharacterProfile.character_id == character_id
    ).first()
    if profile:
        profile.mention_embedding = emb
        profile.updated_at = datetime.utcnow()
        db.commit()
        logger.info(f"[mention_embed] char {character_id[:8]}...: "
            f"mention_embedding updated from {len(selected)} mention(s)")
        return True

    return False


def _get_recent_mentions(
    character_id: str,
    story_id: str,
    db,
    top_k: int = 2,
) -> list[tuple[int, str]]:
    """
    Return (chapter_number, passage_excerpt) tuples for the most recent
    chapters where this character appears.  Used for story evidence in prompts.
    Excerpts are capped at 150 words.
    """
    from models import CharacterMention

    # Get distinct recent chapters for this character
    mentions = (
        db.query(CharacterMention)
        .filter(
            CharacterMention.character_id == character_id,
            CharacterMention.story_id     == story_id,
        )
        .order_by(CharacterMention.chapter_number.desc())
        .limit(top_k * 3)  # fetch extra; deduplicate by chapter below
        .all()
    )

    seen_chapters: set[int] = set()
    result: list[tuple[int, str]] = []
    for m in mentions:
        if m.chapter_number in seen_chapters:
            continue
        seen_chapters.add(m.chapter_number)
        words = m.passage_text.split()
        excerpt = " ".join(words[:150]) if len(words) > 150 else m.passage_text
        result.append((m.chapter_number, excerpt.strip()))
        if len(result) >= top_k:
            break

    return result


# ── Character Enrichment ───────────────────────────────────────────────────────

async def enrich_character_from_story(
    character_id: str,
    story_id: str,
    db,
) -> list[dict]:
    """
    Extract structured profile suggestions for a character from their story mentions.
    Returns a list of {field, value, evidence, chapter, confidence} dicts.
    The caller (router) returns these to the author for review — nothing is auto-applied.
    """
    from models import CharacterMention, Character

    char = db.query(Character).filter(Character.character_id == character_id).first()
    if not char:
        return []

    # Fetch up to 30 diverse mentions (max 3 per chapter)
    all_mentions = (
        db.query(CharacterMention)
        .filter(
            CharacterMention.character_id == character_id,
            CharacterMention.story_id     == story_id,
        )
        .order_by(CharacterMention.chapter_number, CharacterMention.mention_id)
        .all()
    )

    if not all_mentions:
        return []

    selected = []
    ch_counts: dict[int, int] = {}
    for m in all_mentions:
        if ch_counts.get(m.chapter_number, 0) < 3:
            selected.append(m)
            ch_counts[m.chapter_number] = ch_counts.get(m.chapter_number, 0) + 1
        if len(selected) >= 30:
            break

    # Build passage block for LLM
    passage_blocks = []
    for m in selected:
        words = m.passage_text.split()
        excerpt = " ".join(words[:120]) if len(words) > 120 else m.passage_text
        passage_blocks.append(f"[Chapter {m.chapter_number}]\n{excerpt}")

    combined_passages = "\n\n".join(passage_blocks)

    system = (
        f'You are a literary analyst extracting structured character information.\n'
        f'Analyze the provided story passages about "{char.name}" and extract facts.\n'
        f'Return ONLY a valid JSON array. Each element must be an object with keys:\n'
        f'  "field": one of appearance|personality|goals|motivations|backstory|arc_notes|traits\n'
        f'  "value": the extracted fact or description (string; for traits: comma-separated list)\n'
        f'  "evidence": exact quote or close paraphrase from the passage supporting this (string, max 80 words)\n'
        f'  "chapter": chapter number where this evidence appears (integer)\n'
        f'  "confidence": float 0.0-1.0 (1.0 = explicit statement, 0.5 = inferred)\n\n'
        f'Rules:\n'
        f'- Only extract what is explicitly stated or strongly implied in the passages\n'
        f'- Do not invent facts not present in the text\n'
        f'- Prefer concrete facts over vague generalities\n'
        f'- For "traits": extract personality adjectives as a comma-separated string\n'
        f'- Return [] if no clear facts can be extracted\n'
        f'- Return ONLY the JSON array, no other text'
    )

    raw = await _complete(
        system,
        f"Character name: {char.name}\n\nStory passages:\n\n{combined_passages}",
        temperature=0.1,
        max_tokens=1500,
    )

    result = _extract_json(raw, [])
    if not isinstance(result, list):
        logger.info("[enrich] LLM returned non-list for character %s (chars=%d)",
                    character_id[:8], len(raw or ""))
        return []

    chapters_covered = list({m.chapter_number for m in selected})
    logger.info(f"[enrich] {char.name}: {len(result)} suggestion(s) from "
        f"{len(selected)} mention(s) across chapters {sorted(chapters_covered)}")
    return result


# ── Character Arc Timeline ─────────────────────────────────────────────────────

_ARC_TIMELINE_RICH_CUTOFF  = 20
_ARC_TIMELINE_MAX_CHAPTERS = 30


async def build_character_arc_timeline(
    character_id: str,
    story_id:     str,
    db,
) -> list[dict]:
    """
    Produce per-chapter arc snapshots for one character from their story evidence.

    For each chapter where the character appears (via ChapterSummary.character_ids),
    collects up to 3 CharacterMention passages (80-word excerpts) plus the chapter
    raw_summary (≤20 chapters) or structured fields only (>20 chapters) to stay
    within the context window, then asks Qwen to describe the character's state,
    role, and arc development in that chapter.

    Returns list[dict] ordered by chapter_number:
        {chapter_number, chapter_id, role_in_chapter, emotional_state,
         key_action, development_note, status_change, mention_count}

    mention_count = number of CharacterMention rows used for that chapter.
    Stored in the snapshot so future code can compare the current mention count
    against this value to detect staleness without re-running the analysis.
    The unique constraint on (character_id, chapter_id) in the snapshot table
    allows future code to regenerate individual chapters without a full rebuild.
    """
    from models import Character, CharacterMention, ChapterSummary

    char = db.query(Character).filter(Character.character_id == character_id).first()
    if not char:
        return []

    # Chapters where this character appears, ordered chronologically
    summaries = (
        db.query(ChapterSummary)
        .filter(ChapterSummary.story_id == story_id)
        .order_by(ChapterSummary.chapter_number)
        .all()
    )
    relevant = [s for s in summaries if character_id in (s.character_ids or [])]
    if not relevant:
        return []

    capped = relevant[:_ARC_TIMELINE_MAX_CHAPTERS]
    rich   = len(capped) <= _ARC_TIMELINE_RICH_CUTOFF

    chapter_ids = {s.chapter_id for s in capped}

    # Load all mentions for this character in the selected chapters
    all_mentions = (
        db.query(CharacterMention)
        .filter(
            CharacterMention.character_id == character_id,
            CharacterMention.story_id     == story_id,
            CharacterMention.chapter_id.in_(chapter_ids),
        )
        .order_by(CharacterMention.chapter_number, CharacterMention.mention_id)
        .all()
    )

    mentions_by_chapter: dict[str, list] = {}
    for m in all_mentions:
        mentions_by_chapter.setdefault(m.chapter_id, []).append(m)

    # Build per-chapter blocks for Qwen
    chapter_blocks: list[str] = []
    chapter_mention_counts: dict[str, int] = {}

    for s in capped:
        ch_mentions = mentions_by_chapter.get(s.chapter_id, [])
        selected    = ch_mentions[:3]
        chapter_mention_counts[s.chapter_id] = len(selected)

        passages = []
        for m in selected:
            words   = m.passage_text.split()
            excerpt = " ".join(words[:80]) if len(words) > 80 else m.passage_text
            passages.append(f"  - {excerpt}")

        block = f"[Chapter {s.chapter_number}]"
        if rich and s.raw_summary:
            block += f"\nSummary: {s.raw_summary[:300]}"
        if passages:
            block += "\nPassages:\n" + "\n".join(passages)
        else:
            block += "\n(No direct mention passages found for this chapter)"
        chapter_blocks.append(block)

    system = (
        f'You are a literary analyst tracking "{char.name}\'s" journey across chapters.\n\n'
        f'Analyze the provided chapter evidence and return ONLY a valid JSON array.\n'
        f'Each element represents ONE chapter. Required keys:\n'
        f'  "chapter_number": integer\n'
        f'  "role_in_chapter": exactly one of:\n'
        f'    "major_player"   — drives a key event or makes a significant decision\n'
        f'    "turning_point"  — this chapter fundamentally shifts their arc\n'
        f'    "observer"       — present and active but not the focus\n'
        f'    "brief_mention"  — minor presence, little story impact\n'
        f'  "emotional_state": 1-2 sentences on their emotional state in this chapter\n'
        f'  "key_action": one sentence — the most significant thing they do or endure\n'
        f'  "development_note": 1-2 sentences on how this chapter advances, complicates, or stalls their arc\n'
        f'  "status_change": brief string if something definitively changed '
        f'(e.g. "revealed as traitor", "mortally wounded"), or null if nothing changed\n\n'
        f'Rules:\n'
        f'- Use ONLY the passages and summaries provided. Do not invent events.\n'
        f'- Every chapter_number MUST be an actual chapter number from the data below.\n'
        f'- One element per chapter, ordered by chapter_number ascending.\n'
        f'- Return ONLY the JSON array, no other text.'
    )

    cap_note = ""
    if len(relevant) > _ARC_TIMELINE_MAX_CHAPTERS:
        cap_note = (
            f" Chapter cap applied — chapters {_ARC_TIMELINE_MAX_CHAPTERS + 1}+ "
            "not included in this pass."
        )

    raw    = await _complete(
        system,
        f"Character: {char.name}\n\nChapter evidence:\n\n" + "\n\n".join(chapter_blocks),
        temperature=0.1,
        max_tokens=2000,
    )
    result = _extract_json(raw, [])

    if not isinstance(result, list):
        logger.info("[arc_timeline] Qwen returned non-list for character %s (chars=%d)",
                    character_id[:8], len(raw or ""))
        return []

    chnum_to_id    = {s.chapter_number: s.chapter_id for s in capped}
    chnum_to_count = {s.chapter_number: chapter_mention_counts.get(s.chapter_id, 0) for s in capped}
    valid_roles    = {"major_player", "observer", "turning_point", "brief_mention"}

    snapshots: list[dict] = []
    for item in result:
        try:
            chnum = int(item.get("chapter_number", 0))
            ch_id = chnum_to_id.get(chnum)
            if not ch_id:
                continue
            role = str(item.get("role_in_chapter", "observer"))
            if role not in valid_roles:
                role = "observer"
            snapshots.append({
                "chapter_number":   chnum,
                "chapter_id":       ch_id,
                "role_in_chapter":  role,
                "emotional_state":  str(item.get("emotional_state",  "") or "").strip(),
                "key_action":       str(item.get("key_action",        "") or "").strip(),
                "development_note": str(item.get("development_note",  "") or "").strip(),
                "status_change":    item.get("status_change") or None,
                "mention_count":    chnum_to_count.get(chnum, 0),
            })
        except Exception as exc:
            logger.warning(f"[arc_timeline] Skipping malformed snapshot item: {exc}")

    mode_note = "rich" if rich else "compact"
    logger.info(f"[arc_timeline] {char.name}: {len(snapshots)} snapshot(s) across "
        f"{len(capped)} chapter(s) — mode={mode_note}{cap_note}")
    return snapshots


async def _detect_new_character_hints(
    story_id: str,
    chapter_id: str,
    chapter_number: int,
    characters_present: list,
    db,
) -> int:
    """
    Compare names in chapter summary's characters_present list against
    the known character table.  Names that don't match any existing character
    or alias are added as CharacterHint rows for the author to review.

    Returns number of new hints created.
    """
    from models import Character, CharacterHint
    from services.character_names import (
        hint_is_redundant, known_names as known_names_of, normalise_name,
    )

    if not characters_present:
        return 0

    # Normalisation and the similarity threshold live in services/character_names.py
    # so hint creation and hint reconciliation can never drift apart.
    existing = db.query(Character).filter(Character.story_id == story_id).all()
    known_names: set[str] = known_names_of(existing)

    # Also load existing hints to avoid duplicates
    existing_hints = db.query(CharacterHint).filter(
        CharacterHint.story_id == story_id,
        CharacterHint.is_dismissed == False,  # noqa: E712
    ).all()
    hinted_names: set[str] = {normalise_name(h.suggested_name) for h in existing_hints}

    new_count = 0
    for name in characters_present:
        name = str(name).strip()
        if not name or len(name) < 2:
            continue
        norm = normalise_name(name)
        # Skip if already hinted, or already registered / near-identical to a
        # registered name (creation is deliberately the generous side).
        if norm in hinted_names or hint_is_redundant(name, known_names):
            continue

        db.add(CharacterHint(
            story_id=story_id,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            suggested_name=name,
            context_snippet="",
        ))
        hinted_names.add(norm)
        new_count += 1

    if new_count > 0:
        db.commit()
        logger.info(f"[char_hints] ch{chapter_number}: {new_count} new character hint(s) added")

    return new_count


# ── Chapter Summary ────────────────────────────────────────────────────────────

async def generate_chapter_summary(chapter_text: str, chapter_number: int) -> dict:
    system = (
        "You are a literary analyst. Summarise the chapter and return ONLY valid JSON with these keys:\n"
        "  key_events     (string[]) — every distinct event, problem, conflict, negotiation, "
        "complaint, booking, appointment, or communication chaos; include setup events like how "
        "a character obtained their role; aim for 8–15 items, not just 3–5 highlights\n"
        "  characters_present (string[]) — all named characters\n"
        "  locations      (string[]) — all named locations\n"
        "  timeline_markers (string[]) — time references\n"
        "  emotional_tone (string)\n"
        "  chapter_purpose (string)\n"
        "  raw_summary    (string ≤ 300 words) — comprehensive prose summary\n"
        "Return ONLY the JSON object, no extra text."
    )
    excerpt = chapter_text[:8000]
    result, meta = await complete_structured(
        system, f"Chapter {chapter_number}:\n\n{excerpt}",
        coerce=coerce_chapter_summary,
        temperature=0.0, max_tokens=900, label="chapter_summary",
    )
    if result is None:
        # Still a hard failure, and correctly so: a chapter with no usable
        # summary must not be indexed as if it had one. Every retrieval and
        # grounding feature reads these rows.
        raise ValueError(
            f"Chapter {chapter_number} summary could not be generated. Please try again."
        )
    if meta.degraded:
        logger.warning("[generate_chapter_summary] Ch%s indexed from a degraded summary "
                       "(missing_fields=%d) — retrieval quality for this chapter is reduced",
                       chapter_number, meta.discarded)
    return result


# ── Chunk embedding store ─────────────────────────────────────────────────────

async def embed_and_store_chunks(
    chapter_id: str,
    story_id: str,
    chapter_number: int,
    plain_text: str,
    db,
) -> int:
    """
    Split the chapter's plain text into overlapping ~350-word chunks,
    embed each with BGE-M3, and upsert into chapter_chunks.

    Old chunks for this chapter are deleted first so re-runs stay clean.
    Returns the number of chunks stored.
    """
    from models import ChapterChunk

    # Clear stale chunks
    db.query(ChapterChunk).filter(ChapterChunk.chapter_id == chapter_id).delete()
    db.commit()

    chunks = _chunk_text(plain_text)
    word_total = len(plain_text.split())
    logger.info(f"[chunks] ch{chapter_number} ({chapter_id[:8]}...): "
        f"{word_total} words → {len(chunks)} chunk(s)")

    for i, chunk_text in enumerate(chunks):
        emb = await embed_text(chunk_text)
        db.add(ChapterChunk(
            chapter_id     = chapter_id,
            story_id       = story_id,
            chapter_number = chapter_number,
            chunk_index    = i,
            text           = chunk_text,
            word_count     = len(chunk_text.split()),
            embedding      = emb,
        ))

    db.commit()
    logger.info(f"[chunks] {len(chunks)} chunk(s) stored — ch{chapter_number}")
    return len(chunks)


async def retrieve_chunks_from_store(
    question: str,
    story_id: str,
    db,
    top_k: int = 8,
    max_chapter_number: int | None = None,
) -> list[dict]:
    """
    Embed the question with BGE-M3 and return the top-k most semantically
    relevant paragraph-level chunks across the story.

    max_chapter_number: when provided, only chunks from chapters with
    chapter_number <= max_chapter_number are considered.  None = no filter
    (full-corpus scan — used by OCR suggestion grounding and backward-compat
    callers that don't know the current chapter).

    This is the primary retrieval path for QA mode.
    Works identically whether the story has 3 chapters or 300 — only the
    top-k chunks (by cosine similarity) are returned and passed to Qwen.
    """
    from sqlalchemy import text

    logger.debug(f"[chunk_retrieval] story={story_id[:8]}... — embedding query: {question[:80]!r}")
    q_emb = await embed_text(question)
    q_vec_str = vector_literal(q_emb)

    chapter_filter = "AND chapter_number <= :max_ch" if max_chapter_number is not None else ""
    params: dict = {"q": q_vec_str, "story_id": story_id, "limit": top_k}
    if max_chapter_number is not None:
        params["max_ch"] = max_chapter_number

    rows = db.execute(
        text(f"""
            SELECT chunk_id, chapter_number, chunk_index, text, word_count,
                   {vector_similarity('embedding')} AS score
            FROM chapter_chunks
            WHERE story_id = :story_id
              AND embedding IS NOT NULL
              {chapter_filter}
            ORDER BY {vector_distance('embedding')}
            LIMIT :limit
        """),
        params,
    ).fetchall()

    if not rows:
        logger.info(f"[chunk_retrieval] story={story_id[:8]}... — no indexed chunks found")
        return []

    chapters_hit = sorted({row.chapter_number for row in rows})
    logger.info(f"[chunk_retrieval] top-{len(rows)}: "
        f"scores={[round(float(row.score), 3) for row in rows]}, "
        f"chapters={chapters_hit}")
    best = rows[0]
    logger.info(f"[chunk_retrieval] best: "
        f"ch{best.chapter_number}[chunk {best.chunk_index}]: "
        f"{best.text[:120]!r}")

    return [
        {
            "chapter":     row.chapter_number,
            "chunk_index": row.chunk_index,
            "text":        row.text,
            "word_count":  row.word_count,
            "score":       round(float(row.score), 3),
        }
        for row in rows
    ]


# ── Chapter summary + embedding pipeline ─────────────────────────────────────

async def summarize_and_embed_chapter(
    chapter_id: str,
    story_id: str,
    chapter_number: int,
    content: str,
    db,
) -> None:
    """
    Full indexing pipeline for one chapter (called as a background task):
      1. Strip HTML → plain text
      2. Generate chapter summary via Qwen  (for plot suggestions / story structure)
      3. Embed summary via BGE-M3           (for chapter-level retrieval)
      4. Chunk chapter text → embed each   (for fine-grained QA retrieval)

    content may be raw HTML from TipTap.
    Works for any story — no hardcoded details anywhere.
    """
    from models import ChapterSummary

    # Plain text for summary (single line, no paragraph structure needed)
    plain_flat = _strip_html(content)
    if not plain_flat.strip():
        logger.warning(f"[summary] Ch{chapter_number} ({chapter_id[:8]}...) has no text — skipping.")
        return

    # Para-structured plain text for chunking
    plain_para = _html_to_plain(content)

    logger.info(f"[summary] Ch{chapter_number} ({chapter_id[:8]}... story={story_id[:8]}...): "
        f"{len(plain_flat.split())} words")

    # 1 + 2: summary + summary embedding
    try:
        summary_data = await generate_chapter_summary(plain_flat, chapter_number)
    except ValueError as exc:
        # Qwen returned invalid output — do NOT store or embed anything fake.
        # The chapter remains un-indexed until the next sync-summaries run.
        logger.warning(f"[summary] Ch{chapter_number} ({chapter_id[:8]}...): {exc} — skipping indexing.")
        return
    raw_summary  = summary_data.get("raw_summary", "")

    logger.debug(f"[embedding] BGE-M3 embedding for ch{chapter_number} summary...")
    summary_emb = await embed_text(raw_summary)
    logger.debug(f"[embedding] Summary dim={len(summary_emb)}")

    # Upsert ChapterSummary
    cs = db.query(ChapterSummary).filter(ChapterSummary.chapter_id == chapter_id).first()
    if cs:
        cs.key_events          = summary_data.get("key_events", [])
        cs.characters_present  = summary_data.get("characters_present", [])
        cs.locations           = summary_data.get("locations", [])
        cs.timeline_markers    = summary_data.get("timeline_markers", [])
        cs.emotional_tone      = summary_data.get("emotional_tone", "")
        cs.chapter_purpose     = summary_data.get("chapter_purpose", "")
        cs.raw_summary         = raw_summary
        cs.embedding           = summary_emb
        cs.is_stale            = False
    else:
        cs = ChapterSummary(
            chapter_id         = chapter_id,
            story_id           = story_id,
            chapter_number     = chapter_number,
            key_events         = summary_data.get("key_events", []),
            characters_present = summary_data.get("characters_present", []),
            locations          = summary_data.get("locations", []),
            timeline_markers   = summary_data.get("timeline_markers", []),
            emotional_tone     = summary_data.get("emotional_tone", ""),
            chapter_purpose    = summary_data.get("chapter_purpose", ""),
            raw_summary        = raw_summary,
            embedding          = summary_emb,
        )
        db.add(cs)
    db.commit()

    # 4: fine-grained chunks for QA retrieval
    n_chunks = await embed_and_store_chunks(
        chapter_id, story_id, chapter_number, plain_para, db
    )

    # 5: Index character mentions for this chapter
    mention_counts = await index_character_mentions(
        chapter_id, story_id, chapter_number, db
    )

    # 6: Update mention embeddings for affected characters
    if mention_counts:
        for char_id in mention_counts:
            await update_mention_embedding(char_id, story_id, db)

    # 7: Detect new character names not yet in the character table
    await _detect_new_character_hints(
        story_id, chapter_id, chapter_number,
        summary_data.get("characters_present", []), db
    )

    logger.info(f"[summary] Ch{chapter_number} fully indexed: "
        f"summary + {n_chunks} chunk(s) + {sum(mention_counts.values())} mention(s).")


# ── BGE-M3 semantic retrieval ──────────────────────────────────────────────────

async def retrieve_relevant_chunks(
    question: str,
    story_id: str,
    db,
    top_k: int = 4,
    max_chapter_number: int | None = None,
) -> list[dict]:
    """
    Embed the question with BGE-M3 and return the top-k most semantically
    relevant chapter summaries for the given story, ordered by cosine similarity.

    max_chapter_number: when provided, only summaries for chapters with
    chapter_number <= max_chapter_number are candidates.  None = no filter.

    Returns [] if no summaries with embeddings exist for the story (no context).
    """
    from sqlalchemy import text

    logger.debug(f"[retrieval] story={story_id[:8]}... — embedding query: {question[:80]!r}")
    q_emb = await embed_text(question)
    q_vec_str = vector_literal(q_emb)

    chapter_filter = "AND chapter_number <= :max_ch" if max_chapter_number is not None else ""
    params: dict = {"q": q_vec_str, "story_id": story_id, "limit": top_k}
    if max_chapter_number is not None:
        params["max_ch"] = max_chapter_number

    rows = db.execute(
        text(f"""
            SELECT chapter_number, raw_summary, key_events, characters_present,
                   locations, {vector_similarity('embedding')} AS score
            FROM chapter_summaries
            WHERE story_id = :story_id
              AND embedding IS NOT NULL
              {chapter_filter}
            ORDER BY {vector_distance('embedding')}
            LIMIT :limit
        """),
        params,
    ).fetchall()

    logger.info(f"[retrieval] story={story_id[:8]}... — "
        f"{len(rows)} chapter(s) with embeddings found")

    if not rows:
        return []

    logger.info(f"[retrieval] Top-{len(rows)} results: "
        f"scores={[round(float(row.score), 3) for row in rows]}")
    best = rows[0]
    logger.info(f"[retrieval] Best match — Chapter {best.chapter_number}: "
        f"{best.raw_summary[:150]!r}")

    return [
        {
            "chapter":     row.chapter_number,
            "raw_summary": row.raw_summary,
            "key_events":  row.key_events  or [],
            "characters":  row.characters_present or [],
            "locations":   row.locations   or [],
            "score":       round(float(row.score), 3),
        }
        for row in rows
    ]


# ── Backward-compat shim (ocr.py still calls this; redirects to ocr_service) ─

async def process_ocr_image(image_path: str) -> dict:
    from services.ocr_service import process_ocr_image as _ocr
    return await _ocr(image_path)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 AI Service Functions
# ═══════════════════════════════════════════════════════════════════════════════

# ── P2-01: Emotional Arc Assessment ──────────────────────────────────────────

async def get_arc_assessment(arc_entries: list[dict]) -> str:
    """
    Given a list of {chapter_number, chapter_title, emotional_tone} dicts,
    ask Qwen for a one-paragraph arc assessment describing how the emotional
    trajectory flows across the manuscript.
    """
    tone_lines = "\n".join(
        f"  Chapter {e['chapter_number']} ({e['chapter_title']}): {e['emotional_tone'] or 'unknown'}"
        for e in arc_entries
    )
    system = (
        "You are a literary analyst specialising in narrative structure. "
        "You will receive a chapter-by-chapter emotional tone map and must write "
        "exactly ONE paragraph assessing the emotional arc of the manuscript."
    )
    user = (
        f"Emotional tone per chapter:\n{tone_lines}\n\n"
        "Write a single paragraph (4–6 sentences) describing how the emotional "
        "arc of this manuscript flows: where tension builds, where it plateaus, "
        "where it peaks, and how it resolves. Be specific about chapter numbers."
    )
    return await _complete(system, user, temperature=0.3, max_tokens=300)


# ── P2-02: Chapter Continuation Suggestion ───────────────────────────────────

def _parse_suggestions(raw: str) -> list[dict]:
    """
    Parse a continuation payload into [{direction, text, rationale}].

    Tries the tolerant extractor first, then the narrow unterminated-array
    completion. Returns [] when neither yields a list, which is the caller's
    signal to retry or to report truncation.
    """
    parsed = _extract_json(raw, fallback=None)
    if parsed is None:
        parsed = _close_unterminated_json_array(raw)
    if not isinstance(parsed, list):
        return []
    return [
        {
            "direction": str(item.get("direction", "")),
            "text":      str(item.get("text", "")),
            "rationale": str(item.get("rationale", "")),
        }
        for item in parsed[:3]
        if isinstance(item, dict)
    ]


async def generate_continuations(
    tail_text: str,
    story_context: str,
    character_context: str,
    genre_context: str,
    continuation_length: int = 200,
) -> list[dict]:
    """
    Given the last few paragraphs of a chapter plus manuscript context,
    generate 3 continuation options in different narrative directions.
    Returns [{direction, text, rationale}].
    """
    system = (
        "You are a skilled creative writing assistant helping an author continue their chapter. "
        "You write continuations that are grounded in the author's established narrative — "
        "never invent characters, places, or events not present in the provided context."
    )
    user = (
        f"{genre_context}\n\n"
        f"## Story Context\n{story_context}\n\n"
        f"## Character Context\n{character_context}\n\n"
        f"## Current Chapter — Last Few Paragraphs\n{tail_text}\n\n"
        f"Generate exactly 3 continuation suggestions (each ~{continuation_length} words). "
        "Each must take a distinctly different narrative direction. "
        "Return a JSON array with exactly 3 objects, each having these keys:\n"
        '  "direction": one-line description of the narrative direction (e.g. "Conflict Escalation")\n'
        '  "text": the continuation prose (~' + str(continuation_length) + ' words)\n'
        '  "rationale": one sentence explaining why this direction fits the manuscript\n'
        "Return ONLY the JSON array. No explanation outside it."
    )
    # Generation budget must scale with the request. A fixed 1600 was enough for
    # short (100 w) and medium (200 w) but sat exactly on the requirement for
    # long (350 w): 3 × 350 words ≈ 1420 tokens of prose plus ~175 for the
    # direction/rationale strings and JSON scaffolding. Long therefore truncated
    # intermittently — measured at 1 run in 4 — and a truncated JSON array parsed
    # to [], which was silently padded into three "please retry" cards.
    # 1.9 tokens/word is a measured upper bound for this model on English prose.
    # The 1600 floor keeps short and medium byte-identical to previous behaviour.
    max_tokens = max(1600, int(3 * continuation_length * 1.9) + 400)

    raw, finish_reason = await _complete_ex(
        system, user, temperature=0.8, max_tokens=max_tokens,
    )
    result = _parse_suggestions(raw)

    # Exactly one retry, and only for output that finished normally yet could not
    # be parsed or structurally recovered — that is sampling variance, which a
    # fresh sample clears. Never retry finish_reason="length": the budget is
    # already exhausted, so a second attempt would truncate again and cost ~50s
    # for nothing. Straight-line code, no loop: two attempts is a structural
    # maximum, not a policy.
    if not result and finish_reason == "stop":
        logger.warning(
            "[ai_service] continuation output unparseable at finish_reason=stop "
            "(%d chars, max_tokens=%d) — retrying once",
            len(raw), max_tokens,
        )
        raw, finish_reason = await _complete_ex(
            system, user, temperature=0.8, max_tokens=max_tokens,
        )
        result = _parse_suggestions(raw)

    # Truncation must not be reported as success. Only raise when the budget was
    # actually exhausted AND nothing usable survived — a response that hit the
    # cap but still yielded three complete suggestions is fine to return.
    if not result and finish_reason == "length":
        logger.warning(
            "[ai_service] continuation truncated at max_tokens=%d "
            "(continuation_length=%d) — no parseable suggestions",
            max_tokens, continuation_length,
        )
        raise AIResponseTruncatedError(max_tokens=max_tokens)

    return result


# ── P2-03: Dialogue Voice Consistency Checker ─────────────────────────────────

async def check_dialogue_consistency(
    character_name: str,
    passage_pairs: list[tuple],
) -> list[dict]:
    """
    For each (passage_a, passage_b, chapter_a, chapter_b, sim) pair where
    similarity < threshold, ask Qwen whether the two passages sound like the
    same character and describe the inconsistency.
    Returns [{description}] aligned with the input pairs.
    """
    results = []
    for pa, pb, cha, chb, sim in passage_pairs:
        system = (
            "You are a literary editor checking character voice consistency. "
            "Answer concisely and specifically."
        )
        user = (
            f"Character name: {character_name}\n\n"
            f"Passage A (Chapter {cha}):\n\"{pa}\"\n\n"
            f"Passage B (Chapter {chb}):\n\"{pb}\"\n\n"
            "Do these two passages sound like the same character speaking? "
            "In 1–2 sentences, describe any inconsistency in vocabulary, register, "
            "sentence structure, or personality. If they are actually consistent despite "
            "a low similarity score, say so."
        )
        desc = await _complete(system, user, temperature=0.1, max_tokens=120)
        results.append({"description": desc})
    return results


# ── P2-04: Chapter / Scene Outline Generator ──────────────────────────────────

async def generate_chapter_outline(
    chapter_goal: str,
    scene_count: int,
    story_context: str,
    character_context: str,
    genre_context: str,
) -> list[dict]:
    """
    Generate a scene-by-scene outline for a chapter based on the author's goal
    and the established manuscript context.
    Returns [{scene_number, beat_description, characters_present, location, pacing_note}].
    """
    system = (
        "You are a story structure expert helping an author plan their next chapter. "
        "Generate a concrete, grounded outline using only the characters, locations, "
        "and narrative threads that already exist in the manuscript context provided. "
        "Never invent new characters, places, or events not present in the context."
    )
    user = (
        f"{genre_context}\n\n"
        f"## Story Context\n{story_context}\n\n"
        f"## Character Context\n{character_context}\n\n"
        f"## Author's Chapter Goal\n{chapter_goal}\n\n"
        f"Generate a scene-by-scene outline with exactly {scene_count} beats. "
        "Return a JSON array of objects, each with these keys:\n"
        '  "scene_number": integer starting at 1\n'
        '  "beat_description": 2–3 sentences describing what happens in this scene\n'
        '  "characters_present": array of character names present in this scene\n'
        '  "location": the setting for this scene (one phrase)\n'
        '  "pacing_note": one word or phrase describing the pacing (e.g. "slow build", "high tension", "quiet reflection")\n'
        "Return ONLY the JSON array."
    )
    raw = await _complete(system, user, temperature=0.5, max_tokens=1200)
    parsed = _extract_json(raw, fallback=[])
    if not isinstance(parsed, list):
        parsed = []
    result = []
    for i, item in enumerate(parsed[:scene_count]):
        if isinstance(item, dict):
            chars = item.get("characters_present", [])
            if isinstance(chars, str):
                chars = [c.strip() for c in chars.split(",") if c.strip()]
            result.append({
                "scene_number":      int(item.get("scene_number", i + 1)),
                "beat_description":  str(item.get("beat_description", "")),
                "characters_present": chars if isinstance(chars, list) else [],
                "location":          str(item.get("location", "")),
                "pacing_note":       str(item.get("pacing_note", "")),
            })
    return result


# ── P2-05: Continuity & World Consistency Validator ──────────────────────────

async def check_continuity(
    character_profiles: list[dict],
    chapter_summaries: list[dict],
    story_notes: list[str],
    note_cards: list[str],
) -> tuple[list[dict], DegradedMeta]:
    """
    Synthesise all manuscript data and identify contradictions.

    Returns ``(issues, meta)`` — issues being
    [{type, description, chapter_refs, severity, resolution_hint}].

    The meta is not optional decoration: an empty list used to mean either "your
    manuscript is consistent" or "the model returned something unreadable", and
    the author was shown the first message in both cases. The caller must
    distinguish them. For large manuscripts the caller chunks the data and must
    aggregate the meta across chunks — a failed chunk is a silent hole in the
    analysis otherwise.
    """
    char_block = "\n".join(
        f"- {p['name']}: appearance={p.get('appearance','')}, status={p.get('status','')}, goals={p.get('goals','')}"
        for p in character_profiles
    ) or "(no characters)"

    chap_block = "\n".join(
        f"- Ch{s['chapter_number']}: locations={s.get('locations','')}, "
        f"characters_present={s.get('characters_present','')}, "
        f"key_events={s.get('key_events','')}"
        for s in chapter_summaries
    ) or "(no summaries)"

    notes_block = "\n".join(f"- {n}" for n in story_notes[:20]) or "(none)"
    cards_block  = "\n".join(f"- {c}" for c in note_cards[:20]) or "(none)"

    system = (
        "You are a continuity editor reviewing a manuscript for internal contradictions. "
        "Be specific: quote the conflicting facts and cite chapter numbers."
    )
    user = (
        "## Character Profiles\n" + char_block + "\n\n"
        "## Chapter-by-Chapter Summary\n" + chap_block + "\n\n"
        "## World/Story Notes\n" + notes_block + "\n\n"
        "## Location/World Cards\n" + cards_block + "\n\n"
        "Identify contradictions in: character appearance, character locations, "
        "world rules, and timeline. Return a JSON array of objects with keys:\n"
        '  "type": one of character_appearance | character_location | world_rule | timeline\n'
        '  "description": specific description of the contradiction\n'
        '  "chapter_refs": array of chapter numbers involved\n'
        '  "severity": high | medium | low\n'
        '  "resolution_hint": one sentence suggestion for the author\n'
        "If no contradictions found, return an empty array []. "
        "Return ONLY the JSON array."
    )
    issues, meta = await complete_structured(
        system, user,
        coerce=coerce_continuity_issues,
        temperature=0.1,
        max_tokens=1200,
        label="continuity",
    )
    if issues is None:
        # Previously this returned [] — reporting a clean manuscript because the
        # model's output could not be read. That false all-clear is the defect
        # (Phase 2 Issue 14); an empty result now means nothing was found, and
        # a failure says so.
        return [], DegradedMeta(
            True,
            "Some of this manuscript could not be checked — the AI response could "
            "not be read. Please run the check again.",
            meta.attempts, 0,
        )
    return issues, meta


# ── P2-06: Story Bible Generator ─────────────────────────────────────────────

# ── Story bible grounding (task 3.3) ──────────────────────────────────────────

# The exact phrase the model is told to use where the manuscript establishes
# nothing. Fixed and greppable so the honesty convention can be measured rather
# than assumed.
BIBLE_NOT_ESTABLISHED = "Not established in the manuscript"

# Provenance tags the context uses: [Ch 7], [Ch 7-9], [Character: Devika Rao],
# [Note: …], [Card: …].
_PROVENANCE_RE = re.compile(r"\[(?:Ch\s*\d+[\d\s,\-–]*|Character:|Note:|Card:)[^\]]*\]", re.I)
# A generated entry: a bullet, a numbered item, or a "Field: value" line.
_ENTRY_RE = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)")


def audit_section_provenance(text: str) -> dict:
    """
    Count how much of a generated section actually cites its source.

    A quality metric, not a gate: it is logged for diagnostics and regression
    tracking, never shown to the author and never used to reject content. An
    uncited entry is not proof of invention — but a section where most entries
    are uncited is the signature of the gap-filling this task exists to stop.

    Returns {entries, cited, uncited, not_established, cited_ratio}.
    """
    entries = [ln for ln in (text or "").splitlines() if _ENTRY_RE.match(ln)]
    cited = sum(1 for ln in entries if _PROVENANCE_RE.search(ln))
    not_established = (text or "").count(BIBLE_NOT_ESTABLISHED)
    return {
        "entries": len(entries),
        "cited": cited,
        "uncited": len(entries) - cited,
        "not_established": not_established,
        "cited_ratio": round(cited / len(entries), 3) if entries else None,
    }


async def generate_story_bible_section(
    section: str,
    context: str,
) -> tuple[str, Optional[str]]:
    """
    Generate one section of a story bible (characters, locations, timeline,
    world_rules, or themes) from the provided context.

    Returns ``(text, finish_reason)`` — a human-readable formatted string for
    that section, plus vLLM's finish_reason so the caller can tell a complete
    section from a truncated one.

    ``finish_reason == "length"`` means generation stopped at max_tokens and the
    text is cut off mid-sentence. That is invisible from the text alone: it
    arrives looking exactly like success, with no exception raised. Returning it
    unexamined is what let a fragment be persisted as a finished section and the
    bible be marked 'completed' (failure path SB-F13 in
    docs/issues-and-bugs/story-bible-failure-path-audit.md).

    This is why the function delegates to _complete_ex() rather than _complete():
    _complete() discards finish_reason. The Story Bible pipeline is the only
    caller, so the signature was widened in place rather than duplicated.
    """
    # Each instruction states where that section's citations must point, because
    # "cite your source" means something different per section: a timeline entry
    # cites where the event happens, a character trait cites where it is shown.
    section_instructions = {
        # Characters and locations were the two weakest sections for citation
        # (0.00 and 0.33 cited on 2026-07-26, against 1.00 for timeline). The
        # difference was not the model: timeline said MUST, gave a per-line
        # example, and named the consequence. These now say the same.
        "characters": (
            "Write a CHARACTER BIBLE section. For each character, create a compact "
            "reference card: Name, Role, Physical description, Personality, Goals, "
            "Backstory summary, and Arc status. Use '---' between characters.\n"
            "EVERY line MUST end with the source tag it comes from, e.g.\n"
            "  - **Role:** Veritor for the Bureau [Ch 1]\n"
            "  - **Goals:** To prove the memory was forged [Ch 2]\n"
            "Keep each line to one sentence so there is room for its tag. "
            "If a detail is not established anywhere in the context, write "
            f"\"{BIBLE_NOT_ESTABLISHED}\" for that line instead of guessing — "
            "an untagged line is not acceptable."
        ),
        "locations": (
            "Write a LOCATIONS section covering EVERY distinct location that appears "
            "anywhere in the context — do not stop at the first one or two. For each, "
            "write its name as a '####' heading, then bulleted lines beneath it for "
            "Description, Significance and First appearance, with '---' between "
            "locations. Shape (placeholders, not content to copy):\n"
            "#### <location name>\n"
            "  - **Description:** <one or two sentences of what it is> [Ch N]\n"
            "  - **Significance:** <why it matters to the story> [Ch N]\n"
            "  - **First appearance:** [Ch N]\n"
            "EVERY bulleted line MUST end with the chapter tag it comes from. Do not "
            "write a location you cannot attribute to a chapter shown in the context, "
            "and do not leave a line untagged."
        ),
        "timeline": (
            "Write a TIMELINE section: a chronological sequence of key events. "
            "Use bullet points. Every event MUST end with the chapter tag it "
            "happens in, e.g. \"- The archive burns [Ch 7]\". Do not include an "
            "event you cannot attribute to a chapter shown in the context."
        ),
        "world_rules": (
            "Write a WORLD RULES section: list the rules of the story's world — "
            "physical, social, magical, technological, or cultural. Use bullet points.\n"
            "EVERY bullet MUST end with the chapter tag that demonstrates it, e.g.\n"
            "  - Lattice sessions require an induction collar [Ch 1]\n"
            "Do not state a rule you cannot attribute to a chapter shown in the context."
        ),
        "themes": (
            "Write a THEMES & MOTIFS section: identify the primary theme, secondary "
            "themes, recurring motifs, and symbols. Use bullet points. "
            "Cite the chapter tags where each theme or motif is shown."
        ),
    }
    instruction = section_instructions.get(
        section, f"Write a {section.upper()} section for this story."
    )
    system = (
        "You are a story bible author creating a comprehensive reference document for a manuscript. "
        "Be thorough, specific, and ground everything in what is actually in the text. "
        "Do not invent details not supported by the provided context.\n\n"
        # Grounding is enforced by giving the model a way to cite and a way to
        # decline. Telling it not to invent, with no alternative to inventing,
        # is what produced a confident and partly fictional story bible.
        "Every entry in the context is tagged with its source, like [Ch 7] or "
        "[Character: Devika Rao].\n"
        "RULES:\n"
        f"1. Cite the source tag for every factual statement, e.g. \"She burns the archive [Ch 7].\"\n"
        f"2. If the manuscript does not establish something, write exactly "
        f"\"{BIBLE_NOT_ESTABLISHED}\" instead of guessing or filling the gap.\n"
        "3. Never state anything you cannot attribute to a tag shown in the context.\n"
        "4. If the context says material is missing, do not describe that material."
    )
    user = f"{instruction}\n\nManuscript context:\n{context}"
    # Per-line citations add roughly 6-10 tokens per entry. The character card is
    # the longest section and was already close to the old 1500-token ceiling, so
    # requiring tags without more room would simply trade uncited entries for
    # truncated ones (SB-F13). Sections that cite per line get the larger budget.
    max_tokens = 1900 if section in ("characters", "locations") else 1500
    return await _complete_ex(system, user, temperature=0.2, max_tokens=max_tokens)


# ── P2-07: Dead-End Narrative Thread Tracker ──────────────────────────────────

async def extract_narrative_threads_from_summaries(
    chapter_summaries: list[dict],
) -> list[dict]:
    """
    Scan ChapterSummary data (batched up to 5 per call) and extract
    named narrative threads with their status.
    Returns [{thread_name, action, description, chapter_number}].
    """
    # Batch up to 5 chapters per Qwen call to stay within context budget
    all_threads = []
    batch_size = 5
    for i in range(0, len(chapter_summaries), batch_size):
        batch = chapter_summaries[i:i + batch_size]
        batch_text = "\n".join(
            f"Chapter {s['chapter_number']} ({s.get('title','')}):\n"
            f"  Key events: {s.get('key_events', [])}\n"
            f"  Characters: {s.get('characters_present', [])}\n"
            f"  Summary: {s.get('raw_summary', '')[:300]}"
            for s in batch
        )
        system = (
            "You are a narrative analyst extracting story threads from chapter summaries. "
            "A narrative thread is a named subplot, character arc, mystery, quest, "
            "conflict, or recurring motif that spans multiple chapters."
        )
        user = (
            f"{batch_text}\n\n"
            "For each distinct narrative thread you can identify in these chapters, "
            "return one JSON object per action. Return a JSON array of objects with keys:\n"
            '  "thread_name": specific name for the thread (e.g. "The missing crown", "Elena\'s revenge arc")\n'
            '  "action": introduced | developed | resolved\n'
            '  "description": one sentence describing what happens with this thread\n'
            '  "chapter_number": the chapter number\n'
            "Filter out: generic/vague threads shorter than 3 words, "
            "threads matching ['the story', 'the journey', 'the conflict']. "
            "Return ONLY the JSON array. If no threads found, return []."
        )
        raw = await _complete(system, user, temperature=0.1, max_tokens=800)
        parsed = _extract_json(raw, fallback=[])
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and item.get("thread_name"):
                    all_threads.append({
                        "thread_name":    str(item["thread_name"]),
                        "action":         str(item.get("action", "introduced")),
                        "description":    str(item.get("description", "")),
                        "chapter_number": int(item.get("chapter_number", 0)),
                    })
    return all_threads


# ── P2-08: Writing Style Drift Detector ──────────────────────────────────────

async def describe_style_drift(sample_early: str, sample_late: str) -> str:
    """
    Given representative passage samples from early and late chapters,
    ask Qwen to describe the stylistic difference in human terms.
    """
    system = (
        "You are a literary editor analysing writing style consistency. "
        "Compare two writing samples and describe any stylistic differences."
    )
    user = (
        f"Early chapter sample:\n\"{sample_early}\"\n\n"
        f"Late chapter sample:\n\"{sample_late}\"\n\n"
        "Describe the stylistic differences between these two passages in 2–4 sentences. "
        "Consider: sentence length, vocabulary level, narrative distance, POV feel, "
        "use of description, and tone. Be specific about what changed and in which direction."
    )
    return await _complete(system, user, temperature=0.2, max_tokens=200)
