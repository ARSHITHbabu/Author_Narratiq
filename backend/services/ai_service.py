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

def _format_character_for_prompt(character, profile) -> str:
    """
    Format a character + profile as a compact, structured Qwen context block.

    raw_notes is intentionally omitted — it is an OCR staging area and may
    contain artefacts, fragments, and uncleaned text that would confuse the
    model.  It is included only as a fallback when ALL structured fields are
    empty (the profile hasn't been curated yet).
    """
    traits_str = ", ".join(profile.traits or [])
    lines = [f"## Character: {character.name}"]
    meta = f"Role: {character.role} | Status: {character.status}"
    if traits_str:
        meta += f" | Traits: {traits_str}"
    lines.append(meta)

    structured_fields = [
        ("Age",          profile.age),
        ("Appearance",   profile.appearance),
        ("Personality",  profile.personality),
        ("Goals",        profile.goals),
        ("Motivations",  profile.motivations),
        ("Backstory",    profile.backstory[:400] if len(profile.backstory or "") > 400
                         else (profile.backstory or "")),
        ("Arc Notes",    profile.arc_notes),
    ]
    has_structured = False
    for label, value in structured_fields:
        if value and value.strip():
            lines.append(f"{label}: {value.strip()}")
            has_structured = True

    # Fallback: include raw_notes only when all structured fields are empty
    if not has_structured and profile.raw_notes and profile.raw_notes.strip():
        lines.append(f"Notes: {profile.raw_notes.strip()[:300]}")

    return "\n".join(lines)


async def retrieve_character_context(
    story_id: str,
    question: str,
    db,
    top_k: int = 3,
    token_budget: int = 800,
) -> list[str]:
    """
    Hybrid character retrieval for Plot Assistant context injection.

    Two retrieval signals are combined:
      1. Name-mention boost — any character whose name or alias appears literally
         in the question text is guaranteed to be included regardless of cosine rank.
      2. Cosine similarity — remaining slots filled by BGE-M3 semantic similarity
         between the question embedding and each CharacterProfile embedding.

    Results are formatted as structured text blocks and capped at token_budget
    (approximated as word_count × 4/3) to stay within Qwen's context window.

    Returns [] when no character profiles with embeddings exist.
    """
    import numpy as np
    from models import Character, CharacterProfile

    characters = (
        db.query(Character)
        .filter(Character.story_id == story_id)
        .all()
    )
    if not characters:
        return []

    # ── Name-mention detection ────────────────────────────────────────────────
    question_lower = question.lower()
    name_mentioned_ids: list[str] = []
    for char in characters:
        if char.name.lower() in question_lower:
            name_mentioned_ids.append(char.character_id)
            continue
        for alias in (char.aliases or []):
            if alias.strip().lower() in question_lower:
                name_mentioned_ids.append(char.character_id)
                break

    # ── Cosine retrieval ──────────────────────────────────────────────────────
    profiles_with_emb = (
        db.query(CharacterProfile)
        .filter(
            CharacterProfile.story_id  == story_id,
            CharacterProfile.embedding != None,  # noqa: E711
        )
        .all()
    )
    profile_map = {p.character_id: p for p in profiles_with_emb}
    char_map    = {c.character_id: c for c in characters}

    cosine_ranked: list[str] = []
    if profiles_with_emb:
        import numpy as np
        q_emb  = await embed_text(question)
        q_vec  = np.array(q_emb, dtype=np.float32)
        scored = []
        for p in profiles_with_emb:
            s_vec = np.array(p.embedding, dtype=np.float32)
            denom = float(np.linalg.norm(q_vec) * np.linalg.norm(s_vec))
            score = float(np.dot(q_vec, s_vec)) / (denom + 1e-9) if denom > 0 else 0.0
            scored.append((score, p.character_id))
        scored.sort(key=lambda x: x[0], reverse=True)
        cosine_ranked = [cid for _, cid in scored]

    # ── Merge: name-mentioned first, then top cosine, deduplicated ────────────
    selected: list[str] = list(name_mentioned_ids)
    for cid in cosine_ranked:
        if cid not in selected:
            selected.append(cid)
        if len(selected) >= top_k:
            break

    # ── Format with token budget enforcement (~1.33 tokens per word) ──────────
    result: list[str] = []
    tokens_used = 0
    for cid in selected:
        char    = char_map.get(cid)
        profile = profile_map.get(cid)
        if not char:
            continue
        if not profile:
            # Character exists but has no profile yet — emit minimal block
            block = f"## Character: {char.name}\nRole: {char.role} | Status: {char.status}"
        else:
            block = _format_character_for_prompt(char, profile)
        block_tokens = len(block.split()) * 4 // 3
        if tokens_used + block_tokens > token_budget:
            break
        result.append(block)
        tokens_used += block_tokens

    if result:
        print(
            f"[char_rag] story={story_id[:8]}... — "
            f"{len(result)} character(s) injected "
            f"({tokens_used}≈tok, name_boost={len(name_mentioned_ids)})"
        )
    return result


# ── Plot Assistant — direct Q&A answer ────────────────────────────────────────

async def answer_story_question(
    question: str,
    text_chunks: list,
    genre_profile: dict = None,
    current_chapter: str = "",
    character_context: list[str] = None,
) -> str:
    """
    Answer a factual question about the story using top-k semantically retrieved
    paragraph-level chunks from chapter_chunks.

    character_context is a list of pre-formatted character profile strings from
    retrieve_character_context().  It is injected only when present, keeping the
    chunk budget for non-character questions fully intact.
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
