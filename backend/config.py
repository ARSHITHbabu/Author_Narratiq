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
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./narratiq.db"
    secret_key: str = "narratiq-secret-change-in-production-use-a-long-random-string"

    # ── Model base directory ──────────────────────────────────────────────────
    # All model subdirs live here.  Set via MODEL_BASE_DIR env var.
    model_base_dir: str = "/workspace/models"

    # ── Hugging Face model IDs ────────────────────────────────────────────────
    # Used by scripts/download_models.sh and as a display reference.
    llm_model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    bge_model_id: str = "BAAI/bge-m3"
    got_ocr_model_id: str = "stepfun-ai/GOT-OCR2_0"

    # ── Optional direct local path overrides ──────────────────────────────────
    # If unset, paths are derived: {model_base_dir}/{model-folder-name}
    # Set LLM_MODEL_PATH=/workspace/models/Qwen2.5-7B-Instruct to override.
    llm_model_path: str = ""
    bge_model_path: str = ""

    # ── vLLM server ───────────────────────────────────────────────────────────
    # VLLM_BASE_URL overrides host+port construction.
    # Default: http://127.0.0.1:8001/v1  (matches start.sh which binds on 8001)
    vllm_base_url: str = "http://127.0.0.1:8001/v1"
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

    # ── FastAPI server ────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
