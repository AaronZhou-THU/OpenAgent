"""Integration tests — run agent_loop with real tools and a scripted LLM.

These tests wire together the actual loop, registry, tools, and filesystem.
Only the LLM is faked (ScriptedLLMClient returns pre-programmed responses).
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import patch

import pytest

from agent_service.agent.llm import LLMResponse, ToolCall
from agent_service.agent.loop import (
    COMPACT_KEEP_RECENT,
    MAX_CONTINUATIONS,
    PLAN_MODE_TOOLS,
    WRAPUP_HINT,
    agent_loop,
    build_registry,
    build_system_prompt,
    run_subagent,
    _compact_messages,
    _extract_plan_text,
)
from agent_service.agent.tools.plan_mode_tool import (
    ENTER_PLAN_SENTINEL,
    EXIT_PLAN_SENTINEL,
)
from agent_service.agent.memory import MemoryManager
from agent_service.agent.skill_loader import SkillLoader
from agent_service.agent.todo_manager import TodoManager
from agent_service.agent.task_manager import TaskManager
from agent_service.agent.background_manager import BackgroundManager
from agent_service.config import Settings


# ---------------------------------------------------------------------------
# ScriptedLLMClient — returns a sequence of pre-programmed responses
# ---------------------------------------------------------------------------


class ScriptedLLMClient:
    """Fake LLM that returns responses from a script (list).

    Supports both create() and stream(). Each call pops the next response
    from the script. If the script runs out, returns a fallback "done" response.
    """

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def _next(self, **kwargs) -> LLMResponse:
        # Snapshot messages so later mutations don't affect recorded calls
        if "messages" in kwargs:
            kwargs["messages"] = [dict(m) for m in kwargs["messages"]]
        self.calls.append(kwargs)
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(
            content=[{"type": "text", "text": "(scripted LLM exhausted)"}],
            tool_calls=[],
            done=True,
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )

    async def create(self, *, model, system, messages, tools,
                     max_tokens, temperature=1.0,
                     thinking_enabled=None, thinking_effort=None) -> LLMResponse:
        return self._next(model=model, system=system, messages=messages,
                          tools=tools, max_tokens=max_tokens,
                          temperature=temperature,
                          thinking_enabled=thinking_enabled,
                          thinking_effort=thinking_effort)

    @contextlib.asynccontextmanager
    async def stream(self, *, model, system, messages, tools,
                     max_tokens, temperature=1.0,
                     thinking_enabled=None, thinking_effort=None) -> AsyncIterator:
        resp = self._next(model=model, system=system, messages=messages,
                          tools=tools, max_tokens=max_tokens,
                          temperature=temperature,
                          thinking_enabled=thinking_enabled,
                          thinking_effort=thinking_effort)
        yield _FakeStream(resp)


class _FakeStream:
    """Minimal stream that yields thinking/text blocks then returns response."""

    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    def __aiter__(self):
        return self._iter_text()

    async def _iter_text(self):
        for block in self._response.content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                thinking = block.get("thinking") or block.get("text") or ""
                if thinking:
                    yield {"type": "thinking_delta", "content": thinking}
            if isinstance(block, dict) and block.get("type") == "text":
                yield block["text"]

    async def get_response(self) -> LLMResponse:
        return self._response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(workspace: Path, **overrides) -> Settings:
    """Create a Settings with workspace pointed at tmp_path."""
    defaults = dict(
        anthropic_api_key="test-key",
        workspace_dir=str(workspace),
        skills_dir=str(workspace / "_skills"),
        prompts_dir=str(workspace / "_prompts"),
        max_turns=50,
        max_token_budget=200_000,
        max_output_tokens=4096,
        context_window=200_000,
        compact_threshold=0.7,
        bash_timeout=10,
        enable_memory=False,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _make_skill_loader(workspace: Path) -> SkillLoader:
    skills_dir = workspace / "_skills"
    skills_dir.mkdir(exist_ok=True)
    return SkillLoader(skills_dir)


class EventCollector:
    """Collects send_event calls for assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def __call__(self, event: dict) -> None:
        self.events.append(event)

    def of_type(self, etype: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == etype]

    def types(self) -> list[str]:
        return [e.get("type", "") for e in self.events]


def _text_response(text: str, input_tokens=100, output_tokens=50) -> LLMResponse:
    """Create a simple text-only LLM response (done=True)."""
    return LLMResponse(
        content=[{"type": "text", "text": text}],
        tool_calls=[],
        done=True,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        stop_reason="end_turn",
    )


def _tool_response(
    tool_calls: list[tuple[str, str, dict]],
    text: str = "",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> LLMResponse:
    """Create an LLM response with tool_use blocks.

    tool_calls: list of (id, name, input) tuples.
    """
    content = []
    tcs = []
    if text:
        content.append({"type": "text", "text": text})
    for tc_id, name, inp in tool_calls:
        content.append({
            "type": "tool_use", "id": tc_id, "name": name, "input": inp,
        })
        tcs.append(ToolCall(id=tc_id, name=name, input=inp))
    return LLMResponse(
        content=content,
        tool_calls=tcs,
        done=False,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        stop_reason="tool_use",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSimpleQA:
    """LLM returns text only — loop exits after one turn."""

    async def test_text_only_response(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        llm = ScriptedLLMClient([_text_response("Hello! How can I help?")])
        events = EventCollector()

        messages = [{"role": "user", "content": "Hi"}]
        usage = await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=_make_skill_loader(ws),
            todo=TodoManager(),
            send_event=events,
        )

        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50
        # Should have streamed text
        text_deltas = events.of_type("text_delta")
        assert len(text_deltas) >= 1
        assert "Hello" in text_deltas[0]["content"]
        # Only one LLM call
        assert len(llm.calls) == 1

    async def test_thinking_delta_streams_before_text(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws, thinking_enabled=True, thinking_effort="max")
        llm = ScriptedLLMClient([
            LLMResponse(
                content=[
                    {"type": "thinking", "thinking": "I should answer directly."},
                    {"type": "text", "text": "Hello!"},
                ],
                tool_calls=[],
                done=True,
                input_tokens=100,
                output_tokens=50,
                stop_reason="end_turn",
            )
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Hi"}]
        await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=_make_skill_loader(ws),
            todo=TodoManager(),
            send_event=events,
        )

        thinking_events = events.of_type("thinking_delta")
        assert len(thinking_events) == 1
        assert thinking_events[0]["content"] == "I should answer directly."
        assert thinking_events[0]["effort"] == "max"
        assert events.types().index("thinking_delta") < events.types().index("text_delta")
        assert events.of_type("thinking") == []
        assert llm.calls[0]["thinking_enabled"] is True
        assert llm.calls[0]["thinking_effort"] == "max"
        assert messages[-1]["content"][0]["type"] == "thinking"


class TestToolUseFlow:
    """LLM calls write_file, then returns text — file should exist on disk."""

    async def test_write_file_creates_file(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        # Turn 1: LLM wants to write a file
        # Turn 2: LLM returns text after seeing tool result
        llm = ScriptedLLMClient([
            _tool_response([
                ("tc_1", "write_file", {"path": "hello.py", "content": "print('hello')"})
            ]),
            _text_response("I created hello.py for you."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Create hello.py"}]
        usage = await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=_make_skill_loader(ws),
            todo=TodoManager(),
            send_event=events,
        )

        # File should exist on disk
        assert (ws / "hello.py").exists()
        assert (ws / "hello.py").read_text() == "print('hello')"

        # Events should include tool_call, tool_result, text_delta
        types = events.types()
        assert "tool_call" in types
        assert "tool_result" in types
        assert "text_delta" in types

        # Two LLM calls
        assert len(llm.calls) == 2

        # Token usage accumulated from both calls
        assert usage["input_tokens"] == 200
        assert usage["output_tokens"] == 100

    async def test_read_file_returns_content(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "data.txt").write_text("line1\nline2\nline3")
        config = _make_settings(ws)

        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "read_file", {"path": "data.txt"})]),
            _text_response("The file has 3 lines."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Read data.txt"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        # Tool result should contain file contents
        results = events.of_type("tool_result")
        assert len(results) >= 1
        assert "line1" in results[0]["result"]

    async def test_edit_file_modifies_content(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "app.py").write_text("name = 'old'")
        config = _make_settings(ws)

        llm = ScriptedLLMClient([
            _tool_response([
                ("tc_1", "edit_file", {
                    "path": "app.py",
                    "old_text": "name = 'old'",
                    "new_text": "name = 'new'",
                })
            ]),
            _text_response("Updated app.py."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Update the name"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        assert (ws / "app.py").read_text() == "name = 'new'"


class TestParallelToolExecution:
    """LLM returns multiple tool calls — all should execute."""

    async def test_two_files_created(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        llm = ScriptedLLMClient([
            _tool_response([
                ("tc_1", "write_file", {"path": "a.txt", "content": "aaa"}),
                ("tc_2", "write_file", {"path": "b.txt", "content": "bbb"}),
            ]),
            _text_response("Created both files."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Create two files"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        assert (ws / "a.txt").read_text() == "aaa"
        assert (ws / "b.txt").read_text() == "bbb"
        # Two tool_call events, two tool_result events
        assert len(events.of_type("tool_call")) == 2
        assert len(events.of_type("tool_result")) == 2


class TestBashExecution:
    """LLM calls bash — verifies real command execution."""

    async def test_bash_echo(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "bash", {"command": "echo integration_test"})]),
            _text_response("Command ran successfully."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Run echo"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        results = events.of_type("tool_result")
        assert any("integration_test" in r["result"] for r in results)

    async def test_bash_dangerous_blocked(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "bash", {"command": "sudo rm -rf /"})]),
            _text_response("OK I won't do that."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Delete everything"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        results = events.of_type("tool_result")
        assert any("Blocked" in r["result"] or "Error" in r["result"] for r in results)


class TestMaxTurnsExhaustion:
    """Loop runs out of turns — forced final summary should fire."""

    async def test_forced_summary(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws, max_turns=2)

        # Both turns return tool calls (loop never gets done=True)
        # Then the forced summary call should happen
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "think", {"thought": "planning"})]),
            _tool_response([("tc_2", "think", {"thought": "still thinking"})]),
            _text_response("Summary: I thought about it for 2 turns."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Think deeply"}]
        usage = await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        # think is a SAFE_TOOL so tool_use_occurred should be False,
        # meaning no forced summary. Let's use write_file instead.
        pass

    async def test_forced_summary_with_unsafe_tools(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws, max_turns=2)

        # Both turns return unsafe tool calls — tool_use_occurred=True
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "write_file", {"path": "a.txt", "content": "x"})]),
            _tool_response([("tc_2", "write_file", {"path": "b.txt", "content": "y"})]),
            # Third response is for the forced final summary (no tools call)
            _text_response("Final summary: created two files."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Create files"}]
        usage = await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        # The third LLM call is the forced summary
        assert len(llm.calls) == 3
        # Last call should have tools=[] (no tools for summary)
        assert llm.calls[2]["tools"] == []
        # Events should include the turn-limit notice
        text_deltas = events.of_type("text_delta")
        all_text = "".join(e["content"] for e in text_deltas)
        assert "Turn limit" in all_text or "Final summary" in all_text


class TestTruncationContinuation:
    """LLM returns stop_reason=max_tokens — loop should auto-continue."""

    async def test_continues_truncated_response(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        # First response: truncated (done=True but stop_reason=max_tokens)
        truncated = LLMResponse(
            content=[{"type": "text", "text": "I'll start by..."}],
            tool_calls=[],
            done=True,
            input_tokens=100,
            output_tokens=4096,
            stop_reason="max_tokens",
        )
        # Second response: complete
        complete = _text_response("...and that's the full answer.")

        llm = ScriptedLLMClient([truncated, complete])
        events = EventCollector()

        messages = [{"role": "user", "content": "Explain something long"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        # Two LLM calls: truncated + continuation
        assert len(llm.calls) == 2
        # The continuation prompt should have been injected
        last_messages = llm.calls[1]["messages"]
        continuation_msg = last_messages[-1]
        assert "continue" in continuation_msg["content"].lower()

    async def test_max_continuations_limit(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        # All responses are truncated — should stop after MAX_CONTINUATIONS
        truncated = LLMResponse(
            content=[{"type": "text", "text": "partial..."}],
            tool_calls=[],
            done=True,
            input_tokens=100,
            output_tokens=4096,
            stop_reason="max_tokens",
        )
        responses = [truncated] * (MAX_CONTINUATIONS + 2)
        llm = ScriptedLLMClient(responses)
        events = EventCollector()

        messages = [{"role": "user", "content": "Go on forever"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        # 1 initial + MAX_CONTINUATIONS continuations = MAX_CONTINUATIONS + 1
        assert len(llm.calls) == MAX_CONTINUATIONS + 1


class TestCancellation:
    """Cancellation event stops the loop."""

    async def test_cancelled_before_llm_call(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        llm = ScriptedLLMClient([_text_response("Should not appear")])
        events = EventCollector()
        cancelled = asyncio.Event()
        cancelled.set()  # pre-cancelled

        messages = [{"role": "user", "content": "Hello"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events, cancelled=cancelled,
        )

        # LLM should never be called
        assert len(llm.calls) == 0
        # Error event should be emitted
        errors = events.of_type("error")
        assert any("Cancelled" in e["message"] for e in errors)

    async def test_cancelled_between_turns(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        cancelled = asyncio.Event()

        # Turn 1: tool call succeeds. Before turn 2, cancel.
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "read_file", {"path": "nonexistent"})]),
            _text_response("Done."),
        ])

        events = EventCollector()

        # Cancel after the first send_event (tool_call)
        real_events = EventCollector()

        async def cancelling_send_event(event):
            await real_events(event)
            # Cancel after the first tool_result
            if event.get("type") == "tool_result":
                cancelled.set()

        messages = [{"role": "user", "content": "Read a file"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=cancelling_send_event, cancelled=cancelled,
        )

        # Only one LLM call (cancelled before second)
        assert len(llm.calls) == 1
        errors = real_events.of_type("error")
        assert any("Cancelled" in e["message"] for e in errors)


class TestTokenBudget:
    """Loop stops when token budget exceeded."""

    async def test_budget_exceeded(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws, max_token_budget=250)

        # Each response uses 100+50=150 tokens. Budget=250.
        # After turn 1 tool execution: 150 used. After turn 2: 300 > 250.
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "think", {"thought": "a"})]),
            _tool_response([("tc_2", "think", {"thought": "b"})]),
            _text_response("Done."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Think"}]
        usage = await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        errors = events.of_type("error")
        assert any("budget" in e["message"].lower() for e in errors)


class TestWrapUpHint:
    """Wrap-up hint is injected near the turn limit."""

    async def test_wrapup_injected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        # max_turns=4, WRAPUP_TURNS_REMAINING=3
        # Turn 0: remaining=3, hint injected (if tool_use_occurred)
        # So we need tool_use_occurred=True first, then check later turns
        config = _make_settings(ws, max_turns=4)

        # Turn 0: tool call (sets tool_use_occurred=True)
        # Turn 1: tool call (remaining=2 <= 3, hint should be in system prompt)
        # Turn 2: tool call (remaining=1 <= 3, hint should be in system prompt)
        # Turn 3: tool call (remaining=0 <= 3, hint should be in system prompt)
        # Then forced summary
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "write_file", {"path": "x.txt", "content": "x"})]),
            _tool_response([("tc_2", "write_file", {"path": "y.txt", "content": "y"})]),
            _tool_response([("tc_3", "write_file", {"path": "z.txt", "content": "z"})]),
            _tool_response([("tc_4", "write_file", {"path": "w.txt", "content": "w"})]),
            _text_response("Final summary."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Create files"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        # Turn 0: remaining=3, tool_use_occurred becomes True after exec
        # Turn 1: remaining=2 <=3, tool_use_occurred=True → hint injected
        # Check that some calls have the wrap-up hint in the system prompt
        calls_with_hint = [
            c for c in llm.calls
            if WRAPUP_HINT in c.get("system", "")
        ]
        assert len(calls_with_hint) >= 1


class TestToolApproval:
    """Tool approval gate pauses and resumes based on queue."""

    async def test_approve_executes_tool(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        approval_queue = asyncio.Queue()

        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "write_file", {"path": "ok.txt", "content": "approved"})]),
            _text_response("File created."),
        ])
        events = EventCollector()

        # Pre-load approval decision
        await approval_queue.put("approve")

        messages = [{"role": "user", "content": "Write a file"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events, approval_queue=approval_queue,
        )

        # File should be created (tool was approved)
        assert (ws / "ok.txt").exists()
        # Approval request event should have been emitted
        assert len(events.of_type("tool_approval_request")) == 1

    async def test_deny_blocks_tool(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        approval_queue = asyncio.Queue()

        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "write_file", {"path": "bad.txt", "content": "denied"})]),
            _text_response("OK, I won't create the file."),
        ])
        events = EventCollector()

        await approval_queue.put("deny")

        messages = [{"role": "user", "content": "Write a file"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events, approval_queue=approval_queue,
        )

        # File should NOT be created
        assert not (ws / "bad.txt").exists()
        # Tool result should say "denied"
        results = events.of_type("tool_result")
        assert any("denied" in r["result"].lower() for r in results)

    async def test_auto_approve_disables_future_approvals(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        approval_queue = asyncio.Queue()

        # Two tool turns
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "write_file", {"path": "a.txt", "content": "1"})]),
            _tool_response([("tc_2", "write_file", {"path": "b.txt", "content": "2"})]),
            _text_response("Both files created."),
        ])
        events = EventCollector()

        # Auto-approve on first request — second should not ask
        await approval_queue.put("auto_approve")

        messages = [{"role": "user", "content": "Write two files"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events, approval_queue=approval_queue,
        )

        # Both files should exist
        assert (ws / "a.txt").exists()
        assert (ws / "b.txt").exists()
        # Only ONE approval request (auto_approve disables the rest)
        assert len(events.of_type("tool_approval_request")) == 1

    async def test_safe_tools_skip_approval(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "test.txt").write_text("content")
        config = _make_settings(ws)
        approval_queue = asyncio.Queue()

        # read_file is in SAFE_TOOLS — should not trigger approval
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "read_file", {"path": "test.txt"})]),
            _text_response("Read the file."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Read a file"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events, approval_queue=approval_queue,
        )

        # No approval request
        assert len(events.of_type("tool_approval_request")) == 0
        # Tool result should contain file content
        results = events.of_type("tool_result")
        assert any("content" in r["result"] for r in results)


class TestContextCompaction:
    """Auto-compaction triggers when input_tokens exceed threshold."""

    async def test_auto_compact_triggered(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        # threshold = 0.7, context_window = 1000 → trigger at >700 input_tokens
        config = _make_settings(ws, context_window=1000, compact_threshold=0.7)

        # Turn 1: returns 800 input_tokens (exceeds threshold)
        high_input_response = _tool_response(
            [("tc_1", "think", {"thought": "thinking"})],
            input_tokens=800,
            output_tokens=50,
        )
        # Turn 2: compaction LLM call for summarization (via create())
        # Turn 3: after compaction, final text response
        llm = ScriptedLLMClient([
            high_input_response,
            # This is the compaction summary call (via llm.create)
            _text_response("Summary of conversation so far."),
            # This is the next loop turn after compaction
            _text_response("Done with the task."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Do something"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events,
        )

        # Should have a compact event
        compacts = events.of_type("compact")
        assert len(compacts) >= 1
        assert "800" in compacts[0]["message"] or "Compact" in compacts[0]["message"]

    async def test_compact_messages_saves_transcript(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "reply3"},
            {"role": "user", "content": "msg4"},
            {"role": "assistant", "content": "reply4"},
            {"role": "user", "content": "msg5"},
            {"role": "assistant", "content": "reply5"},
            {"role": "user", "content": "msg6"},
            {"role": "assistant", "content": "reply6"},
        ]

        llm = ScriptedLLMClient([
            _text_response("Summarized: discussed topics 1-4."),
        ])

        result = await _compact_messages(messages, llm, "test-model", workspace=ws)

        # Transcript should be saved
        transcripts = list((ws / ".transcripts").glob("transcript_*.jsonl"))
        assert len(transcripts) == 1
        # Result should be shorter than original
        assert len(result) < len(messages)
        # Should keep recent messages
        assert result[-1]["content"] == "reply6"


class TestTaskManager:
    """Task management tools work through the loop."""

    async def test_task_create_and_list(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        task_mgr = TaskManager(ws)

        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "task_create", {
                "subject": "Fix bug", "description": "Fix the login bug",
            })]),
            _tool_response([("tc_2", "task_list", {})]),
            _text_response("Task created and listed."),
        ])
        events = EventCollector()

        messages = [{"role": "user", "content": "Create a task"}]
        await agent_loop(
            messages=messages, config=config, llm=llm,
            skill_loader=_make_skill_loader(ws), todo=TodoManager(),
            send_event=events, task_manager=task_mgr,
        )

        # Task should be persisted on disk
        tasks = await task_mgr.list_all()
        assert len(tasks) == 1
        assert tasks[0].subject == "Fix bug"

        # task_update events should have been emitted
        task_updates = events.of_type("task_update")
        assert len(task_updates) >= 1


class TestSubagent:
    """Subagent spawning via run_subagent."""

    async def test_subagent_explore(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "code.py").write_text("def hello(): pass")
        config = _make_settings(ws)

        # Subagent turn 1: reads file. Turn 2: returns summary.
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "read_file", {"path": "code.py"})]),
            _text_response("Found hello() function in code.py."),
        ])
        events = EventCollector()

        summary = await run_subagent(
            description="Explore code",
            prompt="Find all functions in code.py",
            agent_type="explore",
            config=config,
            workspace=ws,
            todo=TodoManager(),
            skill_loader=_make_skill_loader(ws),
            send_event=events,
            llm=llm,
            depth=0,
        )

        assert "hello()" in summary
        # Should have subagent_start and subagent_end events
        assert len(events.of_type("subagent_start")) == 1
        assert len(events.of_type("subagent_end")) == 1

    async def test_subagent_invalid_type(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        llm = ScriptedLLMClient([])
        events = EventCollector()

        result = await run_subagent(
            description="Bad", prompt="...", agent_type="nonexistent",
            config=config, workspace=ws, todo=TodoManager(),
            skill_loader=_make_skill_loader(ws), send_event=events,
            llm=llm, depth=0,
        )

        assert "Error" in result


class TestBuildRegistry:
    """build_registry wires up the correct tools."""

    def test_default_tools_registered(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        async def noop(event): pass

        llm = ScriptedLLMClient([])
        registry = build_registry(
            config=config, workspace=ws, todo=TodoManager(),
            skill_loader=_make_skill_loader(ws), send_event=noop, llm=llm,
        )

        names = registry.get_names()
        assert "bash" in names
        assert "read_file" in names
        assert "read_file_range" in names
        assert "search_code" in names
        assert "list_symbols" in names
        assert "find_references" in names
        assert "write_file" in names
        assert "edit_file" in names
        assert "think" in names
        assert "compact" in names
        assert "list_skills" in names
        # task tool should be included by default (depth=0)
        assert "task" in names

    def test_task_manager_tools_registered(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        task_mgr = TaskManager(ws)

        async def noop(event): pass

        registry = build_registry(
            config=config, workspace=ws, todo=TodoManager(),
            skill_loader=_make_skill_loader(ws), send_event=noop,
            llm=ScriptedLLMClient([]), task_manager=task_mgr,
        )

        assert "task_create" in registry.get_names()
        assert "task_list" in registry.get_names()

    def test_no_task_tool_at_depth_2(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        async def noop(event): pass

        registry = build_registry(
            config=config, workspace=ws, todo=TodoManager(),
            skill_loader=_make_skill_loader(ws), send_event=noop,
            llm=ScriptedLLMClient([]), depth=2,
        )

        assert "task" not in registry.get_names()


class TestBuildSystemPrompt:
    """System prompt construction."""

    def test_default_prompt(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        sl = _make_skill_loader(ws)

        prompt = build_system_prompt(ws, sl)
        assert "coding agent" in prompt.lower()
        assert str(ws) in prompt

    def test_subagent_prompt(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        sl = _make_skill_loader(ws)

        prompt = build_system_prompt(ws, sl, agent_type="explore")
        assert "exploration" in prompt.lower()

    def test_memory_injected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        sl = _make_skill_loader(ws)

        prompt = build_system_prompt(
            ws, sl, memory_content="User prefers Python."
        )
        assert "User prefers Python" in prompt


class TestSanitizeMessages:
    """_sanitize_messages fixes orphaned tool_use blocks."""

    def test_orphaned_tool_use_stripped(self):
        from agent_service.api.websocket import _sanitize_messages

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "Let me help."},
                {"type": "tool_use", "id": "tc_1", "name": "bash",
                 "input": {"command": "ls"}},
            ]},
            # No tool_result follows — orphaned
            {"role": "user", "content": "Thanks"},
        ]

        result = _sanitize_messages(messages)

        # tool_use should be stripped from assistant message
        assistant_content = result[1]["content"]
        assert all(
            b.get("type") != "tool_use"
            for b in assistant_content
            if isinstance(b, dict)
        )
        # text block should remain
        assert any(
            b.get("type") == "text"
            for b in assistant_content
            if isinstance(b, dict)
        )

    def test_matched_tool_use_kept(self):
        from agent_service.api.websocket import _sanitize_messages

        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tc_1", "name": "bash",
                 "input": {"command": "ls"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tc_1",
                 "content": "file.txt"},
            ]},
        ]

        result = _sanitize_messages(messages)

        # tool_use should be kept (it has a matching result)
        assistant_content = result[0]["content"]
        assert any(
            b.get("type") == "tool_use"
            for b in assistant_content
            if isinstance(b, dict)
        )


# ---------------------------------------------------------------------------
# Agent-initiated plan mode
# ---------------------------------------------------------------------------


class TestAgentInitiatedPlanMode:
    """Tests for enter_plan_mode / exit_plan_mode agent tools."""

    async def test_enter_plan_mode_switches_tools_and_prompt(self, tmp_path):
        """Calling enter_plan_mode restricts tools and emits plan_mode_changed."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws, max_turns=10)
        skill_loader = _make_skill_loader(ws)

        # Step 1: agent calls enter_plan_mode
        # Step 2: agent responds with plan text (done)
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "enter_plan_mode", {})]),
            _text_response("## Plan: My Plan\nDo the thing."),
        ])
        events = EventCollector()
        messages = [{"role": "user", "content": "Refactor auth system"}]

        usage = await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=skill_loader,
            todo=TodoManager(),
            send_event=events,
        )

        # plan_mode_changed event emitted
        pm_events = events.of_type("plan_mode_changed")
        assert len(pm_events) == 1
        assert pm_events[0]["enabled"] is True

        # Return value includes plan_mode: True
        assert usage.get("plan_mode") is True

        # plan_ready event emitted at end (fallback)
        pr_events = events.of_type("plan_ready")
        assert len(pr_events) == 1
        assert "My Plan" in pr_events[0]["plan"]

        # After entering plan mode, the LLM should have been called with
        # restricted tools (second call). Check that exit_plan_mode is
        # available and write tools are excluded.
        second_call = llm.calls[1]
        tool_names = {t["name"] for t in second_call["tools"]}
        assert "exit_plan_mode" in tool_names
        assert "bash" not in tool_names
        assert "write_file" not in tool_names
        assert "edit_file" not in tool_names

    async def test_exit_plan_mode_breaks_loop_with_plan_ready(self, tmp_path):
        """Calling exit_plan_mode emits plan_ready and breaks the loop."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws, max_turns=10)
        skill_loader = _make_skill_loader(ws)

        # Start already in plan mode; agent writes plan then calls exit_plan_mode
        llm = ScriptedLLMClient([
            _text_response("## Plan: Refactor\n### Steps\n1. Do it"),
            # This won't be reached — the text response above will end the loop
            # normally. We need to have the agent call exit_plan_mode.
        ])

        # Actually, let's script it properly: agent calls exit_plan_mode
        llm = ScriptedLLMClient([
            _tool_response(
                [("tc_1", "exit_plan_mode", {})],
                text="## Plan: Refactor\n### Steps\n1. Do it",
            ),
            _text_response("(should not be reached)"),
        ])
        events = EventCollector()
        messages = [{"role": "user", "content": "Refactor auth system"}]

        usage = await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=skill_loader,
            todo=TodoManager(),
            send_event=events,
            plan_mode=True,
        )

        # plan_ready event was emitted
        pr_events = events.of_type("plan_ready")
        assert len(pr_events) == 1
        assert "Refactor" in pr_events[0]["plan"]

        # Loop broke — only one LLM call made
        assert len(llm.calls) == 1

        # Return value reflects plan mode
        assert usage.get("plan_mode") is True

    async def test_enter_plan_mode_noop_when_already_in_plan_mode(self, tmp_path):
        """enter_plan_mode when already in plan mode is a no-op."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws, max_turns=10)
        skill_loader = _make_skill_loader(ws)

        # Already in plan mode; agent calls enter_plan_mode again
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "enter_plan_mode", {})]),
            _text_response("Still in plan mode."),
        ])
        events = EventCollector()
        messages = [{"role": "user", "content": "Plan something"}]

        await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=skill_loader,
            todo=TodoManager(),
            send_event=events,
            plan_mode=True,
        )

        # No plan_mode_changed event (already in plan mode)
        pm_events = events.of_type("plan_mode_changed")
        assert len(pm_events) == 0

    async def test_exit_plan_mode_noop_when_not_in_plan_mode(self, tmp_path):
        """exit_plan_mode when not in plan mode does not break or emit."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws, max_turns=10)
        skill_loader = _make_skill_loader(ws)

        # Not in plan mode; agent mistakenly calls exit_plan_mode
        llm = ScriptedLLMClient([
            _tool_response([("tc_1", "exit_plan_mode", {})]),
            _text_response("Done."),
        ])
        events = EventCollector()
        messages = [{"role": "user", "content": "Do something"}]

        await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=skill_loader,
            todo=TodoManager(),
            send_event=events,
            plan_mode=False,
        )

        # No plan_ready event (not in plan mode)
        pr_events = events.of_type("plan_ready")
        assert len(pr_events) == 0

        # Loop continued — both LLM calls were made
        assert len(llm.calls) == 2

    async def test_return_value_includes_plan_mode_key(self, tmp_path):
        """Return dict always includes plan_mode key."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        skill_loader = _make_skill_loader(ws)

        llm = ScriptedLLMClient([_text_response("Hello")])
        events = EventCollector()
        messages = [{"role": "user", "content": "Hi"}]

        usage = await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=skill_loader,
            todo=TodoManager(),
            send_event=events,
        )

        assert "plan_mode" in usage
        assert usage["plan_mode"] is False

    async def test_tool_defs_exclude_exit_in_normal_mode(self, tmp_path):
        """In normal mode, exit_plan_mode is excluded from tool definitions."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        skill_loader = _make_skill_loader(ws)

        llm = ScriptedLLMClient([_text_response("Hello")])
        events = EventCollector()
        messages = [{"role": "user", "content": "Hi"}]

        await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=skill_loader,
            todo=TodoManager(),
            send_event=events,
        )

        # Check the tool defs passed to the LLM
        tool_names = {t["name"] for t in llm.calls[0]["tools"]}
        assert "enter_plan_mode" in tool_names
        assert "exit_plan_mode" not in tool_names

    async def test_tool_defs_exclude_enter_in_plan_mode(self, tmp_path):
        """In plan mode, enter_plan_mode is excluded (already in it)."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        skill_loader = _make_skill_loader(ws)

        llm = ScriptedLLMClient([_text_response("My plan")])
        events = EventCollector()
        messages = [{"role": "user", "content": "Plan something"}]

        await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=skill_loader,
            todo=TodoManager(),
            send_event=events,
            plan_mode=True,
        )

        # Check tool defs: exit_plan_mode present, enter_plan_mode absent
        tool_names = {t["name"] for t in llm.calls[0]["tools"]}
        assert "exit_plan_mode" in tool_names
        assert "enter_plan_mode" not in tool_names
        # Write tools excluded
        assert "bash" not in tool_names
        assert "write_file" not in tool_names


class TestExtractPlanText:
    """Tests for the _extract_plan_text helper."""

    def test_extracts_from_text_string(self):
        messages = [
            {"role": "user", "content": "Plan something"},
            {"role": "assistant", "content": "Here is my plan"},
        ]
        assert _extract_plan_text(messages) == "Here is my plan"

    def test_extracts_from_content_blocks(self):
        messages = [
            {"role": "user", "content": "Plan"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "Plan details here"},
            ]},
        ]
        assert _extract_plan_text(messages) == "Plan details here"

    def test_returns_empty_for_no_assistant(self):
        messages = [{"role": "user", "content": "Plan"}]
        assert _extract_plan_text(messages) == ""

    def test_returns_empty_for_empty_messages(self):
        assert _extract_plan_text([]) == ""

    def test_collects_all_assistant_messages(self):
        """_extract_plan_text collects from ALL assistant messages (fallback path).
        Primary plan extraction uses exit_plan_mode tool's plan parameter."""
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "First plan"},
            {"role": "user", "content": "Revise"},
            {"role": "assistant", "content": "Revised plan"},
        ]
        assert _extract_plan_text(messages) == "First plan\n\nRevised plan"

    def test_since_index_skips_earlier_messages(self):
        messages = [
            {"role": "assistant", "content": "Exploration chatter"},
            {"role": "user", "content": "tool result"},
            {"role": "assistant", "content": "The actual plan"},
        ]
        assert _extract_plan_text(messages, since_index=2) == "The actual plan"


# ---------------------------------------------------------------------------
# Error path tests (Phase 4.3)
# ---------------------------------------------------------------------------


class TestCompactionFailureRecovery:
    """Test fallback behavior when LLM compaction fails."""

    async def test_compaction_falls_back_on_llm_failure(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        # Create a failing LLM client
        class FailingLLM:
            async def create(self, **kwargs):
                raise ValueError("LLM unavailable")

            import contextlib

            @contextlib.asynccontextmanager
            async def stream(self, **kwargs):
                yield self

        # Build enough messages to trigger compaction
        messages = []
        for i in range(30):
            messages.append({"role": "user", "content": f"Message {i}"})
            messages.append({"role": "assistant", "content": f"Response {i}"})

        result = await _compact_messages(
            messages, FailingLLM(), "test-model", ws, temperature=1.0
        )
        # Should fall back to hard truncation
        assert len(result) < len(messages)
        # First message should mention dropped messages
        assert "dropped" in result[0]["content"].lower() or "removed" in result[0]["content"].lower()


class TestCancellationDuringLoop:
    """Test that the agent loop respects cancellation signals."""

    async def test_cancellation_stops_loop(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        # LLM that returns tool calls — loop would continue forever
        responses = [
            _tool_response([("t1", "think", {"thought": "thinking"})]),
        ] * 10  # many responses

        llm = ScriptedLLMClient(responses)
        events = EventCollector()
        cancelled = asyncio.Event()

        # Set cancelled before starting
        cancelled.set()

        messages = [{"role": "user", "content": "Do something"}]
        usage = await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=_make_skill_loader(ws),
            todo=TodoManager(),
            send_event=events,
            cancelled=cancelled,
        )
        # Should have stopped early (at most 1-2 LLM calls)
        assert len(llm.calls) <= 2


class TestMaxTokensRetryExhaustion:
    """Test that max_tokens retry exhaustion works correctly."""

    async def test_max_continuations_reached(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        # All responses have stop_reason=max_tokens, triggering continuation
        truncated = LLMResponse(
            content=[{"type": "text", "text": "partial output..."}],
            tool_calls=[],
            done=True,
            input_tokens=100,
            output_tokens=4096,
            stop_reason="max_tokens",
        )
        # Need MAX_CONTINUATIONS + 1 responses (original + continuations)
        # then a final done response
        responses = [truncated] * (MAX_CONTINUATIONS + 1)
        responses.append(_text_response("Final response"))

        llm = ScriptedLLMClient(responses)
        events = EventCollector()

        messages = [{"role": "user", "content": "Write a long essay"}]
        usage = await agent_loop(
            messages=messages,
            config=config,
            llm=llm,
            skill_loader=_make_skill_loader(ws),
            todo=TodoManager(),
            send_event=events,
        )
        # Should have made continuation attempts
        assert len(llm.calls) >= MAX_CONTINUATIONS + 1


class TestSubagentMaxDepth:
    """Test that subagent depth is enforced."""

    async def test_subagent_depth_limit(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)

        # The registry built at depth=2 should NOT include the task tool
        registry = build_registry(
            config=config,
            workspace=ws,
            todo=TodoManager(),
            skill_loader=_make_skill_loader(ws),
            send_event=EventCollector(),
            llm=ScriptedLLMClient([]),
            depth=2,
        )
        assert not registry.has("task"), "task tool should not be available at depth 2"

        # depth=0 should include it
        registry_0 = build_registry(
            config=config,
            workspace=ws,
            todo=TodoManager(),
            skill_loader=_make_skill_loader(ws),
            send_event=EventCollector(),
            llm=ScriptedLLMClient([]),
            depth=0,
        )
        assert registry_0.has("task"), "task tool should be available at depth 0"
