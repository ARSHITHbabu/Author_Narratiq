"""
Stage 11 — Phase 2 rule R12: request-time vector similarity now runs in
pgvector (services/vector_math.py). The results must equal the cosine the numpy
code computed before, so voice check, thread clustering and style drift keep
their thresholds' meaning.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_vector_math.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402  (reference implementation only)
import pytest  # noqa: E402

from database import SessionLocal  # noqa: E402
from services.vector_math import cosine, cosine_pairs  # noqa: E402


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


def _np_cos(a, b):
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_pairwise_matches_numpy_on_bge_sized_vectors(db):
    rng = np.random.default_rng(11)
    vecs = rng.normal(size=(12, 1024)).tolist()
    got = cosine_pairs(db, vecs)
    assert len(got) == 12 * 11 // 2
    for (i, j), sim in got.items():
        assert i < j
        assert sim == pytest.approx(_np_cos(vecs[i], vecs[j]), abs=1e-5)


def test_identical_and_opposite_vectors(db):
    v = [0.1] * 1024
    assert cosine(db, v, v) == pytest.approx(1.0, abs=1e-6)
    assert cosine(db, v, [-x for x in v]) == pytest.approx(-1.0, abs=1e-6)


def test_zero_vector_is_skipped_not_nan(db):
    assert cosine(db, [0.0] * 1024, [0.3] * 1024) is None


def test_fewer_than_two_vectors(db):
    assert cosine_pairs(db, []) == {}
    assert cosine_pairs(db, [[1.0] * 1024]) == {}


def test_no_numpy_cosine_left_in_phase2_routers():
    """R12 guard: the three Phase 2 sites must not compute cosine in numpy again."""
    root = Path(__file__).resolve().parents[1]
    for rel in ("routers/characters.py", "routers/narrative_threads.py", "routers/analysis.py"):
        src = (root / rel).read_text()
        assert "np.linalg.norm" not in src and "np.dot" not in src, rel
