"""
OCR Service — EasyOCR (detection) + TrOCR (per-line recognition)

Pipeline per image:
  1. EasyOCR (CRAFT detector): finds all text regions in the full-page image.
     Returns word/region-level bounding boxes + per-region confidence scores.
  2. Regions sorted by Y-center, then merged by proximity (LINE_GAP threshold)
     into full-width line bands — the unit TrOCR was designed to receive.
  3. Each line band is PIL-cropped and fed to TrOCR for handwriting recognition.
     EasyOCR's own text is the fallback if TrOCR returns nothing for a line.
  4. raw_text = recognized lines joined by newlines.
  5. confidence = mean EasyOCR detection score across all regions (real value).
  6. Guard: Qwen cleanup is skipped when raw_text < 5 chars.

Dynamic GPU/CPU device selection:
  get_best_ocr_device(required_vram_gb) is called before each model load.
  It queries every available GPU, picks the one with the most free VRAM, and
  returns that device only when free VRAM ≥ the required threshold.  Otherwise
  it returns CPU.  This makes OCR GPU-aware without hardcoding device indices.

  Thresholds (conservative — account for vLLM KV-cache fluctuation):
    EasyOCR CRAFT:  EASYOCR_MIN_VRAM_GB = 1.5 GB
    TrOCR-large:    TROCR_MIN_VRAM_GB   = 2.5 GB

  OOM safety nets (belt-and-suspenders — in case VRAM changes between load
  and inference):
    EasyOCR readtext() OOM → reinit on CPU + retry
    TrOCR generate()   OOM → move model to CPU + retry the line

  vLLM/Qwen is never touched; OCR shares the GPU only when there is room.
"""

import asyncio
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

# ── Tuneable constants ────────────────────────────────────────────────────────

LINE_GAP     = 40   # px — max Y-center gap to merge word regions into one line
LINE_PADDING = 8    # px — padding added around each merged line crop

# Minimum free VRAM required to run each model on GPU.
# EasyOCR CRAFT: ~700 MB weights + ~500 MB inference headroom for 1200px images.
# TrOCR-large fp32: ~2 GB weights + inference buffer.
EASYOCR_MIN_VRAM_GB = 1.5
TROCR_MIN_VRAM_GB   = 2.5

# ── Singleton model handles ───────────────────────────────────────────────────

_easyocr_reader  = None
_easyocr_on_gpu  = False          # True  when reader is on a CUDA device
_easyocr_gpu_idx = None           # int GPU index, or None when on CPU

_trocr_processor = None
_trocr_model     = None
_trocr_device    = "cpu"          # "cpu" | "cuda:N" — resolved at first load

# Single worker: OCR is sequential; no concurrent CUDA context conflicts.
_ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")


# ── Core device-selection helper ──────────────────────────────────────────────

def get_best_ocr_device(required_vram_gb: float) -> tuple[str, str]:
    """
    Choose the best device for one OCR model load.

    Scans every available CUDA GPU and returns the one with the most free
    VRAM, provided it meets the required_vram_gb threshold.  Falls back to
    CPU when no GPU qualifies or when CUDA is not available.

    Logs GPU count and free/total VRAM for every GPU so the decision is
    fully transparent in the backend log.

    Returns:
        (device_str, reason_str)
        device_str  — "cpu", "cuda:0", "cuda:1", …
        reason_str  — human-readable explanation, shown in log output
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
    gpu_lines: list[str] = []

    for i in range(n_gpus):
        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info(i)
            free_gb  = free_bytes  / (1024 ** 3)
            total_gb = total_bytes / (1024 ** 3)
            gpu_lines.append(
                f"GPU {i} ({torch.cuda.get_device_name(i)}): "
                f"{free_gb:.2f}/{total_gb:.1f} GB free"
            )
            if free_gb > best_free:
                best_free = free_gb
                best_idx  = i
        except Exception as exc:
            gpu_lines.append(f"GPU {i}: query failed ({exc})")

    # Always log the full GPU state so the decision is visible in the log.
    print(
        f"[ocr] GPU survey ({n_gpus} GPU(s), "
        f"need ≥{required_vram_gb} GB for model):"
    )
    for line in gpu_lines:
        print(f"[ocr]   {line}")

    if best_idx < 0:
        return "cpu", "No GPUs found"

    if best_free < required_vram_gb:
        return "cpu", (
            f"Best GPU is GPU {best_idx} with {best_free:.2f} GB free — "
            f"below {required_vram_gb} GB threshold"
        )

    return (
        f"cuda:{best_idx}",
        f"GPU {best_idx} selected — {best_free:.2f} GB free ≥ {required_vram_gb} GB threshold",
    )


# ── Singleton updaters (used by OOM fallback paths) ───────────────────────────

def _set_easyocr_cpu(reader) -> None:
    """Atomically update EasyOCR singletons to the given CPU reader."""
    global _easyocr_reader, _easyocr_on_gpu, _easyocr_gpu_idx
    _easyocr_reader  = reader
    _easyocr_on_gpu  = False
    _easyocr_gpu_idx = None


def _set_trocr_cpu() -> None:
    """Move the TrOCR model to CPU and update the device singleton."""
    global _trocr_device
    import torch
    torch.cuda.empty_cache()
    _trocr_model.to("cpu")
    _trocr_device = "cpu"


# ── Model loaders ─────────────────────────────────────────────────────────────

def _load_easyocr():
    global _easyocr_reader, _easyocr_on_gpu, _easyocr_gpu_idx

    if _easyocr_reader is not None:
        return _easyocr_reader

    try:
        import easyocr
    except ImportError as exc:
        raise RuntimeError(
            "EasyOCR is not installed. Run: pip install easyocr"
        ) from exc

    device, reason = get_best_ocr_device(EASYOCR_MIN_VRAM_GB)
    use_gpu = device.startswith("cuda")
    gpu_idx = int(device.split(":")[1]) if use_gpu else None

    print(
        f"[ocr] EasyOCR → device: {'GPU ' + device if use_gpu else 'CPU'} "
        f"({reason})"
    )

    try:
        # EasyOCR gpu= accepts False, True (default GPU), or int (specific GPU).
        gpu_arg = gpu_idx if use_gpu else False
        _easyocr_reader  = easyocr.Reader(["en"], gpu=gpu_arg)
        _easyocr_on_gpu  = use_gpu
        _easyocr_gpu_idx = gpu_idx
        print(
            f"[ocr] EasyOCR ready on "
            f"{'GPU ' + device if use_gpu else 'CPU'}."
        )
    except Exception as exc:
        if use_gpu:
            print(
                f"[ocr] EasyOCR GPU init failed "
                f"({type(exc).__name__}: {exc}) — falling back to CPU."
            )
            _easyocr_reader  = easyocr.Reader(["en"], gpu=False)
            _easyocr_on_gpu  = False
            _easyocr_gpu_idx = None
            print("[ocr] EasyOCR ready on CPU (init fallback).")
        else:
            raise

    return _easyocr_reader


def _load_trocr():
    global _trocr_processor, _trocr_model, _trocr_device

    if _trocr_model is not None:
        return _trocr_processor, _trocr_model, _trocr_device

    from config import settings
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    print(f"[ocr] Loading TrOCR weights from {settings.trocr_path}...")
    _trocr_processor = TrOCRProcessor.from_pretrained(settings.trocr_path)
    _trocr_model     = VisionEncoderDecoderModel.from_pretrained(settings.trocr_path)
    _trocr_model.eval()

    device, reason = get_best_ocr_device(TROCR_MIN_VRAM_GB)
    use_gpu = device.startswith("cuda")

    print(
        f"[ocr] TrOCR → device: {'GPU ' + device if use_gpu else 'CPU'} "
        f"({reason})"
    )

    try:
        _trocr_model.to(device)
        _trocr_device = device
        print(f"[ocr] TrOCR ready on {'GPU ' + device if use_gpu else 'CPU'}.")
    except RuntimeError as exc:
        if use_gpu and ("out of memory" in str(exc).lower() or "CUDA" in str(exc)):
            print(
                f"[ocr] TrOCR GPU load OOM "
                f"({type(exc).__name__}: {str(exc)[:120]}) — falling back to CPU."
            )
            import torch
            torch.cuda.empty_cache()
            _trocr_model.to("cpu")
            _trocr_device = "cpu"
            print("[ocr] TrOCR ready on CPU (OOM fallback).")
        else:
            raise

    return _trocr_processor, _trocr_model, _trocr_device


# ── Line-merging helper ───────────────────────────────────────────────────────

def _bbox_ycenter(bbox) -> float:
    ys = [pt[1] for pt in bbox]
    return (min(ys) + max(ys)) / 2.0


def _merge_into_line_bands(raw_results: list, img_w: int, img_h: int) -> list:
    """
    Merge word/region-level EasyOCR bounding boxes into full-width line bands.

    Groups entries whose Y-centers lie within LINE_GAP pixels, then computes
    the bounding rectangle spanning all members of each group.

    Returns list of (x_min, y_min, x_max, y_max, avg_confidence, easyocr_text)
    sorted top-to-bottom.
    """
    if not raw_results:
        return []

    sorted_r = sorted(raw_results, key=lambda r: _bbox_ycenter(r[0]))

    groups:       list[list]  = []
    current_group: list       = []
    current_y:    float | None = None

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

        avg_conf  = float(np.mean([c for _, _, c in group]))
        easy_text = " ".join(t.strip() for _, t, _ in group if t.strip())
        bands.append((x_min, y_min, x_max, y_max, avg_conf, easy_text))

    return bands


# ── TrOCR inference on a single cropped line ─────────────────────────────────

def _trocr_on_crop(processor, model, device: str, crop: Image.Image) -> str:
    """
    Run TrOCR on one pre-cropped line image.

    Moves pixel_values to `device`.  On CUDA OOM during generate():
      - clears GPU cache
      - moves the model permanently to CPU
      - updates _trocr_device so all subsequent lines use CPU
      - retries this line on CPU
    """
    import torch

    line = crop.convert("RGB")
    if line.height < 32:
        scale = 64.0 / line.height
        line  = line.resize((max(1, int(line.width * scale)), 64), Image.LANCZOS)

    # Keep pixel_values on CPU until we know the GPU path will work.
    pixel_values_cpu = processor(images=line, return_tensors="pt").pixel_values

    try:
        pv = pixel_values_cpu.to(device)
        with torch.no_grad():
            ids = model.generate(pv, max_new_tokens=128)
        return processor.batch_decode(ids.cpu(), skip_special_tokens=True)[0].strip()

    except RuntimeError as exc:
        oom = "out of memory" in str(exc).lower() or "OutOfMemoryError" in type(exc).__name__
        if oom and device != "cpu":
            print(
                f"[ocr] TrOCR CUDA OOM during inference "
                f"({str(exc)[:120]}) — moving model to CPU and retrying this line."
            )
            _set_trocr_cpu()
            with torch.no_grad():
                ids = model.generate(pixel_values_cpu, max_new_tokens=128)
            return processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
        raise


# ── Main synchronous pipeline (runs inside the thread executor) ───────────────

def _sync_run_ocr_pipeline(image_path: str) -> dict:
    """
    Full OCR pipeline for one image.

    Returns dict:
        raw_text       — newline-joined lines from TrOCR recognition
        confidence     — mean EasyOCR detection confidence (real, not hardcoded)
        ocr_engine     — "easyocr+trocr"
        lines_detected — number of raw EasyOCR word regions found
    """
    reader                       = _load_easyocr()
    processor, model, trocr_dev  = _load_trocr()

    img_pil = Image.open(image_path).convert("RGB")
    img_w, img_h = img_pil.size

    easy_label  = f"GPU (cuda:{_easyocr_gpu_idx})" if _easyocr_on_gpu else "CPU"
    trocr_label = f"GPU ({_trocr_device})"          if _trocr_device != "cpu" else "CPU"
    print(
        f"[ocr] Processing {image_path.split('/')[-1]} "
        f"({img_w}×{img_h}px) | "
        f"EasyOCR={easy_label} | TrOCR={trocr_label}"
    )

    # ── Phase 1: EasyOCR region detection ────────────────────────────────────
    # OOM safety net: if the GPU reader hits OOM at inference time (vLLM may
    # have expanded its KV cache since we loaded), reinit on CPU and retry.
    try:
        raw_results = reader.readtext(image_path)
    except Exception as exc:
        oom = "out of memory" in str(exc).lower() or "OutOfMemoryError" in type(exc).__name__
        if oom:
            print(
                f"[ocr] EasyOCR CUDA OOM during readtext "
                f"({str(exc)[:120]}) — reinitializing on CPU and retrying."
            )
            import torch, easyocr as _ez
            torch.cuda.empty_cache()
            cpu_reader = _ez.Reader(["en"], gpu=False)
            _set_easyocr_cpu(cpu_reader)
            raw_results = cpu_reader.readtext(image_path)
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

    all_confs      = [float(c) for _, _, c in raw_results]
    avg_confidence = float(np.mean(all_confs))
    print(
        f"[ocr] EasyOCR: {n_raw} region(s) detected | "
        f"avg_confidence={avg_confidence:.3f}"
    )

    # ── Phase 2: Merge into line bands ────────────────────────────────────────
    bands = _merge_into_line_bands(raw_results, img_w, img_h)
    print(
        f"[ocr] Merged {n_raw} regions → {len(bands)} line band(s) "
        f"(LINE_GAP={LINE_GAP}px)"
    )

    # ── Phase 3: TrOCR per line band ─────────────────────────────────────────
    texts: list[str] = []
    for i, (x_min, y_min, x_max, y_max, _line_conf, easy_text) in enumerate(bands):
        crop       = img_pil.crop((x_min, y_min, x_max, y_max))
        # Use the current _trocr_device — may have changed to "cpu" via OOM fallback.
        trocr_text = _trocr_on_crop(processor, model, _trocr_device, crop)

        chosen = trocr_text if trocr_text.strip() else easy_text
        source = "trocr"   if trocr_text.strip() else "easyocr"

        print(
            f"[ocr] Line {i + 1:2d}: "
            f"easy={easy_text[:40]!r} | "
            f"trocr={trocr_text!r} | "
            f"used={source}"
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
        "raw_text":      raw_text,
        "confidence":    round(avg_confidence, 3),
        "ocr_engine":    "easyocr+trocr",
        "lines_detected": n_raw,
    }


# ── Public async entry point ──────────────────────────────────────────────────

async def process_ocr_image(image_path: str) -> dict:
    """
    Async wrapper: runs the synchronous pipeline in the thread executor so it
    never blocks the FastAPI event loop.

    RuntimeError (missing package, hard model failure) re-raises → HTTP 500.
    Empty extraction returns raw_text="" without calling Qwen.
    """
    loop = asyncio.get_event_loop()
    ocr_result = await loop.run_in_executor(
        _ocr_executor, _sync_run_ocr_pipeline, image_path
    )

    raw_text   = ocr_result["raw_text"]
    confidence = ocr_result["confidence"]

    # Guard: Qwen cleanup only when real text exists.
    # Prevents Qwen from generating a "no text to clean" filler that would
    # be shown as the extraction result in the UI.
    if len(raw_text.strip()) < 5:
        print(
            f"[ocr] raw_text too short ({len(raw_text.strip())} chars) — "
            "skipping Qwen cleanup."
        )
        return {
            "raw_text":       raw_text,
            "cleaned_text":   "",
            "note_type":      "other",
            "confidence":     confidence,
            "ocr_engine":     ocr_result["ocr_engine"],
            "lines_detected": ocr_result["lines_detected"],
        }

    from services.ai_service import clean_ocr_text
    cleaned_text, note_type = await clean_ocr_text(raw_text)

    return {
        "raw_text":       raw_text,
        "cleaned_text":   cleaned_text,
        "note_type":      note_type,
        "confidence":     confidence,
        "ocr_engine":     ocr_result["ocr_engine"],
        "lines_detected": ocr_result["lines_detected"],
    }
