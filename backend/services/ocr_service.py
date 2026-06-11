"""
OCR Service — GOT-OCR2.0 (General OCR Theory v2)

Pipeline per image:
  1. GOT-OCR2.0: end-to-end full-page OCR (no detect → crop → recognize steps)
     Single forward pass on the raw image → plain text in reading order.
  2. Quality score derived from the ratio of word-like tokens in the output.
  3. Qwen cleanup (spacing / punctuation only; proper nouns preserved).

Why no image preprocessing:
  GOT-OCR2.0 includes robust internal preprocessing (ViT image processor,
  1024×1024 with ImageNet normalisation, trained on diverse real-world images).
  External operations such as CLAHE or Gaussian blur degrade output quality by
  changing the contrast characteristics that the model was calibrated against.

Model: stepfun-ai/GOT-OCR2_0
  - 580M parameters (ViT-large encoder + Qwen-1.5-0.5B decoder)
  - Local path: /workspace/models/GOT-OCR2_0/
  - VRAM (float16): ~1.2 GB  |  RAM (float32 / CPU): ~2.4 GB
  - Custom code files: modeling_GOT.py, got_vision_b.py, tokenization_qwen.py
    (loaded via trust_remote_code=True from the local model directory)

GPU policy (GOT_MIN_VRAM_GB = 2.5):
  get_best_ocr_device() scans free VRAM on all GPUs and selects the one with
  the most free VRAM, provided it meets the 2.5 GB threshold.  Falls back to
  CPU when no GPU qualifies.

  In the current deployment (vLLM TP=2 at 90% utilisation on both GPUs):
    GPU 0: ~0.6 GB free — below threshold → CPU fallback
    GPU 1: ~0.6 GB free — below threshold → CPU fallback
  When vLLM is reconfigured with TP=1, GPU 1 becomes available for GOT.

  CPU inference: ~25–60 s per page (correct output, acceptable for the
  "photograph your handwritten notes" use case).

Compatibility patches applied to modeling_GOT.py (see patch in this repo):
  - DynamicCache.seen_tokens   → getattr fallback (removed in transformers 4.38)
  - DynamicCache.get_max_length() → getattr fallback (removed in transformers 4.38)
  - All .cuda() calls          → .to(_mdl_device) (CPU/GPU agnostic)
  - torch.autocast("cuda", …)  → contextlib.nullcontext() on CPU
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Register HEIC/HEIF decoder with Pillow so PIL.Image.open() handles .heic/.heif
# files transparently — required for iPhone camera photos (default HEIC format).
try:
    from pillow_heif import register_heif_opener as _register_heif_opener
    _register_heif_opener()
    logger.info("[ocr_service] pillow-heif registered — HEIC/HEIF support enabled.")
except ImportError:
    logger.info("[ocr_service] pillow-heif not installed — HEIC/HEIF not supported.")
# Single-worker executor: GOT is sequential; no concurrent CUDA context conflicts.
_ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")

# ── Singleton model handles ───────────────────────────────────────────────────

_got_tokenizer = None
_got_model     = None
_got_device    = "cpu"

GOT_MIN_VRAM_GB = 2.5


# ── Device selection ──────────────────────────────────────────────────────────

def get_best_ocr_device(required_vram_gb: float) -> tuple[str, str]:
    """
    Scan all CUDA GPUs for free VRAM.  Return the device string for the GPU
    with the most free VRAM if it meets required_vram_gb; otherwise 'cpu'.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return "cpu", "CUDA not available"
    except ImportError:
        return "cpu", "PyTorch not installed"

    import torch
    n_gpus = torch.cuda.device_count()
    best_idx  = -1
    best_free = 0.0
    lines: list[str] = []

    for i in range(n_gpus):
        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info(i)
            free_gb  = free_bytes  / (1024 ** 3)
            total_gb = total_bytes / (1024 ** 3)
            lines.append(
                f"GPU {i} ({torch.cuda.get_device_name(i)}): "
                f"{free_gb:.2f}/{total_gb:.1f} GB free"
            )
            if free_gb > best_free:
                best_free = free_gb
                best_idx  = i
        except Exception as exc:
            lines.append(f"GPU {i}: query failed ({exc})")

    logger.info(f"[ocr] GPU survey ({n_gpus} GPU(s), need ≥{required_vram_gb} GB):")
    for ln in lines:
        logger.info(f"[ocr]   {ln}")
    if best_idx < 0:
        return "cpu", "no GPUs found"

    if best_free < required_vram_gb:
        return "cpu", (
            f"best GPU {best_idx} has {best_free:.2f} GB free — "
            f"below {required_vram_gb} GB threshold"
        )

    return (
        f"cuda:{best_idx}",
        f"GPU {best_idx} selected — {best_free:.2f} GB free ≥ {required_vram_gb} GB",
    )


# ── Model loader ──────────────────────────────────────────────────────────────

def _load_got():
    """Load GOT-OCR2.0 tokenizer + model (singleton — loads once, reused)."""
    global _got_tokenizer, _got_model, _got_device

    if _got_model is not None:
        return _got_tokenizer, _got_model, _got_device

    import torch
    from transformers import AutoTokenizer, AutoModel
    from config import settings

    model_path = settings.got_path
    if not os.path.isdir(model_path):
        raise RuntimeError(
            f"GOT-OCR2.0 model not found at {model_path}. "
            "Run: bash scripts/download_models.sh"
        )

    logger.info(f"[ocr] Loading GOT-OCR2.0 from {model_path}...")
    device, reason = get_best_ocr_device(GOT_MIN_VRAM_GB)
    use_gpu = device.startswith("cuda")
    dtype   = torch.float16 if use_gpu else torch.float32

    logger.info(f"[ocr] GOT-OCR2.0 → device: {device} ({reason})")
    _got_tokenizer = AutoTokenizer.from_pretrained(
        model_path, trust_remote_code=True
    )
    _got_model = AutoModel.from_pretrained(
        model_path,
        trust_remote_code=True,
        low_cpu_mem_usage=True,
        device_map=device,
        use_safetensors=True,
        pad_token_id=_got_tokenizer.eos_token_id,
        dtype=dtype,
    )
    _got_model = _got_model.eval()
    _got_device = device

    label = f"GPU ({device})" if use_gpu else "CPU"
    logger.info(f"[ocr] GOT-OCR2.0 ready on {label}.")
    return _got_tokenizer, _got_model, _got_device


# ── Quality score ─────────────────────────────────────────────────────────────

def _quality_score(text: str) -> float:
    """
    Proxy for extraction confidence: fraction of words that are ≥70% alphabetic.
    GOT-OCR2.0 does not emit per-token log-probabilities, so this heuristic
    reflects how much of the output looks like natural English prose.
    """
    if not text or not text.strip():
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    clean = sum(
        1 for w in words
        if len(w) >= 2 and sum(c.isalpha() for c in w) / len(w) >= 0.7
    )
    return round(clean / len(words), 3)


# ── Main synchronous pipeline ─────────────────────────────────────────────────

def _sync_run_got_pipeline(image_path: str) -> dict:
    """
    Synchronous OCR pipeline (runs inside the thread executor).

    Passes the raw image directly to GOT-OCR2.0.  No external preprocessing
    is applied — GOT's internal GOTImageProcessor handles contrast, scaling,
    and normalisation, and performs better than hand-crafted preprocessing
    on phone photos of handwriting.

    Returns dict:
        raw_text       — plain text output from GOT
        confidence     — quality proxy (word-validity ratio, 0.0–1.0)
        ocr_engine     — "got-ocr2.0"
        lines_detected — 0 (GOT is end-to-end; no line detection step)
    """
    from PIL import Image as PILImage

    img     = PILImage.open(image_path)
    w, h    = img.size
    fname   = os.path.basename(image_path)
    logger.info(f"[ocr] Processing {fname} ({w}×{h}px) with GOT-OCR2.0")
    tokenizer, model, device = _load_got()

    label = f"GPU ({device})" if device.startswith("cuda") else "CPU"
    logger.info(f"[ocr] Inference on {label}…")
    try:
        raw_text = model.chat(tokenizer, image_path, ocr_type="ocr")
    except RuntimeError as exc:
        # CUDA OOM safety net: move model to CPU and retry
        oom = "out of memory" in str(exc).lower() or "OutOfMemoryError" in type(exc).__name__
        if oom and device != "cpu":
            import torch
            global _got_device
            logger.info( f"[ocr] GOT CUDA OOM ({str(exc)[:80]}) — " "moving model to CPU and retrying." )
            torch.cuda.empty_cache()
            model.to("cpu")
            _got_device = "cpu"
            raw_text = model.chat(tokenizer, image_path, ocr_type="ocr")
        else:
            raise

    raw_text = (raw_text or "").strip()
    quality  = _quality_score(raw_text)
    n_words  = len(raw_text.split())

    logger.info( f"[ocr] GOT complete: {n_words} words | " f"quality={quality:.3f} | device={device}" )

    return {
        "raw_text":      raw_text,
        "confidence":    quality,
        "ocr_engine":    "got-ocr2.0",
        "lines_detected": 0,
    }


# ── Public async entry point ──────────────────────────────────────────────────

async def process_ocr_image(image_path: str) -> dict:
    """
    Async wrapper: runs the synchronous pipeline in the thread executor so it
    never blocks the FastAPI event loop.

    RuntimeError (model missing, pipeline crash) re-raises → HTTP 500.
    Empty extraction returns raw_text="" without calling Qwen.
    """
    loop       = asyncio.get_event_loop()
    ocr_result = await loop.run_in_executor(
        _ocr_executor, _sync_run_got_pipeline, image_path
    )

    raw_text   = ocr_result["raw_text"]
    confidence = ocr_result["confidence"]

    if len(raw_text.strip()) < 5:
        logger.info( f"[ocr] raw_text too short ({len(raw_text.strip())} chars) — " "skipping Qwen cleanup." )
        return {
            "raw_text":       raw_text,
            "cleaned_text":   "",
            "note_type":      "other",
            "confidence":     confidence,
            "ocr_engine":     ocr_result["ocr_engine"],
            "lines_detected": 0,
        }

    from services.ai_service import clean_ocr_text
    cleaned_text, note_type = await clean_ocr_text(raw_text)

    return {
        "raw_text":       raw_text,
        "cleaned_text":   cleaned_text,
        "note_type":      note_type,
        "confidence":     confidence,
        "ocr_engine":     ocr_result["ocr_engine"],
        "lines_detected": 0,
    }
