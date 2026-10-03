#!/usr/bin/env python3
"""
Stage 12 Tranche 3 addendum — what does extract_cast return on the retrieval
fixture, run after run, and where does a missing character go?

For each run it records the RAW model JSON per window (names + presence + role)
and the FINAL merged cast, so a lost or relabelled character can be traced to
the model or to post-processing. Live model; no database writes.

  cd backend && python3 scripts/quality/cast_variability_probe.py 25 /tmp/cast.json
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from routers.search import _html_to_plain  # noqa: E402
from services import ai_service  # noqa: E402
from tests.fixtures.retrieval_fixture import CHAPTERS  # noqa: E402

EXPECTED = {"mira": "protagonist", "corvin ashe": "supporting", "hessa lin": "supporting", "ondrej vell": "antagonist"}


def _raw_array(text: str):
    """The model's JSON array as returned, for the record only (plain json, not
    the production parser: extract_cast itself parses exactly as before)."""
    text = text or ""
    start, end = text.find("["), text.rfind("]")
    try:
        return json.loads(text[start:end + 1]) if 0 <= start < end else None
    except ValueError:
        return None


def _key(name: str) -> str | None:
    low = (name or "").lower()
    return next((k for k in EXPECTED if k in low), None)


async def main(n: int, out: str):
    real = ai_service._complete
    raw_calls: list = []

    async def recording(*a, **kw):
        text = await real(*a, **kw)
        raw_calls.append(text)
        return text
    ai_service._complete = recording
    texts = [_html_to_plain(c["content"]) for c in CHAPTERS]
    runs = []
    for i in range(n):
        raw_calls.clear()
        final = await ai_service.extract_cast(texts)
        raw = []
        for t in raw_calls:
            parsed = _raw_array(t)
            raw.append([{k: c.get(k) for k in ("name", "presence", "role", "status")} for c in parsed]
                       if isinstance(parsed, list) else {"unparsed": (t or "")[:300]})
        on_page = [c for c in final if c.get("presence", "on_page") == "on_page"]
        row = {"run": i, "windows": len(raw_calls), "raw": raw,
               "final": [{k: c.get(k) for k in ("name", "presence", "role", "status", "evidence_snippet",
                                                "first_appearance", "_possible_duplicate_in_batch",
                                                "_possible_combined_with")} for c in final],
               "on_page": [c["name"] for c in on_page], "pass": len(on_page) == 4}
        ondrej = [c for c in final if _key(c.get("name")) == "ondrej vell"]
        row["ondrej_final"] = ondrej
        row["ondrej_raw"] = [c for w in raw if isinstance(w, list) for c in w if _key(c.get("name")) == "ondrej vell"]
        runs.append(row)
        print(f"run {i:2d} pass={row['pass']} on_page={row['on_page']} "
              f"ondrej={[ (c['name'], c.get('presence'), c.get('role')) for c in ondrej ]}", flush=True)
    Path(out).write_text(json.dumps({"runs": runs, "pass": sum(r["pass"] for r in runs), "n": n}, indent=2,
                                    ensure_ascii=False))

asyncio.run(main(int(sys.argv[1]), sys.argv[2]))
