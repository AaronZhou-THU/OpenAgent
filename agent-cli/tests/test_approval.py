"""Tests for agent_cli.approval.ApprovalHandler."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent_cli.approval import ApprovalHandler


@pytest.fixture
def queue() -> asyncio.Queue:
    return asyncio.Queue()


@pytest.fixture
def handler(queue: asyncio.Queue) -> ApprovalHandler:
    return ApprovalHandler(queue)


class TestApprovalDecisions:
    """Verify that handle() puts the correct decision into the queue."""

    async def test_approve_on_y(self, handler: ApprovalHandler, queue: asyncio.Queue):
        event = {"type": "tool_approval_request", "tools": [{"name": "Bash"}]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="y"):
            await handler.handle(event)
        decision = queue.get_nowait()
        assert decision == "approve"

    async def test_deny_on_n(self, handler: ApprovalHandler, queue: asyncio.Queue):
        event = {"type": "tool_approval_request", "tools": [{"name": "Write"}]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="n"):
            await handler.handle(event)
        decision = queue.get_nowait()
        assert decision == "deny"

    async def test_auto_approve_on_a(self, handler: ApprovalHandler, queue: asyncio.Queue):
        event = {"type": "tool_approval_request", "tools": [{"name": "Read"}]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="a"):
            await handler.handle(event)
        decision = queue.get_nowait()
        assert decision == "auto_approve"

    async def test_unknown_answer_defaults_to_deny(self, handler: ApprovalHandler, queue: asyncio.Queue):
        """Any answer other than 'y' or 'a' should result in 'deny'."""
        event = {"type": "tool_approval_request", "tools": [{"name": "Bash"}]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="x"):
            await handler.handle(event)
        decision = queue.get_nowait()
        assert decision == "deny"


class TestToolNameExtraction:
    """Verify that tool names and details are extracted correctly."""

    async def test_single_dict_tool(self, handler: ApprovalHandler, queue: asyncio.Queue):
        event = {"type": "tool_approval_request", "tools": [{"name": "Bash"}]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="y"):
            with patch("agent_cli.approval.console") as mock_console:
                await handler.handle(event)
                # First console.print call is the header line with tool name
                header = mock_console.print.call_args_list[0][0][0]
                assert "Bash" in header

    async def test_multiple_tools_shows_first(self, handler: ApprovalHandler, queue: asyncio.Queue):
        """With multiple tools, shows the first tool name in the header."""
        event = {"type": "tool_approval_request", "tools": [
            {"name": "Read", "input": {"file_path": "/foo.py"}},
            {"name": "Write"},
        ]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="y"):
            with patch("agent_cli.approval.console") as mock_console:
                await handler.handle(event)
                header = mock_console.print.call_args_list[0][0][0]
                assert "Read" in header

    async def test_tool_without_name_key(self, handler: ApprovalHandler, queue: asyncio.Queue):
        """Dicts missing 'name' should show '?'."""
        event = {"type": "tool_approval_request", "tools": [{"id": "123"}]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="y"):
            with patch("agent_cli.approval.console") as mock_console:
                await handler.handle(event)
                header = mock_console.print.call_args_list[0][0][0]
                assert "?" in header

    async def test_string_tool_entries(self, handler: ApprovalHandler, queue: asyncio.Queue):
        """Non-dict tool entries get stringified."""
        event = {"type": "tool_approval_request", "tools": ["some_tool"]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="y"):
            with patch("agent_cli.approval.console") as mock_console:
                await handler.handle(event)
                header = mock_console.print.call_args_list[0][0][0]
                assert "some_tool" in header

    async def test_empty_tools_list(self, handler: ApprovalHandler, queue: asyncio.Queue):
        """Empty tools list should still work without error."""
        event = {"type": "tool_approval_request", "tools": []}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="n"):
            await handler.handle(event)
        decision = queue.get_nowait()
        assert decision == "deny"

    async def test_missing_tools_key(self, handler: ApprovalHandler, queue: asyncio.Queue):
        """Missing 'tools' key defaults to empty list."""
        event = {"type": "tool_approval_request"}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="y"):
            await handler.handle(event)
        decision = queue.get_nowait()
        assert decision == "approve"

    async def test_detail_line_shown_for_file_path(self, handler: ApprovalHandler, queue: asyncio.Queue):
        """When tool has file_path input, a detail line is printed."""
        event = {"type": "tool_approval_request", "tools": [
            {"name": "Read", "input": {"file_path": "/src/app.py"}}
        ]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="y"):
            with patch("agent_cli.approval.console") as mock_console:
                await handler.handle(event)
                # Should have 2 console.print calls: header + detail
                assert mock_console.print.call_count >= 2
                detail = mock_console.print.call_args_list[1][0][0]
                assert "/src/app.py" in detail

    async def test_detail_line_shown_for_command(self, handler: ApprovalHandler, queue: asyncio.Queue):
        """When tool has command input, a detail line is printed."""
        event = {"type": "tool_approval_request", "tools": [
            {"name": "Bash", "input": {"command": "ls -la"}}
        ]}
        with patch("agent_cli.approval.asyncio.to_thread", new_callable=AsyncMock, return_value="y"):
            with patch("agent_cli.approval.console") as mock_console:
                await handler.handle(event)
                assert mock_console.print.call_count >= 2
                detail = mock_console.print.call_args_list[1][0][0]
                assert "ls -la" in detail
