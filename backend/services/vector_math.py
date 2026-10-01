"""
Vector similarity through pgvector, for vectors that are NOT stored rows.

Phase 2 rule R12: "All vector similarity computations use pgvector SQL with the
<=> operator. numpy cosine ... must not be reintroduced." Three Phase 2
features compare vectors computed for the request (dialogue passages, thread
names, chapter-group centroids) and used numpy cosine for it (found by the
Stage 11 Phase 2 acceptance). These helpers compute the same cosine with
pgvector's `<=>` in ONE query per call, so every similarity in those features
has one implementation, the database's, and nothing needs to be written to a
table.

Zero vectors: pgvector returns NaN for a zero-norm vector. Those pairs come back
as None, which is the same "skip" the numpy code applied.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session


def _literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def cosine_pairs(db: Session, vectors: Sequence[Sequence[float]]) -> dict[tuple[int, int], Optional[float]]:
    """Cosine similarity for every pair i < j, computed by pgvector in one query.
    Returns {(i, j): similarity or None}."""
    n = len(vectors)
    if n < 2:
        return {}
    values = ", ".join(f"({i}, CAST(:v{i} AS vector))" for i in range(n))
    sql = text(
        f"WITH v(i, e) AS (VALUES {values}) "
        "SELECT a.i, b.i, 1 - (a.e <=> b.e) FROM v a JOIN v b ON a.i < b.i"
    )
    params = {f"v{i}": _literal(vec) for i, vec in enumerate(vectors)}
    out: dict[tuple[int, int], Optional[float]] = {}
    for i, j, sim in db.execute(sql, params):
        out[(int(i), int(j))] = None if sim is None or math.isnan(float(sim)) else float(sim)
    return out


def cosine(db: Session, a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    """Cosine similarity of two vectors via pgvector, or None if either has zero norm."""
    return cosine_pairs(db, [a, b]).get((0, 1))
