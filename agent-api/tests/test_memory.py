"""Tests for agent_service.agent.memory."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent_service.agent.memory import (
    MAX_MEMORY_BYTES,
    PRESERVED_DIRS,
    MemoryManager,
    _messages_to_compact_text,
    clean_workspace,
)


# ---------------------------------------------------------------------------
# MemoryManager tests
# ---------------------------------------------------------------------------


def test_read_empty(tmp_path: Path):
    mgr = MemoryManager(tmp_path)
    assert mgr.read() == ""


def test_write_and_read_roundtrip(tmp_path: Path):
    mgr = MemoryManager(tmp_path)
    mgr.write("## User Preferences\n- dark mode\n")
    assert "dark mode" in mgr.read()


def test_write_enforces_max_size(tmp_path: Path):
    mgr = MemoryManager(tmp_path)
    # Create content larger than MAX_MEMORY_BYTES
    big_content = "\n".join(f"line {i}: {'x' * 80}" for i in range(200))
    assert len(big_content.encode("utf-8")) > MAX_MEMORY_BYTES
    mgr.write(big_content)
    stored = mgr.read()
    assert len(stored.encode("utf-8")) <= MAX_MEMORY_BYTES
    # The truncation removes from the top, so later lines should survive
    assert "line 199" in stored


# ---------------------------------------------------------------------------
# _messages_to_compact_text tests
# ---------------------------------------------------------------------------


def test_compact_text_string_content():
    messages = [{"role": "user", "content": "Hello agent"}]
    text = _messages_to_compact_text(messages)
    assert "[user] Hello agent" in text


def test_compact_text_list_content_text():
    messages = [
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "I will help you"}],
        }
    ]
    text = _messages_to_compact_text(messages)
    assert "[assistant] I will help you" in text


def test_compact_text_tool_use():
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "read_file",
                    "input": {"path": "main.py"},
                }
            ],
        }
    ]
    text = _messages_to_compact_text(messages)
    assert "[tool_call] read_file" in text
    assert "main.py" in text


def test_compact_text_tool_result():
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": "file contents here",
                }
            ],
        }
    ]
    text = _messages_to_compact_text(messages)
    assert "[tool_result] file contents here" in text


# ---------------------------------------------------------------------------
# clean_workspace tests
# ---------------------------------------------------------------------------


def test_clean_workspace_removes_files_preserves_dirs(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    # Create regular files
    (ws / "output.txt").write_text("result")
    (ws / "data.json").write_text("{}")
    subdir = ws / "subdir"
    subdir.mkdir()
    (subdir / "inner.py").write_text("x = 1")

    # Create preserved dirs
    for d in PRESERVED_DIRS:
        preserved = ws / d
        preserved.mkdir()
        (preserved / "keep.txt").write_text("important")

    clean_workspace(ws)

    # Regular files/dirs should be gone
    assert not (ws / "output.txt").exists()
    assert not (ws / "data.json").exists()
    assert not (ws / "subdir").exists()

    # Preserved dirs should remain
    for d in PRESERVED_DIRS:
        assert (ws / d).exists()
        assert (ws / d / "keep.txt").exists()


def test_clean_workspace_nonexistent(tmp_path: Path):
    """Should not raise if workspace does not exist."""
    clean_workspace(tmp_path / "nonexistent")
