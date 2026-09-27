"""
The app's HTTP routes as (full path, methods, route) — for route-driven tests.

FastAPI ≥0.140 keeps included routers lazily (`app.routes` holds
`_IncludedRouter` entries, and each APIRoute's own `.path` lacks the include
prefix); older FastAPI flattens them into `app.routes`. The runtime on the pod
is whatever `start-narratiq.sh` installs (vLLM pulls FastAPI in unpinned), so
the tests must work with both.
"""
from __future__ import annotations

from fastapi.routing import APIRoute


def api_routes(app) -> list[tuple[str, set[str], APIRoute]]:
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:
        return [(r.path, set(r.methods), r) for r in app.routes if isinstance(r, APIRoute)]
    return [(c.path, set(c.methods), c.route) for c in iter_route_contexts(app.routes)
            if isinstance(c.route, APIRoute)]
