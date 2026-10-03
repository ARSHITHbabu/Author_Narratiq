"""
Stage 12 Tranche 3 (A19) — configuration record for every security probe output.

Earlier probe files could not be tied to the code or prompts that produced
them. Each probe now writes this block next to its results:

  commit            `git rev-parse HEAD` of the checkout the probe ran from,
                    plus whether the working tree had uncommitted changes
  prompt_version    the PROMPT_VERSION this process resolves (config.settings)
  prompt_injection_guard, output check constants
  vllm_model        what the model server reports it is serving
  qwen_revision     the pinned Hugging Face revision (scripts/download_models.sh,
                    or NARRATIQ_QWEN_REVISION when set)

Run the probe with the same environment as the backend it calls (the
documented isolated backend on :8100); the prompt settings are read from this
process, not from the server.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import subprocess
from pathlib import Path

import httpx

_REPO = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(_REPO), *args], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001 — a missing git binary must not stop a probe
        return ""


def _qwen_revision() -> str:
    if os.environ.get("NARRATIQ_QWEN_REVISION"):
        return os.environ["NARRATIQ_QWEN_REVISION"]
    try:
        text = (_REPO / "scripts" / "download_models.sh").read_text()
    except OSError:
        return ""
    m = re.search(r'QWEN_REVISION="\$\{NARRATIQ_QWEN_REVISION:-([0-9a-f]+)\}"', text)
    return m.group(1) if m else ""


def run_metadata() -> dict:
    from config import settings
    from services import prompt_safety

    served = None
    try:
        r = httpx.get(settings.vllm_base_url.rstrip("/") + "/models", timeout=5)
        served = [m.get("id") for m in (r.json() or {}).get("data", [])]
    except Exception:  # noqa: BLE001
        served = None
    return {
        "recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": _git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(_git("status", "--porcelain")),
        "prompt_version": settings.prompt_version,
        "prompt_version_fallback": settings.prompt_version_fallback,
        "prompt_injection_guard": settings.prompt_injection_guard,
        "obeyed_min_span": prompt_safety.OBEYED_MIN_SPAN,
        "obeyed_max_story_share": prompt_safety.OBEYED_MAX_STORY_SHARE,
        "vllm_model": served,
        "qwen_revision": _qwen_revision(),
    }
