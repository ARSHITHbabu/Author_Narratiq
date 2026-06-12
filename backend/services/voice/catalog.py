"""
FEATURE_CATALOG + INTENT_REGISTRY + BGE-M3 shortlist index.

Both structures are DERIVED from capabilities.CAPABILITY_REGISTRY so the three
stay consistent (the plan calls for all three to exist; this keeps them in sync):

  FEATURE_CATALOG  — one entry per capability, with the phrases used to build the
                     BGE-M3 shortlist embedding matrix.
  INTENT_REGISTRY  — {"<capability>.<action>": (capability, action)} lookup /
                     validation table the Qwen classifier output is checked against.

The shortlist matrix is built once at startup (build_catalog_embeddings) and
cached in-process. shortlist() embeds a command and returns the top-k candidate
capabilities by cosine similarity — keeping the Qwen classifier prompt small and
scalable as the platform grows.
"""
from __future__ import annotations

import logging

from .capabilities import CAPABILITY_REGISTRY

logger = logging.getLogger(__name__)

# ── Derived structures ────────────────────────────────────────────────────────

FEATURE_CATALOG: list[dict] = []
INTENT_REGISTRY: dict[str, tuple[str, str]] = {}

for _name, _cap in CAPABILITY_REGISTRY.items():
    FEATURE_CATALOG.append({
        "capability": _name,
        "router": _cap.router,
        "description": _cap.description,
        "phrases": _cap.phrases,
        "actions": list(_cap.actions.keys()),
    })
    for _action in _cap.actions:
        INTENT_REGISTRY[f"{_name}.{_action}"] = (_name, _action)


# ── BGE-M3 shortlist index (built at startup) ─────────────────────────────────

_capabilities: list[str] = []
_matrix = None          # numpy array [n_caps, dim], L2-normalised
_ready = False


def build_catalog_embeddings() -> int:
    """
    Build the capability shortlist matrix using BGE-M3. Each capability is
    represented by the mean of its phrase + description embeddings. Idempotent;
    call once at startup. Returns the number of capabilities indexed.
    """
    global _capabilities, _matrix, _ready
    import numpy as np
    from services.ai_service import embed_text_sync

    caps: list[str] = []
    vecs: list[list[float]] = []
    for entry in FEATURE_CATALOG:
        cap = entry["capability"]
        texts = [entry["description"]] + entry["phrases"]
        embs = [np.asarray(embed_text_sync(t), dtype="float32") for t in texts]
        centroid = np.mean(embs, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        caps.append(cap)
        vecs.append(centroid)

    _capabilities = caps
    _matrix = np.vstack(vecs) if vecs else None
    _ready = True
    logger.info("[voice.catalog] shortlist index built: %d capabilities", len(caps))
    return len(caps)


def is_ready() -> bool:
    return _ready


def shortlist(query: str, k: int = 8) -> list[tuple[str, float]]:
    """
    Return the top-k (capability, cosine_score) candidates for a command string.
    Falls back to returning all capabilities (unscored) if the index is not built.
    """
    if not _ready or _matrix is None:
        return [(e["capability"], 0.0) for e in FEATURE_CATALOG[:k]]
    import numpy as np
    from services.ai_service import embed_text_sync

    q = np.asarray(embed_text_sync(query), dtype="float32")
    n = np.linalg.norm(q)
    if n > 0:
        q = q / n
    scores = _matrix @ q                       # cosine (both normalised)
    idx = np.argsort(-scores)[:k]
    return [(_capabilities[i], float(scores[i])) for i in idx]


def candidate_brief(capabilities: list[str]) -> str:
    """Human/LLM-readable brief of candidate capabilities + their actions —
    injected into the classifier/planner prompt."""
    lines = []
    for name in capabilities:
        cap = CAPABILITY_REGISTRY.get(name)
        if not cap:
            continue
        acts = ", ".join(
            f"{a.action}({a.action_type})" for a in cap.actions.values()
        )
        lines.append(f"- {name}: {cap.description} | actions: {acts}")
    return "\n".join(lines)
