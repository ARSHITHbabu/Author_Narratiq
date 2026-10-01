"""
Stage 11 — Phase 2 rule R7 for P2-03 (dialogue voice consistency): the 200-chapter
test took 91.9 s for 110 dialogue passages, inside a ~100 s proxy limit. The
check now analyses at most 80 passages, sampled evenly across the manuscript
(first and last kept), embeds them in one batch, describes flagged pairs
concurrently, and says in `note` how many it analysed. No model: embeddings and
descriptions are stubbed.

    DATABASE_URL=...narratiq_test pytest backend/tests/test_voice_check_scale.py -q
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Chapter, Character, CharacterMention, Story, User  # noqa: E402
from routers.auth import create_token, hash_password  # noqa: E402
from services import ai_service  # noqa: E402
from services.account_deletion import delete_account  # noqa: E402


def _seed(n_passages: int):
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    u = User(email=f"s11-voice-{tag}@narratiq-internal-test.com", username=f"s11v{tag}",
             hashed_password=hash_password("x"))
    db.add(u); db.flush()
    s = Story(user_id=u.user_id, title="Voice scale"); db.add(s); db.flush()
    c = Character(story_id=s.story_id, user_id=u.user_id, name="Devika", aliases=[]); db.add(c); db.flush()
    for n in range(1, n_passages + 1):
        ch = Chapter(story_id=s.story_id, title=f"Chapter {n}", chapter_number=n, content="<p>x</p>")
        db.add(ch); db.flush()
        db.add(CharacterMention(character_id=c.character_id, story_id=s.story_id, chapter_id=ch.chapter_id,
                                chapter_number=n, passage_text=f'"Line {n}," Devika said.'))
    db.commit()
    return db, u, s, c


@pytest.mark.parametrize("n_passages, expected_analysed", [(120, 80), (40, 40)])
def test_voice_check_caps_and_batches(monkeypatch, n_passages, expected_analysed):
    calls = {"embed_batches": [], "described": 0}
    rng = np.random.default_rng(3)

    async def fake_embed_texts(texts, batch_size=32):
        calls["embed_batches"].append(list(texts))
        return rng.normal(size=(len(texts), 1024)).tolist()   # random → low similarity → flagged pairs

    async def fake_describe(character_name, passage_pairs):
        pairs = passage_pairs
        calls["described"] += len(pairs)
        return [{"description": "Different register."} for _ in pairs]

    monkeypatch.setattr(ai_service, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(ai_service, "check_dialogue_consistency", fake_describe)
    db, u, s, c = _seed(n_passages)
    try:
        r = TestClient(main.app).post(
            f"/api/stories/{s.story_id}/characters/{c.character_id}/voice-check",
            headers={"Authorization": f"Bearer {create_token(u.user_id)}"}, json={})
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(calls["embed_batches"]) == 1                     # one batched embed call
        batch = calls["embed_batches"][0]
        assert len(batch) == expected_analysed
        assert batch[0].startswith('"Line 1,') and batch[-1].startswith(f'"Line {n_passages},')  # ends kept
        assert j["dialogue_count"] == n_passages                     # total found is still reported
        if n_passages > expected_analysed:
            assert f"Analysed {expected_analysed} of {n_passages} passages" in j["note"]
        else:
            assert not j["note"] or "Analysed" not in j["note"]
        assert calls["described"] <= 10
        assert 0.0 <= j["consistency_score"] <= 1.0 or j["consistency_score"] < 0.2   # random vectors ~0
    finally:
        db.rollback(); delete_account(db, u.user_id); db.close()
