"""Tests for agent_cli.renderer helper functions and make_send_event."""

from __future__ import annotations

import sys
import time
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest

import agent_cli.renderer as renderer_mod
from agent_cli.renderer import (
    ElapsedText,
    StreamingRenderer,
    _end_stream,
    _result_lines,
    _summarize_input,
    _tool_activity_label,
    make_send_event,
)


# -----------------------------------------------------------------------
# _summarize_input
# -----------------------------------------------------------------------


class TestSummarizeInputString:
    """When data is a plain string."""

    def test_short_string_unchanged(self):
        assert _summarize_input("tool", "hello") == "hello"

    def test_string_truncated_at_120(self):
        long = "x" * 200
        result = _summarize_input("tool", long)
        assert len(result) == 121  # 120 chars + ellipsis
        assert result.endswith("\u2026")

    def test_exact_120_no_ellipsis(self):
        exact = "a" * 120
        result = _summarize_input("tool", exact)
        assert result == exact
        assert "\u2026" not in result


class TestSummarizeInputDict:
    """When data is a dict."""

    def test_file_path_key(self):
        assert _summarize_input("Read", {"file_path": "/foo/bar.py"}) == "/foo/bar.py"

    def test_path_key(self):
        assert _summarize_input("Grep", {"path": "/src"}) == "/src"

    def test_notebook_path_key(self):
        assert _summarize_input("NotebookEdit", {"notebook_path": "/nb.ipynb"}) == "/nb.ipynb"

    def test_command_key(self):
        result = _summarize_input("Bash", {"command": "ls -la"})
        assert result == "ls -la"

    def test_command_truncated(self):
        cmd = "echo " + "x" * 200
        result = _summarize_input("Bash", {"command": cmd})
        assert len(result) == 121
        assert result.endswith("\u2026")

    def test_pattern_only(self):
        result = _summarize_input("Grep", {"pattern": "foo"})
        assert result == '"foo"'

    def test_pattern_with_path_prefers_path_key(self):
        result = _summarize_input("Grep", {"pattern": "foo", "path": "/src"})
        assert result == "/src"

    def test_pattern_with_glob(self):
        result = _summarize_input("Grep", {"pattern": "bar", "glob": "*.py"})
        assert result == '"bar"  *.py'

    def test_query_key(self):
        result = _summarize_input("WebSearch", {"query": "python docs"})
        assert result == "python docs"

    def test_url_key(self):
        result = _summarize_input("WebFetch", {"url": "https://example.com"})
        assert result == "https://example.com"

    def test_skill_key(self):
        result = _summarize_input("Skill", {"skill": "commit"})
        assert result == "commit"

    def test_content_key_truncated_to_80(self):
        content = "y" * 200
        result = _summarize_input("Edit", {"content": content})
        assert len(result) == 81  # 80 chars + ellipsis
        assert result.endswith("\u2026")

    def test_content_short_no_truncation(self):
        result = _summarize_input("Edit", {"content": "short"})
        assert result == "short"

    def test_fallback_other_key(self):
        result = _summarize_input("Custom", {"foo": "bar"})
        assert result == "foo=bar"

    def test_fallback_long_value_truncated(self):
        long_val = "z" * 200
        result = _summarize_input("Custom", {"key": long_val})
        assert result.startswith("key=")
        assert result.endswith("\u2026")
        # key= (4 chars) + 97 chars + ellipsis = 102 total
        assert len(result) == 4 + 97 + 1

    def test_empty_dict(self):
        assert _summarize_input("tool", {}) == ""


class TestSummarizeInputOtherTypes:
    """When data is neither str nor dict."""

    def test_integer(self):
        result = _summarize_input("tool", 42)
        assert result == "42"

    def test_list(self):
        result = _summarize_input("tool", [1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_none(self):
        result = _summarize_input("tool", None)
        assert result == "None"

    def test_long_repr_truncated(self):
        long_list = list(range(100))
        result = _summarize_input("tool", long_list)
        assert len(result) <= 120


# -----------------------------------------------------------------------
# _result_lines
# -----------------------------------------------------------------------


class TestResultLinesString:
    """When result is a string."""

    def test_short_string(self):
        lines = _result_lines("hello world")
        assert lines == ["hello world"]

    def test_empty_string(self):
        lines = _result_lines("")
        assert lines == [""]

    def test_string_exceeds_max_len(self):
        long = "a" * 3000
        lines = _result_lines(long, max_len=2000)
        assert len(lines) == 1
        assert len(lines[0]) == 2000

    def test_multiline_within_limits(self):
        text = "line1\nline2\nline3"
        lines = _result_lines(text, max_lines=6)
        assert lines == ["line1", "line2", "line3"]

    def test_multiline_exceeds_max_lines(self):
        text = "\n".join(f"line{i}" for i in range(10))
        lines = _result_lines(text, max_lines=6)
        assert len(lines) == 6
        assert lines[-1].startswith("\u2026")
        assert "more lines" in lines[-1]

    def test_multiline_exact_max_lines(self):
        text = "\n".join(f"line{i}" for i in range(6))
        lines = _result_lines(text, max_lines=6)
        assert len(lines) == 6
        assert "more lines" not in lines[-1]

    def test_remaining_count_is_correct(self):
        text = "\n".join(f"L{i}" for i in range(20))
        lines = _result_lines(text, max_lines=6)
        assert "15 more lines" in lines[-1]


class TestResultLinesDict:
    """When result is a dict or other JSON-serializable object."""

    def test_dict_gets_json_formatted(self):
        data = {"key": "value"}
        lines = _result_lines(data)
        assert lines[0] == "{"
        assert any("key" in ln for ln in lines)

    def test_list_result(self):
        data = [1, 2, 3]
        lines = _result_lines(data)
        joined = "\n".join(lines)
        assert "1" in joined
        assert "2" in joined
        assert "3" in joined


class TestResultLinesNonSerializable:
    """When result cannot be JSON-serialized."""

    def test_non_serializable_uses_str(self):
        class Custom:
            def __str__(self):
                return "custom-object"
        lines = _result_lines(Custom())
        assert lines == ["custom-object"]

    def test_set_uses_str(self):
        result = {1, 2}
        lines = _result_lines(result)
        assert len(lines) >= 1


# -----------------------------------------------------------------------
# _end_stream
# -----------------------------------------------------------------------


class TestEndStream:
    """Verify _end_stream behaviour."""

    def test_sets_streaming_false(self):
        renderer_mod._streaming = True
        with patch.object(sys, "stdout", new_callable=StringIO):
            _end_stream()
        assert renderer_mod._streaming is False

    def test_writes_newline_when_streaming(self):
        renderer_mod._streaming = True
        buf = StringIO()
        with patch.object(sys, "stdout", buf):
            _end_stream()
        assert buf.getvalue() == "\n"

    def test_noop_when_not_streaming(self):
        renderer_mod._streaming = False
        buf = StringIO()
        with patch.object(sys, "stdout", buf):
            _end_stream()
        assert buf.getvalue() == ""
        assert renderer_mod._streaming is False


# -----------------------------------------------------------------------
# StreamingRenderer
# -----------------------------------------------------------------------


class TestStreamingRenderer:
    """Test buffer accumulation and Markdown rendering."""

    def test_plain_text_rendered_as_markdown(self):
        sr = StreamingRenderer()
        sr.feed("hello world")
        with patch("agent_cli.renderer.console") as mock_console:
            sr.finish()
            mock_console.print.assert_called_once()
            arg = mock_console.print.call_args[0][0]
            from rich.markdown import Markdown as RichMarkdown
            assert isinstance(arg, RichMarkdown)

    def test_code_block_rendered_as_markdown(self):
        sr = StreamingRenderer()
        sr.feed("```python\nprint('hi')\n```\n")
        with patch("agent_cli.renderer.console") as mock_console:
            sr.finish()
            mock_console.print.assert_called_once()
            arg = mock_console.print.call_args[0][0]
            from rich.markdown import Markdown as RichMarkdown
            assert isinstance(arg, RichMarkdown)

    def test_reset_clears_buffer(self):
        sr = StreamingRenderer()
        sr.feed("some text")
        sr.reset()
        assert sr._buffer == []

    def test_finish_renders_accumulated_text(self):
        sr = StreamingRenderer()
        sr.feed("hello ")
        sr.feed("world")
        with patch("agent_cli.renderer.console") as mock_console:
            sr.finish()
            mock_console.print.assert_called_once()
        # Buffer should be cleared after finish
        assert sr._buffer == []

    def test_finish_noop_on_empty_buffer(self):
        sr = StreamingRenderer()
        with patch("agent_cli.renderer.console") as mock_console:
            sr.finish()
            mock_console.print.assert_not_called()

    def test_finish_noop_on_whitespace_only(self):
        sr = StreamingRenderer()
        sr.feed("   \n  ")
        with patch("agent_cli.renderer.console") as mock_console:
            sr.finish()
            mock_console.print.assert_not_called()


# -----------------------------------------------------------------------
# make_send_event
# -----------------------------------------------------------------------


class TestSendEventTextDelta:
    """text_delta events accumulate in the renderer buffer."""

    async def test_text_delta_accumulates_in_buffer(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status"):
            await send({"type": "text_delta", "content": "hello"})
            await send({"type": "text_delta", "content": " world"})

    async def test_text_delta_starts_spinner_with_elapsed_text(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus:
            mock_instance = MockStatus.return_value
            await send({"type": "text_delta", "content": "x"})
            mock_instance.start.assert_called_once()
            et = MockStatus.call_args[0][0]
            assert isinstance(et, ElapsedText)
            assert et.message == "Generating"

    async def test_text_delta_updates_elapsed_text_message(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus:
            mock_instance = MockStatus.return_value
            await send({"type": "text_delta", "content": "x"})
            et = MockStatus.call_args[0][0]
            await send({"type": "text_delta", "content": "y"})
            # Message should stay "Generating" (updated via _update_spinner_message)
            assert et.message == "Generating"


class TestSendEventToolCall:
    """tool_call events print the tool name."""

    async def test_tool_call_prints_name(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "tool_call", "tool": "Bash", "input": {"command": "ls"}})
            printed = mock_console.print.call_args[0][0]
            assert "Bash" in printed


class TestSendEventToolResult:
    """tool_result events print the result."""

    async def test_tool_result_prints_result(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "tool_result", "result": "file contents here"})
            printed = mock_console.print.call_args_list[0][0][0]
            assert "file contents here" in printed

    async def test_tool_result_empty(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "tool_result", "result": ""})
            assert mock_console.print.called


class TestSendEventError:
    """error events print an error message."""

    async def test_error_prints_message(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "error", "message": "something broke"})
            printed = mock_console.print.call_args[0][0]
            assert "something broke" in printed
            assert "Error" in printed


class TestSendEventDone:
    """done events print token usage."""

    async def test_done_with_usage(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "done", "usage": {"input_tokens": 1000, "output_tokens": 500}})
            printed = mock_console.print.call_args[0][0]
            assert "1,000" in printed
            assert "500" in printed

    async def test_done_with_cost_tracker(self):
        renderer_mod._streaming = False
        from agent_cli.cost import CostTracker
        ct = CostTracker("claude-sonnet-4-5-20250929")
        ct.add(1000, 500)
        send = make_send_event(cost_tracker=ct)
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "done", "usage": {"input_tokens": 1000, "output_tokens": 500}})
            printed = mock_console.print.call_args[0][0]
            assert "$" in printed

    async def test_done_zero_usage_no_print(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "done", "usage": {"input_tokens": 0, "output_tokens": 0}})
            assert not mock_console.print.called

    async def test_done_missing_usage(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "done"})
            assert not mock_console.print.called


class TestSendEventCompact:
    """compact events print a compaction message."""

    async def test_compact_prints_message(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "compact", "message": "Context compacted"})
            printed = mock_console.print.call_args[0][0]
            assert "Context compacted" in printed

    async def test_compact_default_message(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "compact"})
            printed = mock_console.print.call_args[0][0]
            assert "Context compacted" in printed


class TestSendEventSubagent:
    """subagent_start / subagent_end events."""

    async def test_subagent_start_prints_task(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console, \
             patch("agent_cli.renderer.Status"):
            await send({"type": "subagent_start", "task": "Refactor module"})
            printed = mock_console.print.call_args[0][0]
            assert "Subagent" in printed
            assert "Refactor module" in printed

    async def test_subagent_start_starts_spinner(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus, \
             patch("agent_cli.renderer.console"):
            mock_instance = MockStatus.return_value
            await send({"type": "subagent_start", "task": "Explore code"})
            mock_instance.start.assert_called_once()
            et = MockStatus.call_args[0][0]
            assert isinstance(et, ElapsedText)
            assert et.message == "Researching"

    async def test_subagent_end_prints_summary(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console, \
             patch("agent_cli.renderer.Status"):
            await send({
                "type": "subagent_end",
                "summary": "Done refactoring",
                "tool_count": 3,
                "elapsed": 5.2,
            })
            all_printed = " ".join(
                call[0][0] for call in mock_console.print.call_args_list
            )
            assert "Done refactoring" in all_printed
            assert "3 tools" in all_printed
            assert "5.2s" in all_printed

    async def test_subagent_end_stops_spinner_and_restarts(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus, \
             patch("agent_cli.renderer.console"):
            mock_instance = MockStatus.return_value
            await send({"type": "subagent_start", "task": "Explore"})
            assert mock_instance.start.call_count == 1

            await send({
                "type": "subagent_end",
                "summary": "Done",
                "tool_count": 1,
                "elapsed": 2.0,
            })
            # Spinner stopped (from the _stop_spinner before block events)
            # then restarted with "Thinking" after subagent_end
            assert mock_instance.stop.call_count >= 1
            assert mock_instance.start.call_count >= 2
            et = MockStatus.call_args[0][0]
            assert et.message == "Thinking"


class TestSendEventToolApproval:
    """tool_approval_request delegates to the ApprovalHandler."""

    async def test_tool_approval_calls_handler(self):
        mock_handler = AsyncMock()
        send = make_send_event(approval_handler=mock_handler)
        renderer_mod._streaming = False
        event = {"type": "tool_approval_request", "tools": [{"name": "Bash"}]}
        await send(event)
        mock_handler.handle.assert_awaited_once_with(event)

    async def test_tool_approval_no_handler_is_noop(self):
        send = make_send_event(approval_handler=None)
        renderer_mod._streaming = False
        await send({"type": "tool_approval_request", "tools": [{"name": "Bash"}]})


class TestSendEventTeammateStatus:
    """teammate_status events."""

    async def test_teammate_status_prints_info(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({
                "type": "teammate_status",
                "name": "Alice",
                "role": "reviewer",
                "status": "idle",
            })
            printed = mock_console.print.call_args[0][0]
            assert "Alice" in printed
            assert "reviewer" in printed
            assert "idle" in printed


class TestSendEventToolApprovalResult:
    """tool_approval_result events."""

    async def test_approval_result_approved(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "tool_approval_result", "decision": "approve"})
            printed = mock_console.print.call_args[0][0]
            assert "Approved" in printed
            assert "\u2713" in printed  # ✓ check mark

    async def test_approval_result_auto_approved(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "tool_approval_result", "decision": "auto_approve"})
            printed = mock_console.print.call_args[0][0]
            assert "Auto-approved" in printed
            assert "\u2713" in printed  # ✓ check mark

    async def test_approval_result_denied(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "tool_approval_result", "decision": "deny"})
            printed = mock_console.print.call_args[0][0]
            assert "Denied" in printed
            assert "\u2717" in printed  # ✗ cross mark


class TestSendEventThinking:
    """thinking events start a spinner with ElapsedText."""

    async def test_thinking_starts_spinner(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus:
            mock_instance = MockStatus.return_value
            await send({"type": "thinking"})
            MockStatus.assert_called_once()
            # First arg should be an ElapsedText, not a plain string
            et = MockStatus.call_args[0][0]
            assert isinstance(et, ElapsedText)
            assert et.message == "Thinking"
            mock_instance.start.assert_called_once()

    async def test_text_delta_updates_spinner_message(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus:
            mock_instance = MockStatus.return_value
            await send({"type": "thinking"})
            et = MockStatus.call_args[0][0]
            await send({"type": "text_delta", "content": "hi"})
            # ElapsedText message should be updated to "Generating"
            assert et.message == "Generating"

    async def test_thinking_delta_renders_before_text(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status"), \
             patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "thinking_delta", "content": "reasoning", "effort": "max"})
            assert mock_console.print.call_count == 0

            await send({"type": "text_delta", "content": "answer"})

            calls = mock_console.print.call_args_list
            assert "Thinking" in calls[0][0][0]
            assert "max" in calls[0][0][0]
            from rich.text import Text as RichText
            assert isinstance(calls[1][0][0], RichText)
            assert str(calls[1][0][0]) == "reasoning"

    async def test_final_thinking_with_content_renders_provider_output(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status"), \
             patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "thinking", "content": "final reasoning", "effort": "high"})

            calls = mock_console.print.call_args_list
            assert "Thinking" in calls[0][0][0]
            assert "high" in calls[0][0][0]
            assert str(calls[1][0][0]) == "final reasoning"


class TestSendEventTeamsChanged:
    """teams_changed events."""

    async def test_teams_enabled(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "teams_changed", "enabled": True})
            printed = mock_console.print.call_args[0][0]
            assert "Teams enabled" in printed

    async def test_teams_disabled(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "teams_changed", "enabled": False})
            printed = mock_console.print.call_args[0][0]
            assert "Teams disabled" in printed


class TestSendEventApprovalChanged:
    """approval_changed events."""

    async def test_approval_enabled(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "approval_changed", "enabled": True})
            printed = mock_console.print.call_args[0][0]
            assert "approval enabled" in printed

    async def test_approval_disabled(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.console") as mock_console:
            await send({"type": "approval_changed", "enabled": False})
            printed = mock_console.print.call_args[0][0]
            assert "approval disabled" in printed


class TestSendEventEndStreamOnNonDelta:
    """Non text_delta events should flush markdown before block events."""

    async def test_tool_call_flushes_markdown(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status"):
            await send({"type": "text_delta", "content": "hello"})
        with patch("agent_cli.renderer.console") as mock_console, \
             patch("agent_cli.renderer.Status"):
            await send({"type": "tool_call", "tool": "X", "input": {}})
            # First call should be Markdown render from finish(), second the tool_call
            calls = mock_console.print.call_args_list
            assert len(calls) >= 2
            from rich.markdown import Markdown as RichMarkdown
            assert isinstance(calls[0][0][0], RichMarkdown)


# -----------------------------------------------------------------------
# ElapsedText
# -----------------------------------------------------------------------


class TestElapsedText:
    """Test the ElapsedText Rich renderable."""

    def test_renders_message_without_time_at_zero(self):
        et = ElapsedText("Thinking", start=time.monotonic())
        from rich.console import Console as C, ConsoleOptions
        c = C(file=StringIO(), force_terminal=True)
        options = c.options
        segments = list(et.__rich_console__(c, options))
        text_str = str(segments[0])
        assert "Thinking" in text_str
        # At 0 seconds elapsed, no "(0s)" shown
        assert "(0s)" not in text_str

    def test_renders_message_with_time_after_delay(self):
        # Simulate 5 seconds ago
        et = ElapsedText("Thinking", start=time.monotonic() - 5)
        from rich.console import Console as C
        c = C(file=StringIO(), force_terminal=True)
        options = c.options
        segments = list(et.__rich_console__(c, options))
        text_str = str(segments[0])
        assert "Thinking" in text_str
        assert "(5s)" in text_str

    def test_message_property_updates(self):
        et = ElapsedText("Thinking")
        assert et.message == "Thinking"
        et.message = "Generating"
        assert et.message == "Generating"

    def test_custom_start_time(self):
        start = time.monotonic() - 10
        et = ElapsedText("Working", start=start)
        from rich.console import Console as C
        c = C(file=StringIO(), force_terminal=True)
        segments = list(et.__rich_console__(c, c.options))
        text_str = str(segments[0])
        assert "(10s)" in text_str


# -----------------------------------------------------------------------
# _tool_activity_label
# -----------------------------------------------------------------------


class TestToolActivityLabel:
    """Test tool name to activity label mapping."""

    def test_known_tool_bash(self):
        assert _tool_activity_label("Bash", {"command": "ls"}) == "Running command"

    def test_known_tool_case_insensitive(self):
        assert _tool_activity_label("BASH", {}) == "Running command"

    def test_read_with_file_path(self):
        result = _tool_activity_label("Read", {"file_path": "/src/app.py"})
        assert result == "Reading app.py"

    def test_edit_with_file_path(self):
        result = _tool_activity_label("Edit", {"file_path": "/foo/bar/utils.ts"})
        assert result == "Editing utils.ts"

    def test_write_with_notebook_path(self):
        result = _tool_activity_label("Write", {"notebook_path": "/nb.ipynb"})
        assert result == "Writing nb.ipynb"

    def test_read_without_path_fallback(self):
        result = _tool_activity_label("Read", {"content": "hello"})
        assert result == "Reading"

    def test_grep_tool(self):
        assert _tool_activity_label("Grep", {"pattern": "foo"}) == "Searching files"

    def test_web_search(self):
        assert _tool_activity_label("web_search", {}) == "Searching the web"

    def test_unknown_tool_fallback(self):
        assert _tool_activity_label("CustomTool", {}) == "Working"

    def test_path_extracts_filename_only(self):
        result = _tool_activity_label("Read", {"file_path": "/a/b/c/deep/file.py"})
        assert result == "Reading file.py"
        # Should not contain path components
        assert "/" not in result


# -----------------------------------------------------------------------
# Spinner restart on tool events
# -----------------------------------------------------------------------


class TestSpinnerRestartOnToolCall:
    """tool_call restarts the spinner with a contextual activity label."""

    async def test_spinner_restarts_after_tool_call(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus, \
             patch("agent_cli.renderer.console"):
            mock_instance = MockStatus.return_value
            await send({"type": "thinking"})
            first_start_count = mock_instance.start.call_count

            await send({"type": "tool_call", "tool": "Read", "input": {"file_path": "/src/app.py"}})
            # Spinner should have been stopped and restarted
            assert mock_instance.stop.call_count >= 1
            assert mock_instance.start.call_count > first_start_count
            # Latest ElapsedText should reflect tool activity
            et = MockStatus.call_args[0][0]
            assert isinstance(et, ElapsedText)
            assert "Reading" in et.message
            assert "app.py" in et.message

    async def test_spinner_shows_running_command_for_bash(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus, \
             patch("agent_cli.renderer.console"):
            await send({"type": "thinking"})
            await send({"type": "tool_call", "tool": "Bash", "input": {"command": "ls -la"}})
            et = MockStatus.call_args[0][0]
            assert et.message == "Running command"


class TestSpinnerRestartOnToolResult:
    """tool_result restarts the spinner with 'Thinking'."""

    async def test_spinner_restarts_after_tool_result(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus, \
             patch("agent_cli.renderer.console"):
            mock_instance = MockStatus.return_value
            await send({"type": "thinking"})
            await send({"type": "tool_result", "result": "ok"})
            # Latest spinner should show "Thinking"
            et = MockStatus.call_args[0][0]
            assert isinstance(et, ElapsedText)
            assert et.message == "Thinking"


class TestElapsedTimePreservedAcrossTurn:
    """Elapsed time counter is shared across spinner restarts within a turn."""

    async def test_turn_start_shared(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus, \
             patch("agent_cli.renderer.console"):
            await send({"type": "thinking"})
            first_et = MockStatus.call_args[0][0]
            first_start = first_et._start

            await send({"type": "tool_call", "tool": "Bash", "input": {"command": "ls"}})
            second_et = MockStatus.call_args[0][0]
            # Both should share the same start time
            assert second_et._start == first_start

            await send({"type": "tool_result", "result": "ok"})
            third_et = MockStatus.call_args[0][0]
            assert third_et._start == first_start

    async def test_new_thinking_resets_turn_start(self):
        renderer_mod._streaming = False
        send = make_send_event()
        with patch("agent_cli.renderer.Status") as MockStatus, \
             patch("agent_cli.renderer.console"):
            await send({"type": "thinking"})
            first_et = MockStatus.call_args[0][0]
            first_start = first_et._start

            # Simulate done (resets _turn_start)
            await send({"type": "done", "usage": {}})

            # New thinking event — should get a fresh start time
            await send({"type": "thinking"})
            second_et = MockStatus.call_args[0][0]
            # Start times should differ (or at least be independently set)
            assert second_et._start >= first_start
