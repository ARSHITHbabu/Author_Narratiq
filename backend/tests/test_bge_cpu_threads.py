"""
Stage 12.1 — BGE-M3 CPU threads follow the container's CPU quota, not the host's
core count (indexing 40 chapters took 44 min: two concurrent encodes ran ~96
torch threads on a 7.65-CPU quota).

  cd backend && python3 -m pytest tests/test_bge_cpu_threads.py -q
"""
import os

import pytest

from services import ai_service as ai


def _cgroup(tmp_path, v2=None, v1=None):
    if v2 is not None:
        (tmp_path / "cpu.max").write_text(v2)
    if v1 is not None:
        (tmp_path / "cpu").mkdir()
        (tmp_path / "cpu" / "cpu.cfs_quota_us").write_text(v1[0])
        (tmp_path / "cpu" / "cpu.cfs_period_us").write_text(v1[1])
    return str(tmp_path)


@pytest.fixture(autouse=True)
def _cores(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 96)


def test_v2_quota_rounds_up(tmp_path):
    assert ai.cpu_quota(_cgroup(tmp_path, v2="765000 100000\n")) == 8


def test_v2_unlimited_uses_cores(tmp_path):
    assert ai.cpu_quota(_cgroup(tmp_path, v2="max 100000\n")) == 96


def test_v1_quota(tmp_path):
    assert ai.cpu_quota(_cgroup(tmp_path, v1=("400000", "100000"))) == 4


def test_v1_unlimited_uses_cores(tmp_path):
    assert ai.cpu_quota(_cgroup(tmp_path, v1=("-1", "100000"))) == 96


def test_no_cgroup_uses_cores(tmp_path):
    assert ai.cpu_quota(str(tmp_path)) == 96


def test_quota_never_exceeds_cores_or_drops_below_one(tmp_path, monkeypatch):
    assert ai.cpu_quota(_cgroup(tmp_path, v2="20000000 100000")) == 96
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    assert ai.cpu_quota(str(tmp_path)) == 1


def test_threads_split_quota_across_bge_workers(monkeypatch):
    monkeypatch.setattr(ai, "cpu_quota", lambda: 8)
    assert ai.bge_cpu_threads() == 8 // ai._bge_executor._max_workers
    monkeypatch.setattr(ai, "cpu_quota", lambda: 1)
    assert ai.bge_cpu_threads() == 1


def test_get_bge_sets_torch_threads_on_cpu(monkeypatch):
    import torch
    calls = []
    monkeypatch.setattr(ai, "_bge_model", None)
    monkeypatch.setattr(ai.settings, "bge_device", "cpu")
    monkeypatch.setattr(ai, "bge_cpu_threads", lambda: 3)
    monkeypatch.setattr(torch, "set_num_threads", calls.append)
    monkeypatch.setattr(ai, "SentenceTransformer", lambda path, device: object())
    ai.get_bge()
    assert calls == [3]


def test_get_bge_leaves_torch_threads_alone_on_cuda(monkeypatch):
    import torch
    calls = []
    monkeypatch.setattr(ai, "_bge_model", None)
    monkeypatch.setattr(ai.settings, "bge_device", "cuda")
    monkeypatch.setattr(torch, "set_num_threads", calls.append)
    monkeypatch.setattr(ai, "SentenceTransformer", lambda path, device: object())
    ai.get_bge()
    assert calls == []
