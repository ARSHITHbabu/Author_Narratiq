"""
OCR Service — EasyOCR (detection) + TrOCR (per-line recognition)

Why this replaces PaddleOCR:
  PaddleOCR 3.x + PaddlePaddle 3.3.1 crash at inference with a hard
  NotImplementedError inside the oneDNN/PIR executor — not fixable via
  config or env flags.  EasyOCR uses PyTorch (already present for TrOCR),
  requires no PaddlePaddle, and works on this server.

Pipeline:
  1. EasyOCR detects all text regions in the full-page image.
     Returns word/region-level bounding boxes + per-region confidence.
  2. Regions are merged by Y-center proximity (LINE_GAP threshold) into
     full-width line bands — the unit TrOCR was trained on.
  3. Each merged line band is PIL-cropped and fed to TrOCR for
     handwriting recognition.  EasyOCR's own text is the fallback if
     TrOCR returns nothing for a line.
  4. raw_text = all recognized lines joined by newlines.
  5. confidence = mean of all EasyOCR region detection scores (real, not
     hardcoded).
  6. Guard: Qwen cleanup is skipped when raw_text is empty or < 5 chars.

GPU policy (each model tries GPU first, falls back to CPU on OOM):
  EasyOCR → gpu=True when CUDA is available; RuntimeError → gpu=False
  TrOCR   → moved to CUDA when ≥2 GB VRAM is free; OOM → stays on CPU
  Both models log exactly which device they ended up on.
"""

import asyncio
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

# ── Device detection ──────────────────────────────────────────────────────────

def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False

def _free_vram_gb() -> float:
    """Return free VRAM on device 0 in GB, or 0 if CUDA unavailable."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        free_bytes, _ = torch.cuda.mem_get_info(0)
        return free_bytes / (1024 ** 3)
    except Exception:
        return 0.0

_HAS_CUDA = _cuda_available()

# ── Tuneable constants ────────────────────────────────────────────────────────

LINE_GAP     = 40   # px — max Y-center gap to merge regions into one line
LINE_PADDING = 8    # px — padding added around each merged line crop

# VRAM thresholds — conservative to account for KV-cache fluctuation in vLLM.
# EasyOCR CRAFT model: ~700 MB weights + ~500 MB inference headroom on 1200px images.
# TrOCR-large fp32: ~2 GB weights alone.
EASYOCR_MIN_VRAM_GB = 1.5   # minimum free VRAM to attempt EasyOCR on GPU
TROCR_MIN_VRAM_GB   = 2.0   # minimum free VRAM to attempt TrOCR on GPU

# ── Singleton model handles ───────────────────────────────────────────────────

_easyocr_reader  = None
_easyocr_on_gpu  = False

_trocr_processor = None
_trocr_model     = None
_trocr_device    = "cpu"   # resolved at first load

# Single worker: OCR operations are sequential per image.
_ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")


def _update_easyocr_singleton(reader, *, on_gpu: bool) -> None:
    """Update module-level EasyOCR singletons from inside the OOM fallback."""
    global _easyocr_reader, _easyocr_on_gpu
    _easyocr_reader = reader
    _easyocr_on_gpu = on_gpu


# ── Model loaders ─────────────────────────────────────────────────────────────

def _load_easyocr():
    global _easyocr_reader, _easyocr_on_gpu

    if _easyocr_reader is not None:
        return _easyocr_reader

    try:
        import easyocr
    except ImportError as exc:
        raise RuntimeError(
            "EasyOCR is not installed. Run: pip install easyocr"
        ) from exc

    # EasyOCR CRAFT model needs ~700 MB on GPU, plus ~500 MB inference headroom
    # for typical full-page images.  Check free VRAM before attempting GPU.
    free_gb = _free_vram_gb() if _HAS_CUDA else 0.0
    use_gpu = _HAS_CUDA and (free_gb >= EASYOCR_MIN_VRAM_GB)

    if _HAS_CUDA and not use_gpu:
        print(
            f"[ocr] EasyOCR: free VRAM {free_gb:.1f} GB < {EASYOCR_MIN_VRAM_GB} GB "
            "— loading on CPU."
        )

    if use_gpu:
        print(
            f"[ocr] Loading EasyOCR → attempting GPU "
            f"({free_gb:.1f} GB free ≥ {EASYOCR_MIN_VRAM_GB} GB threshold)..."
        )
        try:
            _easyocr_reader = easyocr.Reader(["en"], gpu=True)
            _easyocr_on_gpu = True
            print("[ocr] EasyOCR ready on GPU.")
        except Exception as exc:
            print(
                f"[ocr] EasyOCR GPU init failed ({type(exc).__name__}: {exc}) "
                "— falling back to CPU."
            )
            _easyocr_reader = easyocr.Reader(["en"], gpu=False)
            _easyocr_on_gpu = False
            print("[ocr] EasyOCR ready on CPU (fallback).")
    else:
        print("[ocr] Loading EasyOCR on CPU.")
        _easyocr_reader = easyocr.Reader(["en"], gpu=False)
        _easyocr_on_gpu = False
        print("[ocr] EasyOCR ready on CPU.")

    return _easyocr_reader


def _load_trocr():
    global _trocr_processor, _trocr_model, _trocr_device

    if _trocr_model is not None:
        return _trocr_processor, _trocr_model, _trocr_device

    from config import settings
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    print(f"[ocr] Loading TrOCR from {settings.trocr_path}...")
    _trocr_processor = TrOCRProcessor.from_pretrained(settings.trocr_path)
    _trocr_model = VisionEncoderDecoderModel.from_pretrained(settings.trocr_path)
    _trocr_model.eval()

    # Decide target device.
    # TrOCR-large-handwritten (fp32) needs ~2 GB VRAM.
    # vLLM pre-allocates most of the GPU; check actual free memory.
    if _HAS_CUDA:
        free_gb = _free_vram_gb()
        print(
            f"[ocr] CUDA available. Free VRAM: {free_gb:.1f} GB "
            f"(need ≥{TROCR_MIN_VRAM_GB} GB for TrOCR on GPU)."
        )
        if free_gb >= TROCR_MIN_VRAM_GB:
            print("[ocr] Loading TrOCR → attempting GPU...")
            try:
                _trocr_model.to("cuda")
                _trocr_device = "cuda"
                print("[ocr] TrOCR ready on GPU.")
            except RuntimeError as exc:
                print(
                    f"[ocr] TrOCR GPU load failed ({type(exc).__name__}: {exc}) "
                    "— falling back to CPU."
                )
                _trocr_model.to("cpu")
                _trocr_device = "cpu"
                print("[ocr] TrOCR ready on CPU (OOM fallback).")
        else:
            print(
                f"[ocr] Insufficient free VRAM ({free_gb:.1f} GB < {TROCR_MIN_VRAM_GB} GB) "
                "— loading TrOCR on CPU."
            )
            _trocr_model.to("cpu")
            _trocr_device = "cpu"
            print("[ocr] TrOCR ready on CPU.")
    else:
        _trocr_model.to("cpu")
        _trocr_device = "cpu"
        print("[ocr] TrOCR ready on CPU (no CUDA).")

    return _trocr_processor, _trocr_model, _trocr_device


# ── Line-merging helper ───────────────────────────────────────────────────────

def _bbox_ycenter(bbox) -> float:
    ys = [pt[1] for pt in bbox]
    return (min(ys) + max(ys)) / 2.0


def _merge_into_line_bands(raw_results: list, img_w: int, img_h: int) -> list:
    """
    Merge word/region-level EasyOCR bounding boxes into line-level bands.

    EasyOCR returns one entry per detected word or text region.  We group
    entries whose Y-centers lie within LINE_GAP pixels of each other, then
    compute the bounding rectangle spanning all members of each group.

    Returns a list of tuples:
        (x_min, y_min, x_max, y_max, avg_confidence, easyocr_text)
    sorted top-to-bottom.
    """
    if not raw_results:
        return []

    sorted_r = sorted(raw_results, key=lambda r: _bbox_ycenter(r[0]))

    groups: list[list] = []
    current_group: list = []
    current_y: float | None = None

    for bbox, text, conf in sorted_r:
        yc = _bbox_ycenter(bbox)
        if current_y is None or abs(yc - current_y) <= LINE_GAP:
            current_group.append((bbox, text, conf))
            n = len(current_group)
            current_y = yc if n == 1 else (current_y * (n - 1) + yc) / n
        else:
            if current_group:
                groups.append(current_group)
            current_group = [(bbox, text, conf)]
            current_y = yc

    if current_group:
        groups.append(current_group)

    bands = []
    for group in groups:
        all_pts = [pt for bbox, _, _ in group for pt in bbox]
        x_min = max(0,     int(min(pt[0] for pt in all_pts)) - LINE_PADDING)
        y_min = max(0,     int(min(pt[1] for pt in all_pts)) - LINE_PADDING)
        x_max = min(img_w, int(max(pt[0] for pt in all_pts)) + LINE_PADDING)
        y_max = min(img_h, int(max(pt[1] for pt in all_pts)) + LINE_PADDING)

        if x_max <= x_min or y_max <= y_min:
            continue

        avg_conf   = float(np.mean([c for _, _, c in group]))
        easy_text  = " ".join(t.strip() for _, t, _ in group if t.strip())
        bands.append((x_min, y_min, x_max, y_max, avg_conf, easy_text))

    return bands


# ── TrOCR inference on a single cropped line ─────────────────────────────────

def _trocr_on_crop(processor, model, device: str, crop: Image.Image) -> str:
    """
    Run TrOCR on one pre-cropped line image.

    Ensures minimum height (TrOCR degrades on very thin slices).
    Moves pixel_values to the same device as the model.
    """
    import torch

    line = crop.convert("RGB")
    if line.height < 32:
        scale = 64.0 / line.height
        line = line.resize((max(1, int(line.width * scale)), 64), Image.LANCZOS)

    pixel_values = processor(images=line, return_tensors="pt").pixel_values.to(device)

    with torch.no_grad():
        generated_ids = model.generate(pixel_values, max_new_tokens=128)

    return processor.batch_decode(
        generated_ids.cpu(), skip_special_tokens=True
    )[0].strip()


# ── Main synchronous pipeline (runs inside the thread executor) ───────────────

def _sync_run_ocr_pipeline(image_path: str) -> dict:
    """
    Full OCR pipeline for one image.

    Returns:
        raw_text       — newline-joined text from all recognized line bands
        confidence     — mean EasyOCR detection confidence (real, not hardcoded)
        ocr_engine     — "easyocr+trocr"
        lines_detected — number of raw EasyOCR regions found
    """
    reader                        = _load_easyocr()
    processor, model, trocr_dev  = _load_trocr()

    img_pil = Image.open(image_path).convert("RGB")
    img_w, img_h = img_pil.size

    print(
        f"[ocr] Processing {image_path.split('/')[-1]} ({img_w}×{img_h}px) | "
        f"easyocr={'GPU' if _easyocr_on_gpu else 'CPU'} | "
        f"trocr={trocr_dev.upper()}"
    )

    # ── Phase 1: EasyOCR region detection ────────────────────────────────────
    # Safety net: if GPU reader was loaded but inference hits OOM anyway
    # (e.g. vLLM expanded its KV cache between load and inference),
    # re-initialize on CPU and retry once.
    try:
        raw_results = reader.readtext(image_path)
    except Exception as exc:
        if "out of memory" in str(exc).lower() or "OutOfMemoryError" in type(exc).__name__:
            print(
                "[ocr] EasyOCR GPU OOM during inference — "
                "re-initializing on CPU and retrying."
            )
            import torch as _torch_oom
            import easyocr as _easyocr_mod
            _torch_oom.cuda.empty_cache()
            _cpu_reader = _easyocr_mod.Reader(["en"], gpu=False)
            # Update the module-level singletons so subsequent calls use CPU too
            _update_easyocr_singleton(_cpu_reader, on_gpu=False)
            raw_results = _cpu_reader.readtext(image_path)
            reader = _cpu_reader
            print("[ocr] EasyOCR CPU retry succeeded.")
        else:
            raise
    n_raw = len(raw_results)

    if not raw_results:
        print("[ocr] EasyOCR detected no text regions in the image.")
        return {
            "raw_text": "",
            "confidence": 0.0,
            "ocr_engine": "easyocr+trocr",
            "lines_detected": 0,
        }

    all_confs = [float(c) for _, _, c in raw_results]
    avg_confidence = float(np.mean(all_confs))

    print(
        f"[ocr] EasyOCR: {n_raw} region(s) detected | "
        f"avg_confidence={avg_confidence:.3f}"
    )

    # ── Phase 2: Merge into line bands ────────────────────────────────────────
    bands = _merge_into_line_bands(raw_results, img_w, img_h)
    print(
        f"[ocr] Merged into {len(bands)} line band(s) "
        f"(LINE_GAP={LINE_GAP}px)"
    )

    # ── Phase 3: TrOCR per line band ─────────────────────────────────────────
    texts: list[str] = []
    for i, (x_min, y_min, x_max, y_max, line_conf, easy_text) in enumerate(bands):
        crop   = img_pil.crop((x_min, y_min, x_max, y_max))
        trocr_text = _trocr_on_crop(processor, model, trocr_dev, crop)

        # Prefer TrOCR result; fall back to EasyOCR text if TrOCR returns nothing.
        chosen = trocr_text if trocr_text.strip() else easy_text

        print(
            f"[ocr] Line {i + 1:2d}: "
            f"easy={easy_text[:45]!r} | "
            f"trocr={trocr_text!r} | "
            f"used={'trocr' if trocr_text.strip() else 'easyocr'}"
        )

        if chosen.strip():
            texts.append(chosen.strip())

    raw_text = "\n".join(texts)

    print(
        f"[ocr] Pipeline complete: "
        f"{len(texts)}/{len(bands)} line(s) non-empty | "
        f"confidence={avg_confidence:.3f} | "
        f"raw_text={len(raw_text)} chars"
    )

    return {
        "raw_text": raw_text,
        "confidence": round(avg_confidence, 3),
        "ocr_engine": "easyocr+trocr",
        "lines_detected": n_raw,
    }


# ── Public async entry point ──────────────────────────────────────────────────

async def process_ocr_image(image_path: str) -> dict:
    """
    Async wrapper: runs the synchronous OCR pipeline in the thread executor
    so it never blocks the FastAPI event loop.

    On RuntimeError (missing package, model load failure): re-raises so the
    router can surface it as HTTP 500.
    When no text is detected: returns raw_text="" without calling Qwen.
    """
    loop = asyncio.get_event_loop()
    ocr_result = await loop.run_in_executor(
        _ocr_executor, _sync_run_ocr_pipeline, image_path
    )

    raw_text   = ocr_result["raw_text"]
    confidence = ocr_result["confidence"]

    # Guard: only call Qwen cleanup if there is real extracted text.
    # Prevents Qwen from generating a "no text to clean" filler that
    # would be shown as the extraction result in the UI.
    if len(raw_text.strip()) < 5:
        print(
            f"[ocr] raw_text too short ({len(raw_text.strip())} chars) — "
            "skipping Qwen cleanup."
        )
        return {
            "raw_text":      raw_text,
            "cleaned_text":  "",
            "note_type":     "other",
            "confidence":    confidence,
            "ocr_engine":    ocr_result["ocr_engine"],
            "lines_detected": ocr_result["lines_detected"],
        }

    from services.ai_service import clean_ocr_text
    cleaned_text, note_type = await clean_ocr_text(raw_text)

    return {
        "raw_text":      raw_text,
        "cleaned_text":  cleaned_text,
        "note_type":     note_type,
        "confidence":    confidence,
        "ocr_engine":    ocr_result["ocr_engine"],
        "lines_detected": ocr_result["lines_detected"],
    }
