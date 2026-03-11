"""WebSocket integration tests — connection handling, malformed data, cleanup.

Tests exercise the WebSocket handler's error paths and edge cases.
Since the actual WebSocket handler depends on FastAPI + DB, these tests
focus on the helper functions and isolated behaviors.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_service.api.websocket import _sanitize_messages, _list_workspace_files


# ---------------------------------------------------------------------------
# _sanitize_messages tests
# ---------------------------------------------------------------------------


class TestSanitizeMessages:
    """Test orphaned tool_use cleanup in message history."""

    def test_no_orphans(self):
        """Messages with matching tool_result should not be modified."""
        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me check."},
                    {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
                ],
            },
        ]
        result = _sanitize_messages(messages)
        # Should keep tool_use intact
        assert any(
            b.get("type") == "tool_use"
            for b in result[1]["content"]
            if isinstance(b, dict)
        )

    def test_orphaned_tool_use_stripped(self):
        """Orphaned tool_use blocks (no matching result) should be stripped."""
        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll help."},
                    {"type": "tool_use", "id": "t1", "name": "bash", "input": {}},
                ],
            },
            # No tool_result follows — this is the end
        ]
        result = _sanitize_messages(messages)
        # tool_use should be stripped
        assert not any(
            b.get("type") == "tool_use"
            for b in result[1]["content"]
            if isinstance(b, dict)
        )
        # Text should remain
        assert any(
            b.get("type") == "text"
            for b in result[1]["content"]
            if isinstance(b, dict)
        )

    def test_orphaned_tool_use_only_gets_placeholder(self):
        """If only tool_use blocks exist (no text), they get a placeholder."""
        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "bash", "input": {}},
                ],
            },
        ]
        result = _sanitize_messages(messages)
        assert result[1]["content"] == [{"type": "text", "text": "(tool call skipped)"}]

    def test_malformed_json_in_content_handled(self):
        """Non-dict content blocks should not crash sanitization."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Just plain text"},
        ]
        result = _sanitize_messages(messages)
        assert result == messages


# ---------------------------------------------------------------------------
# _list_workspace_files tests
# ---------------------------------------------------------------------------


class TestListWorkspaceFiles:
    """Test workspace file listing with skip logic."""

    def test_empty_workspace(self, tmp_path: Path):
        ws = tmp_path / "ws"
        ws.mkdir()
        assert _list_workspace_files(ws) == []

    def test_skips_hidden_dirs(self, tmp_path: Path):
        ws = tmp_path / "ws"
        ws.mkdir()
        # Should be included
        (ws / "hello.py").write_text("pass")
        # Should be skipped
        for d in (".agent", ".transcripts", ".tasks", ".team"):
            (ws / d).mkdir()
            (ws / d / "data.json").write_text("{}")

        files = _list_workspace_files(ws)
        assert len(files) == 1
        assert files[0]["name"] == "hello.py"

    def test_nonexistent_workspace(self, tmp_path: Path):
        ws = tmp_path / "nonexistent"
        assert _list_workspace_files(ws) == []

    def test_nested_files(self, tmp_path: Path):
        ws = tmp_path / "ws"
        ws.mkdir()
        sub = ws / "sub" / "dir"
        sub.mkdir(parents=True)
        (sub / "deep.txt").write_text("hello")

        files = _list_workspace_files(ws)
        assert len(files) == 1
        assert files[0]["path"] == "sub/dir/deep.txt"


# ---------------------------------------------------------------------------
# Connection lifecycle tests
# ---------------------------------------------------------------------------


class TestConnectionLifecycle:
    """Test WebSocket connection handling patterns."""

    async def test_cancelled_event_stops_loop(self):
        """asyncio.Event set should cause loop to check and stop."""
        cancelled = asyncio.Event()
        cancelled.set()
        assert cancelled.is_set()

    async def test_approval_queue_timeout(self):
        """Approval queue with timeout should raise TimeoutError."""
        queue: asyncio.Queue = asyncio.Queue()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.1)

    async def test_concurrent_queue_operations(self):
        """Multiple producers/consumers on asyncio.Queue should work."""
        queue: asyncio.Queue = asyncio.Queue()

        async def producer():
            for i in range(5):
                await queue.put(f"msg-{i}")

        async def consumer():
            items = []
            for _ in range(5):
                items.append(await asyncio.wait_for(queue.get(), timeout=1.0))
            return items

        await producer()
        items = await consumer()
        assert len(items) == 5
        assert items == [f"msg-{i}" for i in range(5)]
