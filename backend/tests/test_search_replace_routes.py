"""
Stage 12 remediation A9 — search & replace through the real routes and database.

  * the count shown, the Replace All preview and the number replaced agree;
  * Replace One rewrites exactly the occurrence the author navigated to;
  * `&amp;` survives replacing "amp"; a replacement like "<b>hello</b>" is stored
    as author text;
  * the pre-replace version snapshot is still written;
  * if a replace would change the chapter's markup, nothing at all is saved;
  * another author's story is 404.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_search_replace_routes.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import two_authors  # noqa: E402
from models import Chapter, StoryVersion  # noqa: E402

HTML = ("<p>Tom &amp; Jerry, ampersand.</p>"
        "<p>old <em>castle</em> then old castle</p>"
        "<h2>The Harbour</h2><ul><li><p>harbour lights</p></li></ul>")


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    from middleware.rate_limit import limiter
    monkeypatch.setattr(limiter, "enabled", False)


def _setup(db, author, html=HTML):
    ch = author.chapters[0]
    db.query(Chapter).filter(Chapter.chapter_id == ch.chapter_id).update({"content": html})
    db.commit()
    return ch.chapter_id


def _content(db, cid):
    db.expire_all()
    return db.get(Chapter, cid).content


def _versions(db, cid):
    return db.query(StoryVersion).filter(StoryVersion.chapter_id == cid).count()


def _search(client, a, q, **kw):
    return client.post(f"/api/search/exact/{a.sid}", headers=a.headers, json={"query": q, **kw}).json()


def _replace(client, a, q, rep, **kw):
    return client.post(f"/api/search/replace/{a.sid}", headers=a.headers,
                       json={"query": q, "replacement": rep, **kw})


def test_count_preview_and_replaced_agree():
    with two_authors() as (db, a, _b, client):
        cid = _setup(db, a)
        for q, kw in (("old castle", {}), ("harbour", {"whole_word": True}), ("amp", {}), ("&", {})):
            shown = _search(client, a, q, chapter_ids=[cid], **kw)["total_matches"]
            preview = _replace(client, a, q, "Z", chapter_ids=[cid], dry_run=True, **kw).json()["replaced_count"]
            assert shown == preview, q
        before = _search(client, a, "old castle", chapter_ids=[cid])["total_matches"]
        r = _replace(client, a, "old castle", "Z", chapter_ids=[cid])
        assert r.status_code == 200 and r.json()["replaced_count"] == before == 2
        assert _search(client, a, "old castle", chapter_ids=[cid])["total_matches"] == 0


def test_amp_entity_and_html_replacement_are_safe():
    with two_authors() as (db, a, _b, client):
        cid = _setup(db, a)
        assert _replace(client, a, "amp", "X", chapter_ids=[cid]).json()["replaced_count"] == 1
        html = _content(db, cid)
        assert "Tom &amp; Jerry, Xersand." in html and "&X;" not in html
        _replace(client, a, "Jerry", "<b>hello</b>", chapter_ids=[cid])
        html = _content(db, cid)
        assert "&lt;b&gt;hello&lt;/b&gt;" in html and "<b>hello</b>" not in html


def test_replace_one_changes_the_navigated_occurrence_and_keeps_a_version():
    with two_authors() as (db, a, _b, client):
        cid = _setup(db, a)
        v0 = _versions(db, cid)
        r = _replace(client, a, "old castle", "X", chapter_ids=[cid], occurrence_index=0)
        assert r.status_code == 200 and r.json()["replaced_count"] == 1
        assert "<p>X<em></em> then old castle</p>" in _content(db, cid)
        assert _versions(db, cid) == v0 + 1
        snap = db.query(StoryVersion).filter(StoryVersion.chapter_id == cid).order_by(
            StoryVersion.version_number.desc()).first()
        assert snap.content == HTML


def test_integrity_guard_saves_nothing(monkeypatch):
    from services import search_match

    def broken(html, *a, **k):
        return html.replace("<em>", "<strong>"), 1

    monkeypatch.setattr(search_match, "replace", broken)
    with two_authors() as (db, a, _b, client):
        cid = _setup(db, a)
        v0 = _versions(db, cid)
        r = _replace(client, a, "old castle", "X", chapter_ids=[cid], occurrence_index=0)
        assert r.status_code == 500
        assert "nothing was changed" in r.json()["detail"]
        assert _content(db, cid) == HTML
        assert _versions(db, cid) == v0


def test_query_length_is_bounded():
    with two_authors() as (db, a, _b, client):
        r = client.post(f"/api/search/exact/{a.sid}", headers=a.headers, json={"query": "x" * 501})
        assert r.status_code == 422


def test_other_authors_story_is_404():
    with two_authors() as (db, a, b, client):
        _setup(db, b)
        assert client.post(f"/api/search/exact/{b.sid}", headers=a.headers, json={"query": "castle"}).status_code == 404
        r = client.post(f"/api/search/replace/{b.sid}", headers=a.headers,
                        json={"query": "castle", "replacement": "x"})
        assert r.status_code == 404
        assert _content(db, b.chapters[0].chapter_id) == HTML
