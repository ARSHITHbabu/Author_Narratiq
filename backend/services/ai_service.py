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
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Optional

from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer

from config import settings

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


# ── Core inference primitives ─────────────────────────────────────────────────

async def _complete(
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> str:
    """Non-streaming completion. Use for structured JSON outputs."""
    resp = await get_vllm_client().chat.completions.create(
        model=settings.vllm_model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    return resp.choices[0].message.content.strip()


async def _stream_generate(
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 800,
) -> AsyncGenerator[str, None]:
    """
    Streaming completion. Yields token strings as vLLM produces them.
    Caller wraps this in an SSE generator.
    """
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
    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token


def _extract_json(text: str, fallback):
    match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return fallback


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
    audience = audience_hint or "Adult"
    system = (
        "You are a literary genre expert. Analyse the story description and return ONLY a valid JSON "
        "object with keys: genre, sub_genre, tone (string array), audience, structure, conflict, "
        "themes (string array), writing_direction, confidence (float 0–1). No extra text, just JSON."
    )
    raw = await _complete(system, f"Description: {description}\nAudience: {audience}", max_tokens=350)
    result = _extract_json(raw, None)
    if result is None:
        print(f"[detect_genre] Qwen returned invalid JSON. Raw response: {raw[:300]!r}")
        raise ValueError(
            "Genre detection failed: AI model returned invalid output. "
            "Please try again."
        )
    return result


# ── Text Refinement ───────────────────────────────────────────────────────────

_REFINE_MODE = {
    "standard":  "general prose quality and clarity",
    "literary":  "literary richness, voice, and imagery",
    "grammar":   "grammar, punctuation, and sentence structure only",
    "dialogue":  "natural-sounding dialogue and speech rhythm",
}


async def refine_text(text: str, mode: str = "standard", context: str = "") -> str:
    desc = _REFINE_MODE.get(mode, "general prose quality")
    system = (
        f"You are a professional fiction editor specialising in {desc}. "
        "Improve the text while preserving the author's voice. Return ONLY the improved text."
    )
    ctx = f"\n\nManuscript context:\n{context}" if context else ""
    return await _complete(system, text + ctx, temperature=0.3, max_tokens=len(text.split()) * 2 + 150)


async def stream_refine(text: str, mode: str = "standard", context: str = "") -> AsyncGenerator[str, None]:
    desc = _REFINE_MODE.get(mode, "general prose quality")
    system = (
        f"You are a professional fiction editor specialising in {desc}. "
        "Improve the text while preserving the author's voice. Return ONLY the improved text."
    )
    ctx = f"\n\nManuscript context:\n{context}" if context else ""
    async for token in _stream_generate(system, text + ctx, temperature=0.3, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Tone Transformation ────────────────────────────────────────────────────────

async def transform_tone(text: str, tone: str, context: str = "") -> str:
    system = (
        f"You are a literary writing coach. Rewrite the passage in a {tone} tone. "
        "Keep all events and characters identical — only change style, word choice, and mood. "
        "Return ONLY the rewritten passage."
    )
    ctx = f"\n\nStory context:\n{context}" if context else ""
    return await _complete(system, text + ctx, temperature=0.5, max_tokens=len(text.split()) * 2 + 150)


async def stream_tone(text: str, tone: str, context: str = "") -> AsyncGenerator[str, None]:
    system = (
        f"You are a literary writing coach. Rewrite the passage in a {tone} tone. "
        "Keep all events and characters identical — only change style, word choice, and mood. "
        "Return ONLY the rewritten passage."
    )
    ctx = f"\n\nStory context:\n{context}" if context else ""
    async for token in _stream_generate(system, text + ctx, temperature=0.5, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Emotion Rewriting ─────────────────────────────────────────────────────────

async def rewrite_emotion(text: str, emotion: str, intensity: str = "medium") -> str:
    system = (
        f"You are a fiction editor. Rewrite the passage so it deeply conveys {emotion} at "
        f"{intensity} intensity using sensory detail and interiority — not emotional labels. "
        "Return ONLY the rewritten passage."
    )
    return await _complete(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150)


async def stream_emotion(text: str, emotion: str, intensity: str = "medium") -> AsyncGenerator[str, None]:
    system = (
        f"You are a fiction editor. Rewrite the passage so it deeply conveys {emotion} at "
        f"{intensity} intensity using sensory detail and interiority — not emotional labels. "
        "Return ONLY the rewritten passage."
    )
    async for token in _stream_generate(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Age Adaptation ─────────────────────────────────────────────────────────────

_AGE_GUIDE = {
    "children": "children aged 5–10 — simple vocabulary, short sentences, no violence or adult themes",
    "ya":       "young adult readers aged 10–18 — age-appropriate complexity and themes",
    "adult":    "adult readers — full vocabulary and thematic depth",
}


async def adapt_for_age(text: str, target_age: str, context: str = "") -> str:
    guide = _AGE_GUIDE.get(target_age, _AGE_GUIDE["adult"])
    system = (
        f"You are an editor. Adapt the text for {guide}. "
        "Preserve the story meaning. Return ONLY the adapted text."
    )
    ctx = f"\n\nContext:\n{context}" if context else ""
    return await _complete(system, text + ctx, temperature=0.3, max_tokens=len(text.split()) * 2 + 150)


async def stream_age_adapt(text: str, target_age: str, context: str = "") -> AsyncGenerator[str, None]:
    guide = _AGE_GUIDE.get(target_age, _AGE_GUIDE["adult"])
    system = (
        f"You are an editor. Adapt the text for {guide}. "
        "Preserve the story meaning. Return ONLY the adapted text."
    )
    ctx = f"\n\nContext:\n{context}" if context else ""
    async for token in _stream_generate(system, text + ctx, temperature=0.3, max_tokens=len(text.split()) * 2 + 150):
        yield token


# ── Style Transformation ───────────────────────────────────────────────────────

async def transform_style(text: str, style: str) -> str:
    system = (
        f"Rewrite the passage in the literary style of {style} — capturing their characteristic "
        "sentence structure, diction, rhythm, and voice. Return ONLY the rewritten passage."
    )
    return await _complete(system, text, temperature=0.6, max_tokens=len(text.split()) * 2 + 150)


async def stream_style(text: str, style: str) -> AsyncGenerator[str, None]:
    system = (
        f"Rewrite the passage in the literary style of {style} — capturing their characteristic "
        "sentence structure, diction, rhythm, and voice. Return ONLY the rewritten passage."
    )
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

async def extract_cast(chapter_texts: list) -> list:
    """
    Extract named characters and significant recurring persons from story text.
    chapter_texts: list of plain-text strings, one per chapter (already chunked/cleaned).
    Returns a list of dicts with keys: name, role, status, description, aliases,
    first_appearance, evidence_snippet, confidence.
    """
    MAX_WORDS = 8000
    parts = []
    total_words = 0

    for i, text in enumerate(chapter_texts, 1):
        if total_words >= MAX_WORDS:
            break
        words = text.split()
        remaining = MAX_WORDS - total_words
        if len(words) > remaining:
            text = " ".join(words[:remaining]) + " [truncated]"
            words = words[:remaining]
        parts.append(f"=== Chapter {i} ===\n{text}")
        total_words += len(words)

    if not parts:
        return []

    combined = "\n\n".join(parts)

    system = (
        'You are a literary analyst. Extract all characters from the story text below.\n'
        'Return ONLY a valid JSON array. Each element must be an object with these exact keys:\n'
        '  "name": canonical full name (string)\n'
        '  "role": one of "protagonist", "antagonist", "supporting", "minor"\n'
        '  "status": one of "active", "deceased", "unknown"\n'
        '  "description": 1-2 sentence summary of who this character is (string)\n'
        '  "aliases": other names this character is called by (array of strings, may be empty)\n'
        '  "first_appearance": which chapter this character first appears in (e.g. "Chapter 1")\n'
        '  "evidence_snippet": short quote or paraphrase from the text confirming this character (max 80 words)\n'
        '  "confidence": "high" if the character is clearly named and present; "uncertain" if inferred or ambiguous\n\n'
        'Rules:\n'
        '- Include named individuals AND named groups/collectives that act as characters\n'
        '- Include unnamed but significant recurring characters by their role (e.g. "Ravi\'s Mother")\n'
        '- Do NOT invent characters absent from the text\n'
        '- Return [] if no characters are found\n'
        '- No text outside the JSON array'
    )

    raw = await _complete(system, f"Story text:\n\n{combined}", temperature=0.1, max_tokens=2000)
    result = _extract_json(raw, [])
    if not isinstance(result, list):
        print(f"[extract_cast] LLM returned non-list. Raw: {raw[:200]!r}")
        return []
    print(f"[extract_cast] extracted {len(result)} character(s) from {len(parts)} chapter(s)")
    return result


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
    raw = await _complete(system, "\n\n".join(parts), temperature=0.0, max_tokens=600)
    result = _extract_json(raw, None)
    if isinstance(result, list):
        return result
    print(f"[generate_suggestions] Qwen returned invalid JSON. Raw response: {raw[:300]!r}")
    raise ValueError(
        "Writing suggestions failed: AI model returned invalid output. "
        "Please try again."
    )


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
    print(f"[intent] question={question[:60]!r} → intent={intent!r} (raw={raw.strip()!r})")
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
        q_vec_str = "[" + ",".join(str(v) for v in q_emb) + "]"

        score_rows = db.execute(
            text("""
                SELECT character_id,
                       CASE WHEN embedding IS NOT NULL
                            THEN 1 - (embedding <=> :q::vector)
                            ELSE 0.0 END AS profile_score,
                       CASE WHEN mention_embedding IS NOT NULL
                            THEN 1 - (mention_embedding <=> :q::vector)
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
        print(
            f"[char_rag_v2] story={story_id[:8]}... — "
            f"{len(result)}/{len(characters)} character(s) injected "
            f"({tokens_used}≈tok, name_boost={len(name_mentioned_ids)}, "
            f"has_mention_emb={sum(1 for p in profiles_map.values() if p.mention_embedding)})"
        )
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
    q_vec_str = "[" + ",".join(str(v) for v in q_emb) + "]"

    rows = db.execute(
        text("""
            SELECT 'note' AS kind, note_id AS record_id, title, content,
                   NULL AS card_type,
                   1 - (embedding <=> :q::vector) AS score
            FROM story_notes
            WHERE story_id = :story_id AND embedding IS NOT NULL
            UNION ALL
            SELECT 'card', card_id, title, content, card_type,
                   1 - (embedding <=> :q::vector) AS score
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
        print(
            f"[note_rag] story={story_id[:8]}... — "
            f"{len(result)}/{len(rows)} note(s) injected ({tokens_used}≈tok)"
        )
    return result


# ── Plot Assistant — direct Q&A answer ────────────────────────────────────────

async def answer_story_question(
    question: str,
    text_chunks: list,
    genre_profile: dict = None,
    current_chapter: str = "",
    character_context: list[str] = None,
    note_context: list[str] = None,
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

    if genre_profile:
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
        print(
            f"[qa_answer] {len(text_chunks)} chunk(s), {total_words} words, "
            f"char_ctx={len(character_context or [])}, "
            f"prompt≈{total_chars//4} tokens, max_tokens=900"
        )
    else:
        parts.append(
            "No indexed story passages found for this story. "
            "The author needs to save their chapters and run sync-summaries "
            "so the content can be indexed."
        )
        user_prompt = "\n\n".join(parts)
        print("[qa_answer] No chunks available — answering without story context")

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

    if genre_profile:
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

    if current_chapter:
        parts.append(f"Current chapter excerpt (last 600 chars):\n{current_chapter[-600:]}")

    context_status = (
        f"retrieved_chunks={len(retrieved_chunks) if retrieved_chunks else 0}, "
        f"summaries={len(summaries) if summaries else 0}, "
        f"current_chapter={'yes' if current_chapter else 'no'}"
    )
    print(f"[plot_suggestions] Calling Qwen — {context_status}")

    raw = await _complete(system, "\n\n".join(parts), temperature=0.0, max_tokens=800)
    result = _extract_json(raw, None)
    if isinstance(result, list):
        return result
    print(f"[generate_plot_suggestions] Qwen returned invalid JSON. Raw response: {raw[:300]!r}")
    raise ValueError(
        "Plot suggestion generation failed: AI model returned invalid output. "
        "Please try again."
    )


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

    raw = await _complete(
        system,
        "Story chapters:\n\n" + "\n".join(lines),
        temperature=0.0,
        max_tokens=1400,
    )
    result = _extract_json(raw, None)

    if not isinstance(result, dict) or "issues" not in result:
        print(f"[plot_holes] single_pass: Qwen returned invalid JSON. Raw: {raw[:300]!r}")
        raise ValueError(
            "Plot hole analysis failed: AI model returned invalid output. Please try again."
        )

    return {
        "issues":            result.get("issues", []),
        "note":              cap_note or result.get("note", ""),
        "chapters_analyzed": len(capped),
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

    print(
        f"[plot_holes] story={story_id[:8]}... "
        f"strategy={strategy!r} total_chapters={len(summaries)}"
    )
    result = await fn(summaries)
    print(
        f"[plot_holes] done — "
        f"{result['chapters_analyzed']} analyzed, "
        f"{len(result['issues'])} issue(s) found"
    )
    return result


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
    raw = await _complete(
        system,
        "Manuscript chapters:\n\n" + separator.join(lines),
        temperature=0.1,
        max_tokens=1800,
    )
    result = _extract_json(raw, None)

    if not isinstance(result, dict) or "character_arcs" not in result:
        print(f"[manuscript] summary_pass: Qwen returned invalid JSON. Raw: {raw[:300]!r}")
        raise ValueError(
            "Manuscript analysis failed: AI model returned invalid output. Please try again."
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

    print(
        f"[manuscript] story={story_id[:8]}... "
        f"strategy={strategy!r} total_chapters={len(chapters)}"
    )
    result = await fn(chapters)
    print(
        f"[manuscript] done — "
        f"{result['chapters_analyzed']} analyzed, "
        f"{len(result.get('character_arcs', []))} arc(s), "
        f"{len(result.get('unresolved_threads', []))} thread(s)"
    )
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
        print(
            f"[clean_ocr_text] raw_text too short ({len(raw_text.strip())} chars) — "
            "skipping Qwen call."
        )
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
            print(
                f"[entity_safety] Discarded '{s['original']}' → '{s['suggested']}': "
                "original is a protected entity span (Rule 1)"
            )
            continue

        # Rule 2 — original is a high-similarity form of any registry entity
        max_sim = max(
            (SequenceMatcher(None, orig_lower, e).ratio() for e in registry_lower),
            default=0.0,
        )
        if max_sim >= 0.90:
            print(
                f"[entity_safety] Discarded '{s['original']}' → '{s['suggested']}': "
                f"original matches registry entity at {max_sim:.2f} (Rule 2)"
            )
            continue

        # Rule 3 — suggested replacement must be a known registry entity
        sugg_in_registry = any(
            SequenceMatcher(None, sugg_lower, e).ratio() >= 0.90
            for e in registry_lower
        )
        if not sugg_in_registry:
            print(
                f"[entity_safety] Discarded '{s['original']}' → '{s['suggested']}': "
                "suggested term is not a registry entity (Rule 3)"
            )
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
        print("[ocr_suggestions] No entities in registry yet — no suggestions generated")
        return []

    # Step 2: Protected spans
    protected = _find_protected_spans(raw_text, registry)
    if protected:
        sample = list(protected)[:6]
        print(f"[ocr_suggestions] {len(protected)} protected span(s): {sample}")

    # Step 3A: BGE-M3 retrieval + Qwen
    try:
        chunks = await retrieve_chunks_from_store(raw_text, story_id, db, top_k=4)
    except Exception as exc:
        print(f"[ocr_suggestions] BGE-M3 retrieval failed ({exc}) — using difflib fallback")
        chunks = []

    if not chunks:
        print("[ocr_suggestions] No indexed chunks — using difflib fallback")
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
        print(f"[ocr_suggestions] Qwen call failed ({exc}) — using difflib fallback")
        return _suggest_difflib(raw_text, registry, protected, term_chapter_count, n_summaries)

    if not isinstance(suggestions, list):
        print("[ocr_suggestions] Qwen returned non-list — using difflib fallback")
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
    print(
        f"[ocr_suggestions] {len(safe)} safe suggestion(s) "
        f"(Qwen: {len(validated)}, after safety filter: {len(safe)})"
    )
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
        print(
            f"[mention_index] ch{chapter_number} ({chapter_id[:8]}...): "
            f"{sum(mention_counts.values())} mention(s) for "
            f"{len(mention_counts)} character(s): "
            f"{ {k[:6]: v for k, v in mention_counts.items()} }"
        )
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
        print(
            f"[mention_embed] char {character_id[:8]}...: "
            f"mention_embedding updated from {len(selected)} mention(s)"
        )
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
        print(f"[enrich] LLM returned non-list for {char.name}. Raw: {raw[:200]!r}")
        return []

    chapters_covered = list({m.chapter_number for m in selected})
    print(
        f"[enrich] {char.name}: {len(result)} suggestion(s) from "
        f"{len(selected)} mention(s) across chapters {sorted(chapters_covered)}"
    )
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
        print(f"[arc_timeline] Qwen returned non-list for {char.name}. Raw: {raw[:200]!r}")
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
            print(f"[arc_timeline] Skipping malformed snapshot item: {exc}")

    mode_note = "rich" if rich else "compact"
    print(
        f"[arc_timeline] {char.name}: {len(snapshots)} snapshot(s) across "
        f"{len(capped)} chapter(s) — mode={mode_note}{cap_note}"
    )
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

    if not characters_present:
        return 0

    # Build normalized existing name index (name + aliases)
    existing = db.query(Character).filter(Character.story_id == story_id).all()
    known_names: set[str] = set()
    for c in existing:
        known_names.add(c.name.strip().lower())
        for alias in (c.aliases or []):
            if alias.strip():
                known_names.add(alias.strip().lower())

    # Also load existing hints to avoid duplicates
    existing_hints = db.query(CharacterHint).filter(
        CharacterHint.story_id == story_id,
        CharacterHint.is_dismissed == False,  # noqa: E712
    ).all()
    hinted_names: set[str] = {h.suggested_name.strip().lower() for h in existing_hints}

    new_count = 0
    for name in characters_present:
        name = str(name).strip()
        if not name or len(name) < 2:
            continue
        norm = name.lower()
        # Skip if already in characters table or already hinted
        if norm in known_names or norm in hinted_names:
            continue
        # Simple fuzzy check: skip if very close to a known name (edit distance proxy)
        from difflib import SequenceMatcher
        if any(SequenceMatcher(None, norm, k).ratio() >= 0.85 for k in known_names):
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
        print(f"[char_hints] ch{chapter_number}: {new_count} new character hint(s) added")

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
    raw = await _complete(system, f"Chapter {chapter_number}:\n\n{excerpt}", temperature=0.0, max_tokens=900)
    result = _extract_json(raw, None)
    if isinstance(result, dict):
        return result
    print(
        f"[generate_chapter_summary] Ch{chapter_number}: Qwen returned invalid JSON. "
        f"Raw response: {raw[:300]!r}"
    )
    raise ValueError(
        f"Chapter {chapter_number} summary generation failed: AI model returned invalid output."
    )


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
    print(
        f"[chunks] ch{chapter_number} ({chapter_id[:8]}...): "
        f"{word_total} words → {len(chunks)} chunk(s)"
    )

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
    print(f"[chunks] {len(chunks)} chunk(s) stored — ch{chapter_number}")
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

    print(f"[chunk_retrieval] story={story_id[:8]}... — embedding query: {question[:80]!r}")
    q_emb = await embed_text(question)
    q_vec_str = "[" + ",".join(str(v) for v in q_emb) + "]"

    chapter_filter = "AND chapter_number <= :max_ch" if max_chapter_number is not None else ""
    params: dict = {"q": q_vec_str, "story_id": story_id, "limit": top_k}
    if max_chapter_number is not None:
        params["max_ch"] = max_chapter_number

    rows = db.execute(
        text(f"""
            SELECT chunk_id, chapter_number, chunk_index, text, word_count,
                   1 - (embedding <=> :q::vector) AS score
            FROM chapter_chunks
            WHERE story_id = :story_id
              AND embedding IS NOT NULL
              {chapter_filter}
            ORDER BY embedding <=> :q::vector
            LIMIT :limit
        """),
        params,
    ).fetchall()

    if not rows:
        print(f"[chunk_retrieval] story={story_id[:8]}... — no indexed chunks found")
        return []

    chapters_hit = sorted({row.chapter_number for row in rows})
    print(
        f"[chunk_retrieval] top-{len(rows)}: "
        f"scores={[round(float(row.score), 3) for row in rows]}, "
        f"chapters={chapters_hit}"
    )
    best = rows[0]
    print(
        f"[chunk_retrieval] best: "
        f"ch{best.chapter_number}[chunk {best.chunk_index}]: "
        f"{best.text[:120]!r}"
    )

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
        print(f"[summary] Ch{chapter_number} ({chapter_id[:8]}...) has no text — skipping.")
        return

    # Para-structured plain text for chunking
    plain_para = _html_to_plain(content)

    print(
        f"[summary] Ch{chapter_number} ({chapter_id[:8]}... story={story_id[:8]}...): "
        f"{len(plain_flat.split())} words"
    )

    # 1 + 2: summary + summary embedding
    try:
        summary_data = await generate_chapter_summary(plain_flat, chapter_number)
    except ValueError as exc:
        # Qwen returned invalid output — do NOT store or embed anything fake.
        # The chapter remains un-indexed until the next sync-summaries run.
        print(f"[summary] Ch{chapter_number} ({chapter_id[:8]}...): {exc} — skipping indexing.")
        return
    raw_summary  = summary_data.get("raw_summary", "")

    print(f"[embedding] BGE-M3 embedding for ch{chapter_number} summary...")
    summary_emb = await embed_text(raw_summary)
    print(f"[embedding] Summary dim={len(summary_emb)}")

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

    print(
        f"[summary] Ch{chapter_number} fully indexed: "
        f"summary + {n_chunks} chunk(s) + {sum(mention_counts.values())} mention(s)."
    )


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

    print(f"[retrieval] story={story_id[:8]}... — embedding query: {question[:80]!r}")
    q_emb = await embed_text(question)
    q_vec_str = "[" + ",".join(str(v) for v in q_emb) + "]"

    chapter_filter = "AND chapter_number <= :max_ch" if max_chapter_number is not None else ""
    params: dict = {"q": q_vec_str, "story_id": story_id, "limit": top_k}
    if max_chapter_number is not None:
        params["max_ch"] = max_chapter_number

    rows = db.execute(
        text(f"""
            SELECT chapter_number, raw_summary, key_events, characters_present,
                   locations, 1 - (embedding <=> :q::vector) AS score
            FROM chapter_summaries
            WHERE story_id = :story_id
              AND embedding IS NOT NULL
              {chapter_filter}
            ORDER BY embedding <=> :q::vector
            LIMIT :limit
        """),
        params,
    ).fetchall()

    print(
        f"[retrieval] story={story_id[:8]}... — "
        f"{len(rows)} chapter(s) with embeddings found"
    )

    if not rows:
        return []

    print(
        f"[retrieval] Top-{len(rows)} results: "
        f"scores={[round(float(row.score), 3) for row in rows]}"
    )
    best = rows[0]
    print(
        f"[retrieval] Best match — Chapter {best.chapter_number}: "
        f"{best.raw_summary[:150]!r}"
    )

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
