"""
Stage 12 remediation A2 — OCR (GOT-OCR2.0) works on the pinned transformers.

GOT's vendored modeling_GOT.py calls DynamicCache.seen_tokens and
DynamicCache.get_max_length(), removed from transformers before the pinned
4.57.6; every extraction failed with
"'DynamicCache' object has no attribute 'seen_tokens'"
(docs/issues-and-bugs/ocr-extraction-got-ocr2-dynamiccache-failure.md).

The unit tests need only transformers. The live test runs the real pinned model
on a GPU and is skipped when the weights are absent.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_ocr_compat.py -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


def test_shim_restores_the_two_members_with_their_old_meaning():
    import torch
    from transformers.cache_utils import DynamicCache
    from services.ocr_service import _ensure_got_cache_compat

    _ensure_got_cache_compat()
    cache = DynamicCache()
    assert cache.seen_tokens == 0
    k = torch.zeros(1, 2, 5, 4)
    cache.update(k, k, layer_idx=0)
    assert cache.seen_tokens == cache.get_seq_length() == 5
    cache.update(torch.zeros(1, 2, 1, 4), torch.zeros(1, 2, 1, 4), layer_idx=0)
    assert cache.seen_tokens == 6
    assert cache.get_max_length() is None


def test_shim_is_idempotent_and_never_overrides_existing_members():
    from services.ocr_service import _ensure_got_cache_compat
    _ensure_got_cache_compat()
    assert _ensure_got_cache_compat() == []


def test_vendored_code_still_needs_the_shim():
    """If GOT's code stops using these members, the shim can be retired."""
    from config import settings
    src = Path(settings.got_path) / "modeling_GOT.py"
    if not src.exists():
        pytest.skip("GOT-OCR2.0 weights not downloaded on this machine")
    text = src.read_text()
    assert "past_key_values.seen_tokens" in text
    assert "past_key_values.get_max_length()" in text


@pytest.mark.skipif(os.environ.get("SKIP_LLM_TESTS") == "1", reason="SKIP_LLM_TESTS=1 — real GOT-OCR2.0 on GPU")
def test_real_ocr_reads_a_rendered_page(tmp_path):
    import torch
    from PIL import Image, ImageDraw, ImageFont
    from config import settings
    from services import ocr_service

    if not Path(settings.got_path, "model.safetensors").exists():
        pytest.skip("GOT-OCR2.0 weights not downloaded on this machine")
    if not torch.cuda.is_available():
        pytest.skip("GOT-OCR2.0's vendored code requires a GPU")

    lines = ["The lighthouse keeper climbed the stairs.",
             "Mara counted every boat in the harbour."]
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
    img = Image.new("RGB", (1600, 300), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((60, 60 + i * 110), line, fill="black", font=font)
    path = tmp_path / "page.png"
    img.save(path)

    result = ocr_service._sync_run_got_pipeline(str(path))
    text = " ".join(result["raw_text"].split()).lower()
    for line in lines:
        assert line.lower() in text, result["raw_text"]
    assert result["confidence"] >= 0.9
