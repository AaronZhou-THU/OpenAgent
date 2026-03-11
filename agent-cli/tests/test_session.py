"""Tests for agent_cli.session — SessionStore persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_cli.session import SessionMeta, SessionStore


@pytest.fixture
def store(tmp_path) -> SessionStore:
    return SessionStore(tmp_path / "conversations")


class TestSessionCreate:
    """Test session creation."""

    def test_creates_session_dir(self, store):
        meta = store.create(preset="coding", model="test-model")
        assert (store._dir / meta.id).is_dir()

    def test_creates_meta_json(self, store):
        meta = store.create(preset="coding", model="test-model")
        meta_path = store._dir / meta.id / "meta.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert data["preset"] == "coding"
        assert data["model"] == "test-model"

    def test_unique_ids(self, store):
        m1 = store.create(preset="coding", model="m1")
        m2 = store.create(preset="coding", model="m2")
        assert m1.id != m2.id

    def test_updates_index(self, store):
        meta = store.create(preset="coding", model="test-model")
        index = json.loads((store._dir / "index.json").read_text())
        assert len(index) == 1
        assert index[0]["id"] == meta.id


class TestSessionMessages:
    """Test message persistence."""

    def test_save_and_load(self, store):
        meta = store.create(preset="coding", model="m")
        store.save_message(meta.id, {"role": "user", "content": "hello"})
        store.save_message(meta.id, {"role": "assistant", "content": "hi"})
        msgs = store.load_messages(meta.id)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_load_empty_session(self, store):
        meta = store.create(preset="coding", model="m")
        msgs = store.load_messages(meta.id)
        assert msgs == []

    def test_load_nonexistent_session(self, store):
        msgs = store.load_messages("nonexistent")
        assert msgs == []

    def test_increments_message_count(self, store):
        meta = store.create(preset="coding", model="m")
        store.save_message(meta.id, {"role": "user", "content": "hello"})
        updated = store.get_session(meta.id)
        assert updated.message_count == 1


class TestSessionUsage:
    """Test usage persistence."""

    def test_save_usage(self, store):
        meta = store.create(preset="coding", model="m")
        store.save_usage(meta.id, 10000, 5000, 0.45)
        usage_path = store._dir / meta.id / "usage.json"
        data = json.loads(usage_path.read_text())
        assert data["input_tokens"] == 10000
        assert data["output_tokens"] == 5000
        assert data["cost"] == 0.45


class TestSessionListing:
    """Test session listing and retrieval."""

    def test_list_empty(self, store):
        assert store.list_sessions() == []

    def test_list_returns_newest_first(self, store):
        m1 = store.create(preset="coding", model="m1")
        m2 = store.create(preset="coding", model="m2")
        sessions = store.list_sessions()
        # m2 was created after m1
        assert sessions[0].id == m2.id

    def test_list_respects_limit(self, store):
        for i in range(5):
            store.create(preset="coding", model=f"m{i}")
        sessions = store.list_sessions(limit=3)
        assert len(sessions) == 3

    def test_get_latest(self, store):
        store.create(preset="coding", model="m1")
        m2 = store.create(preset="coding", model="m2")
        latest = store.get_latest()
        assert latest.id == m2.id

    def test_get_latest_empty(self, store):
        assert store.get_latest() is None

    def test_get_session(self, store):
        meta = store.create(preset="coding", model="m")
        retrieved = store.get_session(meta.id)
        assert retrieved.id == meta.id
        assert retrieved.model == "m"

    def test_get_nonexistent_session(self, store):
        assert store.get_session("nonexistent") is None


class TestSessionTitle:
    """Test title update."""

    def test_update_title(self, store):
        meta = store.create(preset="coding", model="m")
        store.update_title(meta.id, "My conversation about Python")
        updated = store.get_session(meta.id)
        assert updated.title == "My conversation about Python"

    def test_title_truncated_to_60(self, store):
        meta = store.create(preset="coding", model="m")
        long_title = "x" * 100
        store.update_title(meta.id, long_title)
        updated = store.get_session(meta.id)
        assert len(updated.title) == 60
