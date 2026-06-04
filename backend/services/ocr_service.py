"""
OCR Service — PaddleOCR (detection) + TrOCR (per-line recognition)

Why this architecture:
  TrOCR-large-handwritten was designed for single-line text recognition.
  Feeding it a full-page photo produces empty or garbled output because it
  has no text detection capability — it doesn't know where lines are.

  PaddleOCR solves this: its DBNet detector finds every text line in the
  image (including rotated, tilted, or multi-column layouts) and returns
  a bounding box per line. Each cropped line is then fed to TrOCR, which
  is exactly the input it was trained on.

Pipeline per image:
  1. PaddleOCR (CPU): detect all text line bounding boxes + PaddleOCR text
     + per-line detection confidence scores.
  2. Sort detected lines top-to-bottom (natural reading order).
  3. For each line: perspective-correct crop → TrOCR inference → line text.
     Fall back to PaddleOCR's own recognition if TrOCR returns nothing.
  4. Assemble raw_text from all lines joined by newlines.
  5. Real confidence = average of PaddleOCR detection scores.
  6. Guard: if raw_text is empty/too short, return without calling Qwen.
  7. Qwen cleanup (ai_service.clean_ocr_text): fix spelling, classify note type.

Both OCR models run on CPU — they do not compete with vLLM for GPU VRAM.
Both are lazy-loaded on the first OCR request and stay resident.
All inference runs in a single-worker ThreadPoolExecutor so it never blocks
the FastAPI async event loop.
"""

import asyncio
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

from config import settings

# ── Singleton model handles ───────────────────────────────────────────────────

_trocr_processor = None
_trocr_model = None
_paddle_ocr = None

# Single worker: OCR is sequential per image; one thread is enough.
_ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")


# ── Model loaders (called at first OCR request) ───────────────────────────────

def _load_trocr():
    global _trocr_processor, _trocr_model
    if _trocr_model is None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        print(f"[ocr] Loading TrOCR from {settings.trocr_path}...")
        _trocr_processor = TrOCRProcessor.from_pretrained(settings.trocr_path)
        _trocr_model = VisionEncoderDecoderModel.from_pretrained(settings.trocr_path)
        _trocr_model.to("cpu")
        _trocr_model.eval()
        print("[ocr] TrOCR ready.")
    return _trocr_processor, _trocr_model


def _load_paddle():
    global _paddle_ocr
    if _paddle_ocr is None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. "
                "Run: pip install paddlepaddle paddleocr opencv-python-headless"
            ) from exc
        print("[ocr] Loading PaddleOCR detection model (CPU)...")
        _paddle_ocr = PaddleOCR(
            use_angle_cls=True,      # handles rotated / upside-down text lines
            lang="en",
            use_gpu=False,           # CPU only — preserves vLLM GPU VRAM
            show_log=False,          # suppress PaddlePaddle verbose output
            det_db_box_thresh=0.3,   # lower threshold catches faint handwriting
            det_db_unclip_ratio=1.6, # expand bounding boxes slightly for context
        )
        print("[ocr] PaddleOCR ready.")
    return _paddle_ocr


# ── Image utilities ───────────────────────────────────────────────────────────

def _crop_line_region(img_array: np.ndarray, box: list) -> "np.ndarray | None":
    """
    Perspective-correct crop of one text line bounding box.

    box is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] — four corners, clockwise
    from top-left, as returned by PaddleOCR.

    Returns a flat (deskewed) rectangle of the line, ready for TrOCR.
    Returns None if the box is degenerate (zero area).
    """
    import cv2

    pts = np.array(box, dtype=np.float32)

    width = int(max(
        np.linalg.norm(pts[0] - pts[1]),
        np.linalg.norm(pts[2] - pts[3]),
    ))
    height = int(max(
        np.linalg.norm(pts[1] - pts[2]),
        np.linalg.norm(pts[0] - pts[3]),
    ))

    if width < 5 or height < 5:
        return None

    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(pts, dst)
    cropped = cv2.warpPerspective(img_array, M, (width, height))
    return cropped


def _trocr_on_line(processor, model, img_array: np.ndarray) -> str:
    """
    Run TrOCR on a single pre-cropped line image.

    TrOCR expects the input to be a legible, roughly horizontal text line.
    Heights below 32px are upscaled to avoid degraded recognition.
    max_new_tokens=128 is sufficient for any single handwritten line.
    """
    import torch

    line_pil = Image.fromarray(img_array).convert("RGB")

    if line_pil.height < 32:
        scale = 64.0 / line_pil.height
        line_pil = line_pil.resize(
            (int(line_pil.width * scale), 64), Image.LANCZOS
        )

    pixel_values = processor(images=line_pil, return_tensors="pt").pixel_values
    with torch.no_grad():
        generated_ids = model.generate(pixel_values, max_new_tokens=128)
    return processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()


# ── Main OCR pipeline (runs synchronously in thread executor) ─────────────────

def _sync_run_ocr_pipeline(image_path: str) -> dict:
    """
    Full OCR pipeline for one image:
      Phase 1 — PaddleOCR full pipeline (det+rec+cls):
                 detects text line bounding boxes and gives confidence scores.
      Phase 2 — TrOCR on each cropped line:
                 provides handwriting-optimised recognition per line.

    Returns a dict with:
      raw_text       — assembled multi-line text (newline-separated)
      confidence     — average PaddleOCR detection confidence (0.0–1.0)
      ocr_engine     — "paddleocr+trocr"
      lines_detected — number of text lines PaddleOCR found
    """
    paddle = _load_paddle()
    processor, model = _load_trocr()

    img_pil = Image.open(image_path).convert("RGB")
    img_array = np.array(img_pil)

    print(
        f"[ocr] Processing image: {image_path.split('/')[-1]} "
        f"({img_pil.width}×{img_pil.height}px)"
    )

    # ── Phase 1: PaddleOCR full pipeline ─────────────────────────────────────
    # det=True, rec=True, cls=True gives us:
    #   result[0] = list of [bounding_box, (paddle_text, confidence_score)]
    paddle_result = paddle.ocr(image_path, det=True, rec=True, cls=True)

    if not paddle_result or not paddle_result[0]:
        print("[ocr] PaddleOCR found no text regions in the image.")
        return {
            "raw_text": "",
            "confidence": 0.0,
            "ocr_engine": "paddleocr+trocr",
            "lines_detected": 0,
        }

    lines = paddle_result[0]

    # Sort top-to-bottom by the y-coordinate of the first (top-left) corner
    lines_sorted = sorted(lines, key=lambda ln: ln[0][0][1])

    # Collect PaddleOCR detection confidence scores
    confidence_scores = []
    for ln in lines_sorted:
        try:
            score = float(ln[1][1])
            if 0.0 <= score <= 1.0:
                confidence_scores.append(score)
        except (IndexError, TypeError, ValueError):
            pass

    avg_confidence = float(np.mean(confidence_scores)) if confidence_scores else 0.0

    print(
        f"[ocr] PaddleOCR detected {len(lines_sorted)} line(s), "
        f"avg confidence={avg_confidence:.3f}"
    )

    # ── Phase 2: TrOCR per line ───────────────────────────────────────────────
    texts = []
    for i, line in enumerate(lines_sorted):
        box = line[0]

        # PaddleOCR recognition output (used as fallback if TrOCR returns nothing)
        try:
            paddle_text = str(line[1][0]).strip() if line[1] else ""
            paddle_score = float(line[1][1]) if line[1] else 0.0
        except (IndexError, TypeError):
            paddle_text = ""
            paddle_score = 0.0

        # Crop and deskew the line region
        cropped = _crop_line_region(img_array, box)
        if cropped is None:
            print(f"[ocr] Line {i + 1}: degenerate bounding box — skipping.")
            continue

        # TrOCR recognition on the cropped line
        trocr_text = _trocr_on_line(processor, model, cropped)

        print(
            f"[ocr] Line {i + 1}: "
            f"paddle={paddle_text!r} (conf={paddle_score:.2f}) | "
            f"trocr={trocr_text!r}"
        )

        # Prefer TrOCR; fall back to PaddleOCR recognition if TrOCR returns nothing
        chosen = trocr_text if trocr_text.strip() else paddle_text
        if chosen:
            texts.append(chosen)

    raw_text = "\n".join(texts)

    print(
        f"[ocr] Complete: {len(texts)} line(s) extracted | "
        f"confidence={avg_confidence:.3f} | "
        f"raw_text={len(raw_text)} chars"
    )

    return {
        "raw_text": raw_text,
        "confidence": round(avg_confidence, 3),
        "ocr_engine": "paddleocr+trocr",
        "lines_detected": len(lines_sorted),
    }


# ── Public async entry point ──────────────────────────────────────────────────

async def process_ocr_image(image_path: str) -> dict:
    """
    Async wrapper: runs the synchronous OCR pipeline in the thread executor
    so it never blocks the FastAPI event loop.

    Raises RuntimeError if either model fails to load or the pipeline crashes.
    Returns a result dict with raw_text="" when no text is detected (not an error).
    """
    loop = asyncio.get_event_loop()
    ocr_result = await loop.run_in_executor(
        _ocr_executor, _sync_run_ocr_pipeline, image_path
    )

    raw_text = ocr_result["raw_text"]
    confidence = ocr_result["confidence"]

    # Guard: only call Qwen cleanup if there is real text to process.
    # If raw_text is empty, returning immediately prevents Qwen from
    # generating a "no text to clean" response that would be shown as
    # the extracted text in the UI.
    if len(raw_text.strip()) < 5:
        print(
            f"[ocr] raw_text is empty or too short ({len(raw_text.strip())} chars) — "
            "skipping Qwen cleanup."
        )
        return {
            "raw_text": raw_text,
            "cleaned_text": "",
            "note_type": "other",
            "confidence": confidence,
            "ocr_engine": ocr_result["ocr_engine"],
            "lines_detected": ocr_result["lines_detected"],
        }

    from services.ai_service import clean_ocr_text
    cleaned_text, note_type = await clean_ocr_text(raw_text)

    return {
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "note_type": note_type,
        "confidence": confidence,
        "ocr_engine": ocr_result["ocr_engine"],
        "lines_detected": ocr_result["lines_detected"],
    }
