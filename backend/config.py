"""
Central configuration — all values overridable via environment variables or .env file.

GPU auto-detection (handled by start.sh before FastAPI boots):
  start.sh detects GPU count, selects the correct TENSOR_PARALLEL_SIZE,
  scales MAX_MODEL_LEN to available VRAM, then exports these as env vars
  so FastAPI picks them up here automatically.

  1× RTX 4090 (24 GB)  → TP=1, GPU_UTIL=0.88, MAX_CTX=8192
  2× RTX 4090 (48 GB)  → TP=2, GPU_UTIL=0.90, MAX_CTX=16384
  3× RTX 4090 (72 GB)  → TP=2, GPU_UTIL=0.90, MAX_CTX=16384
                          (TP=3 invalid for Qwen2.5-7B's 4 KV heads)
  4× RTX 4090 (96 GB)  → TP=4, GPU_UTIL=0.90, MAX_CTX=32768

Manual override — set env vars before start.sh:
  TENSOR_PARALLEL_SIZE=2
  GPU_MEMORY_UTILIZATION=0.90
  MAX_MODEL_LEN=32768

Local Windows dev:
  vLLM is Linux/CUDA only. Run the backend pointing at a remote vLLM instance,
  or use WSL2. Set VLLM_BASE_URL to wherever vLLM is reachable.
"""

from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./narratiq.db"
    secret_key: str  # Required — must be set in .env. Generate: python3 -c "import secrets; print(secrets.token_hex(32))"

    # ── Model base directory ──────────────────────────────────────────────────
    # All model subdirs live here.  Set via MODEL_BASE_DIR env var.
    model_base_dir: str = "/workspace/models"

    # ── Hugging Face model IDs ────────────────────────────────────────────────
    # Used by scripts/download_models.sh and as a display reference.
    llm_model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    bge_model_id: str = "BAAI/bge-m3"
    got_ocr_model_id: str = "stepfun-ai/GOT-OCR2_0"
    # Systran/faster-whisper-large-v3-turbo now 401s (gated/removed); use the
    # public byte-identical CTranslate2 mirror as the HF auto-download fallback.
    whisper_model_id: str = "deepdml/faster-whisper-large-v3-turbo-ct2"

    # ── Optional direct local path overrides ──────────────────────────────────
    # If unset, paths are derived: {model_base_dir}/{model-folder-name}
    # Set LLM_MODEL_PATH=/workspace/models/Qwen2.5-7B-Instruct to override.
    llm_model_path: str = ""
    bge_model_path: str = ""

    # ── vLLM server ───────────────────────────────────────────────────────────
    # VLLM_BASE_URL overrides host+port construction.
    # The running vLLM instance listens on 9001 (see start-narratiq.sh and
    # CLAUDE.md). The default matches that port so the backend reaches the model
    # even if VLLM_BASE_URL is omitted from .env. Override in .env if needed.
    vllm_base_url: str = "http://127.0.0.1:9001/v1"
    # Name vLLM was started with via --served-model-name.
    # Must match exactly what the OpenAI client sends as `model=`.
    vllm_model_name: str = "Qwen/Qwen2.5-7B-Instruct"

    # ── GPU / vLLM launch config (read by start.sh) ──────────────────────────
    gpu_memory_utilization: float = 0.88
    tensor_parallel_size: int = 1
    max_model_len: int = 8192

    # ── Embedding model device ────────────────────────────────────────────────
    # "cpu"  — safe default; BGE-M3 ~80–150 ms/query on CPU, acceptable.
    # "cuda" — use only when GPU has headroom above gpu_memory_utilization.
    bge_device: str = "cpu"

    # ── Whisper (faster-whisper) settings ─────────────────────────────────────
    # "cpu" is safe; set "cuda" when GPU VRAM headroom allows.
    # compute_type: "int8" for CPU (fastest), "float16" for GPU.
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # ── FastAPI server ────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # All limits follow slowapi's string format: "N/period" where period is
    # second | minute | hour | day. Redis-upgradeable: set SLOWAPI_STORAGE_URI.
    rate_limit_auth:          str = "5/minute"    # per IP — /login, /register
    rate_limit_realtime_ai:   str = "20/minute"   # per user — refine, tone, etc.
    rate_limit_heavy_ai:      str = "5/minute"    # per user — continuity, plot-holes
    rate_limit_background_ai: str = "3/minute"    # per user — bible, threads scan
    rate_limit_upload:        str = "10/minute"   # per user — audio, OCR, manuscript
    rate_limit_voice:         str = "30/minute"   # per user — voice interpret / transcribe

    # ── Upload size limits ────────────────────────────────────────────────────
    max_audio_upload_mb:      int = 100   # audio files (mp3, wav, m4a, …)
    max_ocr_upload_mb:        int = 50    # OCR images (jpg, png, webp, heic)
    max_manuscript_upload_mb: int = 25    # DOCX / TXT manuscripts

    # ── Storage paths ─────────────────────────────────────────────────────────
    # Relative to the backend working directory. Change here (or via env) to
    # point at a mounted volume or object storage path. S3 migration: swap these
    # for bucket/prefix values and update the StorageBackend implementation.
    upload_dir_audio: str = "uploads/audio"
    upload_dir_ocr:   str = "uploads/ocr"

    # ── Background AI concurrency ─────────────────────────────────────────────
    # Hard cap on simultaneous background Qwen calls so foreground (realtime)
    # requests are not starved. Raise via BG_AI_CONCURRENCY env var when needed.
    # Celery migration: replace semaphore with worker concurrency setting.
    bg_ai_concurrency:     int = 3   # Qwen background tasks
    embedding_concurrency: int = 2   # BGE-M3 background embedding tasks

    # ── Real-Time Voice Agent ─────────────────────────────────────────────────
    # Master feature flag. When False the WS/REST voice endpoints return 404-style
    # disabled responses and the frontend hides the panel (safe rollout / rollback).
    voice_agent_enabled: bool = True

    # ── Transform prompt versioning (Stage 5, task 5.1) ────────────────────────
    # Selects which entry in services.prompt_registry.PROMPT_REGISTRY builds the
    # system prompt for every transform (tone/emotion/audience/style/author-style/
    # translate) and generate_suggestions. "v1" is the frozen pre-Stage-5 baseline,
    # byte-identical to what shipped before this task. Reverting to a prior version
    # is this env var, not a code change (task 5.1's own definition of done). An
    # unknown version fails safe: services.prompt_registry.resolve_prompt_version()
    # logs an error and falls back to prompt_version_fallback, never to arbitrary
    # or partially-applied prompt content.
    # v2 is Stage 5's improved prompt set (tasks 5.7-5.11 — see
    # prompt_registry.py's v2 builders for the specific issue each one
    # addresses). Flipped from "v1" only after the pre-change golden-set
    # baseline (task 5.2, tests/fixtures/transform_golden_baseline_v1.json)
    # had already been captured against v1, per the required capture-before-
    # change ordering. Fallback stays "v1" (the frozen baseline) so an
    # unknown/misconfigured version never silently falls forward to v2.
    # v3 (Stage 5 live-review fix D4) changes only the style prompt and adds the
    # continuity signals; every other transform resolves to its v2 builder
    # under v3. Fallback is "v2" so a misconfigured version lands on the
    # Stage 5 prompts, not on the pre-Stage-5 v1 baseline. PROMPT_VERSION=v2
    # restores the previous behaviour exactly (rollback by config).
    prompt_version:          str = "v3"
    prompt_version_fallback: str = "v2"

    # Streaming STT runs faster-whisper on CPU behind a bounded worker pool so it
    # never contends with vLLM/BGE-M3 on the GPU. Scale out via CPU replicas.
    #   stt_concurrency       — max simultaneous transcription jobs (partial+final)
    #   stt_partial_model     — small/fast model for live partial passes
    #   stt_partial_compute   — compute_type for the partial model
    # The authoritative FINAL pass reuses the existing large-v3-turbo model
    # (settings.resolved_whisper_path) via services/audio_service.py.
    stt_concurrency:       int = 2
    stt_partial_model:     str = "base"      # faster-whisper size: tiny|base|small
    stt_partial_compute:   str = "int8"

    # Live voice-command STT is forced to one language (English by default) so a
    # noisy/accented utterance is never auto-detected as a random other language.
    # Set voice_stt_auto_language=True to re-enable Whisper auto-detection later.
    # (The legacy upload→note path is unaffected — it still auto-detects.)
    voice_stt_language:        str   = "en"
    voice_stt_auto_language:   bool  = False
    # Stability / noise filtering thresholds (passed to faster-whisper)
    voice_no_speech_threshold: float = 0.6    # drop segments the model thinks are silence
    voice_logprob_threshold:   float = -1.0   # drop low-confidence segments
    voice_min_partial_chars:   int   = 2      # ignore tiny/garbage partial transcripts
    voice_min_final_confidence: float = 0.0   # below → treat final as unclear (clarify)
    # Story-aware transcript correction (fuzzy + phonetic), built per story
    voice_vocab_fuzzy_min:     int   = 84     # rapidfuzz ratio 0-100 to accept a fix
    voice_vocab_enabled:       bool  = True

    # Voice agent behaviour limits
    max_voice_audio_mb:            int   = 25     # per streamed utterance / blob
    voice_session_idle_minutes:    int   = 30     # idle session → swept to failed
    # Task 3.7: a client-side action handed to the browser must not sit in
    # 'executing' for ever. Silence is not consent to claim success.
    voice_execution_timeout_seconds: int = 180
    voice_max_graph_nodes:         int   = 8      # hard cap on multi-step plan size
    voice_intent_shortlist_k:      int   = 8      # BGE-M3 candidate capabilities
    voice_confidence_threshold:    float = 0.55   # below → force confirmation
    voice_low_confidence_floor:    float = 0.35   # below → needs_clarification
    voice_admin_emails: list[str] = []            # may read /api/voice/analytics/*

    # ── Phase 3 — generation management (spec §35) ───────────────────────────
    # Every Phase 3 business number lives here (product rule R8: limits are
    # configuration, not code). All have defaults so an untouched .env keeps
    # working; every key is mirrored in .env.example because of extra="forbid".
    #
    # Pins (P3-01). Only the "db" backend is implemented; any other value fails
    # fast at startup (services/pin_store.get_pin_store).
    pin_storage_backend:      str   = "db"
    pin_object_bucket:        str   = ""
    pin_object_prefix:        str   = "pins"
    pin_store_embedding:      bool  = True     # D4 — enables similarity stage 2
    pin_source_excerpt_chars: int   = 300      # only manuscript text a pin stores
    pin_cleanup_batch_size:   int   = 5000
    max_total_pin_age_days:   int   = 365      # ceiling on repeated TTL extension
    rate_limit_pin_write:     str   = "60/minute"
    # JSON object overriding any subset of services/plans._DEFAULT_PLANS, e.g.
    # '{"free": {"max_pins": 30}}'. Validated at import; malformed = no start.
    plan_limits_json:         str   = ""

    # Prompt context budget (P3-03/07/08/10) — tokens, chars/4 estimate.
    generation_context_token_budget:  int = 2600
    consistency_context_token_budget: int = 1200
    pin_context_token_budget:         int = 800
    style_context_token_budget:       int = 400
    avoid_block_token_cap:            int = 300
    avoid_gist_chars:                 int = 240
    avoid_max_items:                  int = 8
    session_history_max:              int = 10

    # Partial regeneration / lineage (P3-02, P3-06).
    max_segments_per_regen: int = 40
    max_fallback_segments:  int = 5
    max_lineage_depth:      int = 12

    # Similarity (P3-11). Conservative starting points; tune per deployment.
    similarity_lexical_hi:      float = 0.82
    similarity_lexical_lo:      float = 0.45
    similarity_semantic_hi:     float = 0.90
    similarity_semantic_mid:    float = 0.75
    similarity_candidate_limit: int   = 20
    duplicate_retry_temp_step:  float = 0.15

    # Preservation checks (P3-05). Heuristic checks only ever WARN; they never
    # rewrite text. Margins are deliberately conservative (false positives
    # train authors to ignore the banner — spec risk R-02).
    tense_flip_margin:        float = 0.25
    pov_shift_margin:         float = 0.30
    dialogue_similarity_min:  float = 0.6
    preservation_auto_repair: bool  = True

    # ── JWT settings ──────────────────────────────────────────────────────────
    # All token values are now configurable without a code deployment.
    # Production: set JWT_EXPIRE_MINUTES=60 for short-lived tokens.
    jwt_expire_minutes: int = 10080   # default 7 days; set to 60 in production
    jwt_algorithm:      str = "HS256" # HS256 default; future: RS256

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level:  str = "INFO"    # DEBUG | INFO | WARNING | ERROR | CRITICAL
    log_format: str = "text"    # text (human-readable) | json (structured)

    # ── CORS origins ──────────────────────────────────────────────────────────
    # On RunPod add your frontend URL: CORS_ORIGINS='["https://your-app.vercel.app"]'
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # ── Computed model paths ──────────────────────────────────────────────────

    @property
    def resolved_llm_path(self) -> str:
        """Local path to Qwen2.5-7B-Instruct weights."""
        return self.llm_model_path or str(Path(self.model_base_dir) / "Qwen2.5-7B-Instruct")

    @property
    def resolved_bge_path(self) -> str:
        """Local path to BGE-M3 weights."""
        return self.bge_model_path or str(Path(self.model_base_dir) / "bge-m3")

    # Backward-compat alias — service code references this name
    @property
    def bge_path(self) -> str:
        return self.resolved_bge_path

    @property
    def got_path(self) -> str:
        """Local path to GOT-OCR2.0 weights."""
        return str(Path(self.model_base_dir) / "GOT-OCR2_0")

    @property
    def resolved_whisper_path(self) -> str:
        """Local path to faster-whisper-large-v3-turbo weights."""
        return str(Path(self.model_base_dir) / "faster-whisper-large-v3-turbo")

    @property
    def qwen_path(self) -> str:
        return self.resolved_llm_path

    # ── vLLM health URL ───────────────────────────────────────────────────────

    @property
    def vllm_health_url(self) -> str:
        """Health check URL — strips /v1 suffix from base URL."""
        base = self.vllm_base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        return f"{base}/health"

    # ── Startup validation ────────────────────────────────────────────────────

    def validate_model_paths(self) -> list[str]:
        """
        Returns a list of missing model paths.
        Empty list means all required models are present.
        GOT-OCR2.0 is excluded — it lazy-loads on first OCR request (no startup penalty).
        """
        missing = []
        checks = [
            ("LLM (Qwen2.5-7B-Instruct)", self.resolved_llm_path),
            ("BGE-M3 embeddings", self.resolved_bge_path),
        ]
        for label, path in checks:
            if not Path(path).exists():
                missing.append(f"  {label}: '{path}'")
        return missing

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if not self.secret_key or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
