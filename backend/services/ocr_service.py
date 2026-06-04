"""
OCR Service — TrOCR (lazy-loaded, CPU)

TrOCR runs on CPU by default so it doesn't compete with vLLM for VRAM.
Loaded on first OCR request, stays loaded for subsequent requests.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from config import settings

_trocr_processor = None
_trocr_model = None
_ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="trocr")


def _load_trocr():
    global _trocr_processor, _trocr_model
    if _trocr_model is None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        _trocr_processor = TrOCRProcessor.from_pretrained(settings.trocr_path)
        _trocr_model = VisionEncoderDecoderModel.from_pretrained(settings.trocr_path)
        # CPU only — keeps vLLM's full VRAM allocation intact
        _trocr_model.to("cpu")
        _trocr_model.eval()
    return _trocr_processor, _trocr_model


def _sync_run_trocr(image_path: str) -> str:
    import torch
    processor, model = _load_trocr()
    image = Image.open(image_path).convert("RGB")
    pixel_values = processor(images=image, return_tensors="pt").pixel_values
    with torch.no_grad():
        generated_ids = model.generate(pixel_values, max_new_tokens=512)
    return processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()


async def process_ocr_image(image_path: str) -> dict:
    loop = asyncio.get_event_loop()
    raw_text = await loop.run_in_executor(_ocr_executor, _sync_run_trocr, image_path)

    from services.ai_service import clean_ocr_text
    cleaned_text, note_type = await clean_ocr_text(raw_text)

    return {
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "note_type": note_type,
        "confidence": 0.85,
        "ocr_engine": "trocr",
    }
