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
from typing import AsyncGenerator, Optional

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
    return _extract_json(raw, {
        "genre": "Literary Fiction", "sub_genre": "Psychological Drama",
        "tone": ["Introspective", "Nuanced"], "audience": audience,
        "structure": "Character study", "conflict": "Internal vs. external",
        "themes": ["Identity", "Human connection"],
        "writing_direction": "Focus on voice and interiority.", "confidence": 0.75,
    })


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
    return [
        {"id": 1, "category": "Prose Quality",    "text": "Vary sentence length deliberately — short sentences build tension.", "reason": "Uniform sentence length reduces rhythmic impact."},
        {"id": 2, "category": "Show Don't Tell",  "text": "Replace emotional labels with physical manifestations.",             "reason": "Current text tells rather than shows."},
        {"id": 3, "category": "Dialogue",          "text": "Add a dialogue beat to reveal character through voice.",            "reason": "Extended prose block could use a break."},
        {"id": 4, "category": "Pacing",            "text": "Expand sensory detail here — the moment feels rushed.",            "reason": "Key beat needs space to land."},
    ]


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


# ── Plot Assistant — direct Q&A answer ────────────────────────────────────────

async def answer_story_question(
    question: str,
    text_chunks: list,
    genre_profile: dict = None,
    current_chapter: str = "",
) -> str:
    """
    Answer a factual question about the story using top-k semantically retrieved
    paragraph-level chunks from chapter_chunks.

    text_chunks comes from retrieve_chunks_from_store().
    Each chunk is a ~350-word passage with a relevance score — exactly the text
    the author wrote, retrieved by BGE-M3 semantic search.

    No story details are hardcoded here.  Works for any author, any genre,
    any language, any number of chapters.
    """
    system = (
        "You are a story knowledge assistant. Answer the writer's question using "
        "ONLY the retrieved story passages provided below — do not invent any "
        "characters, events, or details absent from the passages.\n\n"
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
        parts.append("Characters:\n" + "\n".join(str(c) for c in (character_profiles or [])[:3]))

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
    return [
        {"id": 1, "text": "A secret the protagonist has been hiding surfaces, forcing a reckoning with a key relationship.", "rationale": "Fits established story elements."},
        {"id": 2, "text": "An unexpected visitor arrives carrying information that reframes everything established so far.",   "rationale": "Fits established story elements."},
        {"id": 3, "text": "The antagonist makes their most decisive move, leaving the protagonist with an impossible choice.", "rationale": "Fits established story elements."},
        {"id": 4, "text": "A minor character introduced earlier becomes unexpectedly central to the resolution.",             "rationale": "Fits established story elements."},
    ]


# ── OCR text cleanup (called by ocr_service after TrOCR) ─────────────────────

async def clean_ocr_text(raw_text: str) -> tuple[str, str]:
    """Returns (cleaned_text, note_type)."""
    clean_system = (
        "You are an OCR post-processor for handwritten writer's notes. "
        "Fix spelling, improve formatting, and structure the text. Return ONLY the cleaned text."
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


# ── Embeddings (BGE-M3) ───────────────────────────────────────────────────────

async def embed_text(text: str) -> list[float]:
    loop = asyncio.get_event_loop()

    def _sync() -> list[float]:
        return get_bge().encode(text, normalize_embeddings=True).tolist()

    return await loop.run_in_executor(_bge_executor, _sync)


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
    words = chapter_text.split()
    return {
        "key_events": [f"Primary event of chapter {chapter_number}"],
        "characters_present": ["Protagonist"],
        "locations": ["Primary scene location"],
        "timeline_markers": [f"Chapter {chapter_number}"],
        "emotional_tone": "Neutral",
        "chapter_purpose": f"Advances chapter {chapter_number} arc",
        "raw_summary": f"[Chapter {chapter_number} — {len(words)} words]",
    }


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
) -> list[dict]:
    """
    Embed the question with BGE-M3 and return the top-k most semantically
    relevant paragraph-level chunks across ALL chapters of the story.

    This is the primary retrieval path for QA mode.
    Works identically whether the story has 3 chapters or 300 — only the
    top-k chunks (by cosine similarity) are returned and passed to Qwen.
    """
    import numpy as np
    from models import ChapterChunk

    all_chunks = (
        db.query(ChapterChunk)
        .filter(
            ChapterChunk.story_id  == story_id,
            ChapterChunk.embedding != None,  # noqa: E711
        )
        .all()
    )

    print(
        f"[chunk_retrieval] story={story_id[:8]}... — "
        f"{len(all_chunks)} indexed chunk(s) across all chapters"
    )

    if not all_chunks:
        return []

    print(f"[chunk_retrieval] embedding query: {question[:80]!r}")
    q_emb = await embed_text(question)
    q_vec  = np.array(q_emb, dtype=np.float32)

    scored = []
    for c in all_chunks:
        s_vec = np.array(c.embedding, dtype=np.float32)
        denom = float(np.linalg.norm(q_vec) * np.linalg.norm(s_vec))
        score = float(np.dot(q_vec, s_vec)) / (denom + 1e-9) if denom > 0 else 0.0
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    chapters_hit = sorted({c.chapter_number for _, c in top})
    print(
        f"[chunk_retrieval] top-{len(top)}: "
        f"scores={[round(s, 3) for s, _ in top]}, "
        f"chapters={chapters_hit}"
    )
    if top:
        best = top[0][1]
        print(
            f"[chunk_retrieval] best: "
            f"ch{best.chapter_number}[chunk {best.chunk_index}]: "
            f"{best.text[:120]!r}"
        )

    return [
        {
            "chapter":     c.chapter_number,
            "chunk_index": c.chunk_index,
            "text":        c.text,
            "word_count":  c.word_count,
            "score":       round(score, 3),
        }
        for score, c in top
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
    summary_data = await generate_chapter_summary(plain_flat, chapter_number)
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
    print(
        f"[summary] Ch{chapter_number} fully indexed: "
        f"summary + {n_chunks} chunk(s) stored."
    )


# ── BGE-M3 semantic retrieval ──────────────────────────────────────────────────

async def retrieve_relevant_chunks(
    question: str,
    story_id: str,
    db,
    top_k: int = 4,
) -> list[dict]:
    """
    Embed the question with BGE-M3 and return the top-k most semantically
    relevant chapter summaries for the given story, ordered by cosine similarity.

    Returns [] if no summaries with embeddings exist for the story (no context).
    """
    import numpy as np
    from models import ChapterSummary

    summaries = (
        db.query(ChapterSummary)
        .filter(
            ChapterSummary.story_id == story_id,
            ChapterSummary.embedding != None,  # noqa: E711 — SQLAlchemy IS NOT NULL
        )
        .all()
    )

    print(
        f"[retrieval] story={story_id[:8]}... — "
        f"{len(summaries)} chapter(s) with embeddings found in DB"
    )

    if not summaries:
        return []

    print(f"[retrieval] Embedding query: {question[:80]!r}")
    q_emb = await embed_text(question)
    q_vec  = np.array(q_emb, dtype=np.float32)

    scored = []
    for s in summaries:
        s_vec = np.array(s.embedding, dtype=np.float32)
        denom = float(np.linalg.norm(q_vec) * np.linalg.norm(s_vec))
        score = float(np.dot(q_vec, s_vec)) / (denom + 1e-9) if denom > 0 else 0.0
        scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    print(
        f"[retrieval] Top-{len(top)} results: "
        f"scores={[round(sc, 3) for sc, _ in top]}"
    )
    if top:
        best = top[0][1]
        print(
            f"[retrieval] Best match — Chapter {best.chapter_number}: "
            f"{best.raw_summary[:150]!r}"
        )

    return [
        {
            "chapter":     s.chapter_number,
            "raw_summary": s.raw_summary,
            "key_events":  s.key_events  or [],
            "characters":  s.characters_present or [],
            "locations":   s.locations   or [],
            "score":       round(score, 3),
        }
        for score, s in top
    ]


# ── Backward-compat shim (ocr.py still calls this; redirects to ocr_service) ─

async def process_ocr_image(image_path: str) -> dict:
    from services.ocr_service import process_ocr_image as _ocr
    return await _ocr(image_path)
