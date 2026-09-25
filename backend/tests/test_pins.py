"""
Stage 7 task 7.5 (P3-01 pins), 7.8 (lineage), 7.11 (promotion) and the
cross-user isolation requirement. Integration tests against the allow-listed
test database: real HTTP calls through FastAPI, assertions on persisted rows.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_pins.py -q
"""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _phase3_helpers import pin_payload, tiny_plan, two_authors  # noqa: E402
from config import settings  # noqa: E402
from models import AiGenerationPin, Chapter, NoteCard, Story  # noqa: E402


@pytest.fixture(autouse=True)
def _no_background_embedding(monkeypatch):
    monkeypatch.setattr(settings, "pin_store_embedding", False)


def _pin(client, author, **kw):
    r = client.post(f"/api/stories/{author.sid}/ai/pins", headers=author.headers, json=pin_payload(**kw))
    assert r.status_code in (200, 201), r.text
    return r.json()


# ── Lifecycle ────────────────────────────────────────────────────────────────

def test_pin_create_persists_with_materialised_expiry():
    with two_authors() as (db, a, _b, client):
        before = datetime.utcnow()
        out = _pin(client, a, chapter_id=a.chapters[0].chapter_id)
        pin = out["pin"]
        assert out["already_pinned"] is False and out["limits"] == {"used": 1, "max": 20, "plan": "free"}
        row = db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pin["pin_id"]).one()
        # 7-day free TTL (D3), written at insert.
        assert timedelta(days=6, hours=23) < row.expires_at - before < timedelta(days=7, minutes=1)
        assert row.content_sha256 and row.content_bytes > 0 and row.word_count == 7
        assert row.root_pin_id == row.pin_id and row.lineage_depth == 0
        assert row.embedding is None


def test_list_returns_preview_not_body_and_detail_returns_body():
    with two_authors() as (_db, a, _b, client):
        long = "Word " * 100
        pid = _pin(client, a, content=long)["pin"]["pin_id"]
        lst = client.get(f"/api/stories/{a.sid}/ai/pins", headers=a.headers).json()
        assert lst["total"] == 1 and "content" not in lst["pins"][0]
        assert len(lst["pins"][0]["preview"]) <= 181
        detail = client.get(f"/api/stories/{a.sid}/ai/pins/{pid}", headers=a.headers).json()
        assert detail["content"] == long


def test_same_content_twice_is_deduplicated():
    with two_authors() as (db, a, _b, client):
        first = _pin(client, a)
        r = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers, json=pin_payload())
        assert r.status_code == 200 and r.json()["already_pinned"] is True
        assert r.json()["pin"]["pin_id"] == first["pin"]["pin_id"]
        assert db.query(AiGenerationPin).filter(AiGenerationPin.user_id == a.uid).count() == 1


def test_cap_returns_409_with_oldest_pin_and_never_evicts_silently(monkeypatch):
    tiny_plan(monkeypatch)
    with two_authors(plan_a="test_tiny") as (db, a, _b, client):
        p1 = _pin(client, a, content="first")["pin"]["pin_id"]
        _pin(client, a, content="second")
        r = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers, json=pin_payload(content="third"))
        assert r.status_code == 409
        body = r.json()
        assert body["code"] == "pin_limit_reached" and body["limits"] == {"used": 2, "max": 2, "plan": "test_tiny"}
        assert body["oldest_pin"]["pin_id"] == p1
        assert isinstance(body["detail"], str)
        assert db.query(AiGenerationPin).filter(AiGenerationPin.user_id == a.uid).count() == 2
        # Explicit author choice replaces the oldest.
        r = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers,
                        json=pin_payload(content="third", replace_oldest=True))
        assert r.status_code == 201
        db.expire_all()
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == p1).count() == 0


def test_concurrent_pins_at_cap_cannot_exceed_it(monkeypatch):
    """E16 — the advisory lock makes the cap exact under concurrency."""
    import threading
    from fastapi.testclient import TestClient
    import main
    tiny_plan(monkeypatch, max_pins=3)
    with two_authors(plan_a="test_tiny") as (db, a, _b, _client):
        codes = []

        def worker(i):
            c = TestClient(main.app)
            codes.append(c.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers,
                                json=pin_payload(content=f"concurrent {i}")).status_code)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        db.expire_all()
        assert db.query(AiGenerationPin).filter(AiGenerationPin.user_id == a.uid).count() == 3
        assert sorted(codes).count(201) == 3 and sorted(codes).count(409) == 5


def test_oversized_content_returns_413():
    with two_authors() as (_db, a, _b, client):
        r = client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers, json=pin_payload(content="x" * 8001))
        assert r.status_code == 413 and r.json()["code"] == "pin_too_large"


def test_source_excerpt_is_capped():
    with two_authors() as (db, a, _b, client):
        pid = _pin(client, a, source_excerpt="m" * 5000)["pin"]["pin_id"]
        row = db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).one()
        assert len(row.source_excerpt) == settings.pin_source_excerpt_chars


def test_patch_label_favourite_and_plan_gated_extension(monkeypatch):
    with two_authors(plan_b="pro") as (db, a, b, client):
        pid = _pin(client, a)["pin"]["pin_id"]
        r = client.patch(f"/api/stories/{a.sid}/ai/pins/{pid}", headers=a.headers,
                         json={"label": "v3", "is_favourite": True})
        assert r.status_code == 200 and r.json()["label"] == "v3" and r.json()["is_favourite"] is True
        r = client.patch(f"/api/stories/{a.sid}/ai/pins/{pid}", headers=a.headers, json={"extend_ttl": True})
        assert r.status_code == 422 and r.json()["code"] == "extend_not_in_plan"
        # pro can extend, capped by max_total_pin_age_days.
        bp = _pin(client, b)["pin"]["pin_id"]
        row = db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == bp).one()
        row.expires_at = datetime.utcnow() + timedelta(days=1)
        db.commit()
        r = client.patch(f"/api/stories/{b.sid}/ai/pins/{bp}", headers=b.headers, json={"extend_ttl": True})
        assert r.status_code == 200
        db.expire_all()
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == bp).one().expires_at > datetime.utcnow() + timedelta(days=80)
        row = db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == bp).one()
        row.created_at = datetime.utcnow() - timedelta(days=settings.max_total_pin_age_days)
        db.commit()
        r = client.patch(f"/api/stories/{b.sid}/ai/pins/{bp}", headers=b.headers, json={"extend_ttl": True})
        assert r.status_code == 422 and r.json()["code"] == "extension_limit_reached"


def test_delete_and_applied():
    with two_authors() as (db, a, _b, client):
        pid = _pin(client, a)["pin"]["pin_id"]
        r = client.post(f"/api/stories/{a.sid}/ai/pins/{pid}/applied", headers=a.headers)
        assert r.status_code == 200 and r.json()["applied_at"]
        assert client.delete(f"/api/stories/{a.sid}/ai/pins/{pid}", headers=a.headers).status_code == 204
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).count() == 0


# ── Expiry, cascades ─────────────────────────────────────────────────────────

def test_expired_pins_are_invisible_then_swept():
    import main
    with two_authors() as (db, a, _b, client):
        pid = _pin(client, a)["pin"]["pin_id"]
        keep = _pin(client, a, content="still live")["pin"]["pin_id"]
        db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).update(
            {"expires_at": datetime.utcnow() - timedelta(minutes=1)})
        db.commit()
        # Past expires_at = gone to the author immediately, before the sweep runs.
        assert client.get(f"/api/stories/{a.sid}/ai/pins/{pid}", headers=a.headers).status_code == 404
        assert client.get(f"/api/stories/{a.sid}/ai/pins", headers=a.headers).json()["total"] == 1
        removed = asyncio.run(main._cleanup_expired_pins())
        assert removed >= 1
        db.expire_all()
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).count() == 0
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == keep).count() == 1


def test_deleting_story_deletes_its_pins_and_chapter_delete_nulls_reference():
    with two_authors() as (db, a, _b, client):
        pid = _pin(client, a, chapter_id=a.chapters[2].chapter_id)["pin"]["pin_id"]
        ch = db.query(Chapter).filter(Chapter.chapter_id == a.chapters[2].chapter_id).one()
        db.delete(ch)
        db.commit()
        db.expire_all()
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).one().chapter_id is None
        r = client.delete(f"/api/projects/{a.sid}", headers=a.headers)
        assert r.status_code == 200, r.text
        db.expire_all()
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).count() == 0


# ── Lineage (P3-06) ─────────────────────────────────────────────────────────

def test_lineage_recorded_and_depth_capped(monkeypatch):
    monkeypatch.setattr(settings, "max_lineage_depth", 2)
    with two_authors() as (db, a, _b, client):
        root = _pin(client, a, content="v1")["pin"]
        c1 = _pin(client, a, content="v2", parent_pin_id=root["pin_id"], derivation="variation")["pin"]
        c2 = _pin(client, a, content="v3", parent_pin_id=c1["pin_id"], derivation="improve")["pin"]
        assert (c1["root_pin_id"], c1["lineage_depth"], c1["parent_pin_id"]) == (root["pin_id"], 1, root["pin_id"])
        assert (c2["root_pin_id"], c2["lineage_depth"]) == (root["pin_id"], 2)
        c3 = _pin(client, a, content="v4", parent_pin_id=c2["pin_id"])["pin"]
        assert c3["lineage_depth"] == 0 and c3["root_pin_id"] == c3["pin_id"]     # beyond cap → new root
        assert c2["pin_id"] in c3["derived_from_pin_ids"]                           # provenance kept
        tree = client.get(f"/api/stories/{a.sid}/ai/pins?root_pin_id={root['pin_id']}", headers=a.headers).json()
        assert {p["pin_id"] for p in tree["pins"]} == {root["pin_id"], c1["pin_id"], c2["pin_id"]}
        # Expired ancestor: child keeps root, parent becomes NULL (E7).
        db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == root["pin_id"]).delete()
        db.commit()
        db.expire_all()
        child = db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == c1["pin_id"]).one()
        assert child.parent_pin_id is None and child.root_pin_id == root["pin_id"]


# ── Promotion to the Idea Shelf (P3-09) ──────────────────────────────────────

def test_promote_creates_permanent_card_that_survives_pin_expiry():
    import main
    with two_authors() as (db, a, _b, client):
        pid = _pin(client, a, content="A twist for act three.")["pin"]["pin_id"]
        r = client.post(f"/api/stories/{a.sid}/ai/pins/{pid}/promote", headers=a.headers,
                        json={"card_type": "plot_twist", "title": "Twist", "tags": ["act3"],
                              "target_chapter_id": a.chapters[1].chapter_id, "release_pin": False})
        assert r.status_code == 201, r.text
        card = r.json()["card"]
        assert card["source_pin_id"] == pid and card["status"] == "open" and card["tags"] == ["act3"]
        db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).update(
            {"expires_at": datetime.utcnow() - timedelta(seconds=1)})
        db.commit()
        asyncio.run(main._cleanup_expired_pins())
        db.expire_all()
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == pid).count() == 0
        kept = db.query(NoteCard).filter(NoteCard.card_id == card["card_id"]).one()
        assert kept.content == "A twist for act three." and kept.source_pin_id == pid


def test_promote_with_release_deletes_pin_and_respects_idea_cap(monkeypatch):
    tiny_plan(monkeypatch, max_idea_cards=1, max_pins=5)
    with two_authors(plan_a="test_tiny") as (db, a, _b, client):
        p1 = _pin(client, a, content="idea one")["pin"]["pin_id"]
        p2 = _pin(client, a, content="idea two")["pin"]["pin_id"]
        r = client.post(f"/api/stories/{a.sid}/ai/pins/{p1}/promote", headers=a.headers, json={"card_type": "future_scene"})
        assert r.status_code == 201 and r.json()["pin_released"] is True
        assert db.query(AiGenerationPin).filter(AiGenerationPin.pin_id == p1).count() == 0
        r = client.post(f"/api/stories/{a.sid}/ai/pins/{p2}/promote", headers=a.headers, json={"card_type": "future_scene"})
        assert r.status_code == 409 and r.json()["code"] == "idea_limit_reached"


# ── Cross-user isolation: foreign ≡ non-existent (author requirement 3) ──────

def _same(r1, r2):
    assert r1.status_code == r2.status_code, (r1.status_code, r2.status_code)
    assert r1.json() == r2.json(), (r1.json(), r2.json())


def test_foreign_and_nonexistent_pins_are_indistinguishable_on_every_route():
    with two_authors() as (_db, a, b, client):
        bpin = _pin(client, b)["pin"]["pin_id"]
        fake = "00000000-0000-0000-0000-000000000000"
        # A tries B's pin id through A's OWN story, and through B's story.
        for sid in (a.sid, b.sid):
            base = f"/api/stories/{sid}/ai/pins"
            _same(client.get(f"{base}/{bpin}", headers=a.headers), client.get(f"{base}/{fake}", headers=a.headers))
            _same(client.patch(f"{base}/{bpin}", headers=a.headers, json={"label": "x"}),
                  client.patch(f"{base}/{fake}", headers=a.headers, json={"label": "x"}))
            _same(client.delete(f"{base}/{bpin}", headers=a.headers), client.delete(f"{base}/{fake}", headers=a.headers))
            _same(client.post(f"{base}/{bpin}/applied", headers=a.headers), client.post(f"{base}/{fake}/applied", headers=a.headers))
            _same(client.post(f"{base}/{bpin}/promote", headers=a.headers, json={}),
                  client.post(f"{base}/{fake}/promote", headers=a.headers, json={}))
        # As a parent_pin_id reference.
        _same(client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers, json=pin_payload(content="c1", parent_pin_id=bpin)),
              client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers, json=pin_payload(content="c1", parent_pin_id=fake)))
        # B's pin untouched.
        assert client.get(f"/api/stories/{b.sid}/ai/pins/{bpin}", headers=b.headers).status_code == 200


def test_foreign_and_nonexistent_story_and_chapter_ids_are_indistinguishable():
    with two_authors() as (_db, a, b, client):
        fake = "00000000-0000-0000-0000-000000000000"
        for path, method, body in [
            ("/ai/pins", "post", pin_payload()), ("/ai/pins", "get", None),
            ("/ai/preferences", "get", None), ("/ai/preferences", "patch", {"preserve_tone": False}),
            ("/ai/similarity", "post", {"text": "hello"}),
        ]:
            r1 = getattr(client, method)(f"/api/stories/{b.sid}{path}", headers=a.headers, **({"json": body} if body else {}))
            r2 = getattr(client, method)(f"/api/stories/{fake}{path}", headers=a.headers, **({"json": body} if body else {}))
            assert r1.status_code == 404, (path, r1.status_code)
            _same(r1, r2)
        _same(client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers, json=pin_payload(chapter_id=b.chapters[0].chapter_id)),
              client.post(f"/api/stories/{a.sid}/ai/pins", headers=a.headers, json=pin_payload(chapter_id=fake)))


def test_batch_pin_ids_foreign_vs_nonexistent_give_identical_generic_warning():
    with two_authors() as (_db, a, b, client):
        bpin = _pin(client, b)["pin"]["pin_id"]
        fake = "00000000-0000-0000-0000-000000000000"
        r1 = client.post(f"/api/stories/{a.sid}/ai/similarity", headers=a.headers, json={"text": "x", "against_pin_ids": [bpin]})
        r2 = client.post(f"/api/stories/{a.sid}/ai/similarity", headers=a.headers, json={"text": "x", "against_pin_ids": [fake]})
        _same(r1, r2)
        assert r1.status_code == 200 and r1.json()["matches"] == []
        assert "not available" in r1.json()["warnings"][0]["message"]


def test_listing_never_shows_another_authors_pins():
    with two_authors() as (_db, a, b, client):
        _pin(client, b)
        assert client.get(f"/api/stories/{a.sid}/ai/pins", headers=a.headers).json()["total"] == 0
        assert client.get(f"/api/ai/limits", headers=a.headers).json()["usage"]["pins"] == 0


def test_note_cards_foreign_and_nonexistent_are_indistinguishable():
    with two_authors() as (_db, a, b, client):
        card = client.post(f"/api/ocr/{b.sid}/note-cards", headers=b.headers, json={"content": "B's card"}).json()
        fake = "00000000-0000-0000-0000-000000000000"
        _same(client.patch(f"/api/ocr/note-cards/{card['card_id']}", headers=a.headers, json={"title": "x"}),
              client.patch(f"/api/ocr/note-cards/{fake}", headers=a.headers, json={"title": "x"}))
        _same(client.delete(f"/api/ocr/note-cards/{card['card_id']}", headers=a.headers),
              client.delete(f"/api/ocr/note-cards/{fake}", headers=a.headers))
        # A cannot target B's chapter from A's own card.
        own = client.post(f"/api/ocr/{a.sid}/note-cards", headers=a.headers, json={"content": "A's"}).json()
        _same(client.patch(f"/api/ocr/note-cards/{own['card_id']}", headers=a.headers,
                           json={"target_chapter_id": b.chapters[0].chapter_id}),
              client.patch(f"/api/ocr/note-cards/{own['card_id']}", headers=a.headers, json={"target_chapter_id": fake}))
