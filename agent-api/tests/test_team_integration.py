"""Integration tests for the team system (MessageBus, ProtocolTracker, TeammateManager, team tools).

Wires real components together with only the LLM faked via ScriptedLLMClient.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import patch

import pytest

from agent_service.agent.llm import LLMResponse, ToolCall
from agent_service.agent.loop import agent_loop, build_registry
from agent_service.agent.message_bus import MessageBus, TeamMessage, VALID_MSG_TYPES
from agent_service.agent.protocol_tracker import ProtocolTracker
from agent_service.agent.skill_loader import SkillLoader
from agent_service.agent.task_manager import TaskManager
from agent_service.agent.teammate_manager import TeammateManager
from agent_service.agent.todo_manager import TodoManager
from agent_service.config import Settings


# ---------------------------------------------------------------------------
# ScriptedLLMClient + helpers (same as test_integration.py)
# ---------------------------------------------------------------------------


class ScriptedLLMClient:
    """Fake LLM that returns responses from a script (list)."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def _next(self, **kwargs) -> LLMResponse:
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
    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    def __aiter__(self):
        return self._iter_text()

    async def _iter_text(self):
        for block in self._response.content:
            if isinstance(block, dict) and block.get("type") == "text":
                yield block["text"]

    async def get_response(self) -> LLMResponse:
        return self._response


class EventCollector:
    """Collects send_event calls for assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def __call__(self, event: dict) -> None:
        self.events.append(event)

    def of_type(self, etype: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == etype]


def _make_settings(workspace: Path, **overrides) -> Settings:
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


def _text_response(text: str, input_tokens=100, output_tokens=50) -> LLMResponse:
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
# Helpers
# ---------------------------------------------------------------------------


_original_wait_for = asyncio.wait_for


async def _fast_wait_for(coro, *, timeout=None):
    """Test helper: replace asyncio.wait_for with near-instant timeout."""
    try:
        return await _original_wait_for(coro, timeout=0.001)
    except asyncio.TimeoutError:
        raise


def _make_skill_loader(workspace: Path) -> SkillLoader:
    skills_dir = workspace / "_skills"
    skills_dir.mkdir(exist_ok=True)
    return SkillLoader(skills_dir)


def _make_team_stack(
    workspace: Path,
    *,
    teammate_llm: ScriptedLLMClient | None = None,
    task_manager: TaskManager | None = None,
    persist: bool = False,
) -> tuple[MessageBus, TeammateManager, ProtocolTracker, EventCollector, Settings]:
    """Create a fully wired team stack for tests.

    Returns (bus, team_manager, tracker, events, config).
    """
    config = _make_settings(workspace)
    events = EventCollector()
    persist_dir = (workspace / ".team" / "inbox") if persist else None
    bus = MessageBus(persist_dir=persist_dir)
    tracker = ProtocolTracker()
    llm = teammate_llm or ScriptedLLMClient([])
    tm = TeammateManager(
        workspace=workspace,
        bus=bus,
        llm=llm,
        config=config,
        send_event=events,
        task_manager=task_manager,
    )
    return bus, tm, tracker, events, config


# ---------------------------------------------------------------------------
# TestMessageBusIntegration
# ---------------------------------------------------------------------------


class TestMessageBusIntegration:
    """MessageBus: send/receive, broadcast, persistence, validation."""

    async def test_send_and_receive(self, tmp_path):
        bus = MessageBus()
        result = await bus.send("alice", "bob", "hello", "message")
        assert "Sent" in result

        inbox = await bus.read_inbox("bob")
        assert len(inbox) == 1
        assert inbox[0].sender == "alice"
        assert inbox[0].content == "hello"
        assert inbox[0].type == "message"

    async def test_broadcast_skips_sender(self, tmp_path):
        bus = MessageBus()
        result = await bus.broadcast("lead", "team standup", ["lead", "alice", "bob"])
        assert "2" in result  # broadcast to 2 (skipped lead)

        alice_inbox = await bus.read_inbox("alice")
        bob_inbox = await bus.read_inbox("bob")
        lead_inbox = await bus.read_inbox("lead")

        assert len(alice_inbox) == 1
        assert len(bob_inbox) == 1
        assert len(lead_inbox) == 0

    async def test_jsonl_persistence(self, tmp_path):
        persist_dir = tmp_path / "inbox"
        bus = MessageBus(persist_dir=persist_dir)

        await bus.send("alice", "bob", "persisted msg", "message")

        # JSONL file should exist before drain
        jsonl_path = persist_dir / "bob.jsonl"
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["content"] == "persisted msg"

        # After read_inbox, persistence file is cleared
        await bus.read_inbox("bob")
        assert jsonl_path.read_text() == ""

    async def test_invalid_msg_type(self, tmp_path):
        bus = MessageBus()
        result = await bus.send("alice", "bob", "bad", "nonexistent_type")
        assert "Error" in result
        assert "Invalid" in result

        # Nothing should be in inbox
        inbox = await bus.read_inbox("bob")
        assert len(inbox) == 0

    async def test_empty_inbox(self, tmp_path):
        bus = MessageBus()
        inbox = await bus.read_inbox("nobody")
        assert inbox == []


# ---------------------------------------------------------------------------
# TestProtocolTrackerIntegration
# ---------------------------------------------------------------------------


class TestProtocolTrackerIntegration:
    """ProtocolTracker: lifecycle and filtered queries."""

    async def test_full_lifecycle(self, tmp_path):
        tracker = ProtocolTracker()

        # Create
        req = await tracker.create_request("shutdown", "alice")
        assert req.status == "pending"
        assert req.target == "alice"

        # Pending list
        pending = await tracker.list_pending()
        assert len(pending) == 1

        # Resolve
        resolved = await tracker.resolve(req.id, approved=True)
        assert resolved.status == "approved"

        # No longer pending
        pending = await tracker.list_pending()
        assert len(pending) == 0

        # Still retrievable
        got = await tracker.get(req.id)
        assert got.status == "approved"

    async def test_type_filtered_pending(self, tmp_path):
        tracker = ProtocolTracker()
        await tracker.create_request("shutdown", "alice")
        await tracker.create_request("plan_approval", "bob")

        shutdown_pending = await tracker.list_pending("shutdown")
        assert len(shutdown_pending) == 1
        assert shutdown_pending[0].target == "alice"

        plan_pending = await tracker.list_pending("plan_approval")
        assert len(plan_pending) == 1
        assert plan_pending[0].target == "bob"


# ---------------------------------------------------------------------------
# TestTeammateWorkPhase
# ---------------------------------------------------------------------------


class TestTeammateWorkPhase:
    """Teammate WORK phase: text exit, tool use, duplicate rejection, inbox."""

    async def test_text_only_exit(self, tmp_path):
        """Teammate LLM returns text (done=True) → enters IDLE → times out."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        teammate_llm = ScriptedLLMClient([
            _text_response("Task complete. Reporting back."),
        ])
        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm,
        )

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            result = await tm.spawn("worker1", "coder", "Write hello.py")
            assert "Spawned" in result

            # Wait for the teammate task to finish
            await _original_wait_for(tm._tasks["worker1"], timeout=5.0)

        # Should have gone through working → idle → shutdown
        statuses = [
            e["status"] for e in events.events
            if e.get("type") == "teammate_status" and e.get("name") == "worker1"
        ]
        assert "working" in statuses
        assert "idle" in statuses
        assert "shutdown" in statuses

    async def test_tool_use_writes_file(self, tmp_path):
        """Teammate calls write_file → file should appear on disk."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        teammate_llm = ScriptedLLMClient([
            _tool_response([
                ("tc_1", "write_file", {"path": "from_teammate.py", "content": "# written by teammate"})
            ]),
            _text_response("Done writing file."),
        ])
        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm,
        )

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            await tm.spawn("writer", "coder", "Create from_teammate.py")
            await _original_wait_for(tm._tasks["writer"], timeout=5.0)

        assert (ws / "from_teammate.py").exists()
        assert "written by teammate" in (ws / "from_teammate.py").read_text()

    async def test_duplicate_spawn_rejected(self, tmp_path):
        """Spawning a teammate that's already working returns error."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        # This LLM will block — we'll use a long-running response list
        teammate_llm = ScriptedLLMClient([
            _tool_response([("tc_1", "think", {"thought": "thinking..."})]),
            _tool_response([("tc_2", "think", {"thought": "still thinking..."})]),
            _text_response("Done."),
        ])
        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm,
        )

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            result1 = await tm.spawn("dup", "coder", "Task A")
            assert "Spawned" in result1

            result2 = await tm.spawn("dup", "coder", "Task B")
            assert "Error" in result2
            assert "currently working" in result2

            # Clean up
            tm._tasks["dup"].cancel()
            with pytest.raises((asyncio.CancelledError, Exception)):
                await tm._tasks["dup"]

    async def test_inbox_messages_during_work(self, tmp_path):
        """Messages sent to a teammate are drained before each LLM call."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        # Teammate will make 2 LLM calls. We'll send a message between them.
        call_count = 0
        original_responses = [
            _tool_response([("tc_1", "think", {"thought": "step 1"})]),
            _text_response("Done after receiving inbox."),
        ]

        teammate_llm = ScriptedLLMClient(original_responses)
        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm,
        )

        # Send a message to the teammate before it starts (will be drained on first turn)
        await bus.send("lead", "inbox_test", "Here's additional context", "message")

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            await tm.spawn("inbox_test", "coder", "Do work")
            await asyncio.wait_for(tm._tasks["inbox_test"], timeout=5.0)

        # Verify the message was consumed (inbox should be empty now)
        remaining = await bus.read_inbox("inbox_test")
        assert len(remaining) == 0

        # Verify the LLM saw the inbox message in its context
        # The second call should have the inbox message injected
        assert len(teammate_llm.calls) >= 1
        all_messages = []
        for call in teammate_llm.calls:
            for msg in call.get("messages", []):
                content = msg.get("content", "")
                if isinstance(content, str) and "additional context" in content:
                    all_messages.append(msg)
        assert len(all_messages) >= 1


# ---------------------------------------------------------------------------
# TestTeammateShutdown
# ---------------------------------------------------------------------------


class TestTeammateShutdown:
    """Teammate shutdown via message and shutdown_all cancellation."""

    async def test_shutdown_via_message(self, tmp_path):
        """Sending shutdown_request message causes teammate to exit."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        # The teammate will get a shutdown_request on its first inbox drain
        teammate_llm = ScriptedLLMClient([
            _text_response("Should not see this."),
        ])
        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm,
        )

        # Pre-load a shutdown_request in the inbox
        await bus.send("lead", "shutme", "Please shut down.", "shutdown_request")

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            await tm.spawn("shutme", "coder", "Do work")
            await asyncio.wait_for(tm._tasks["shutme"], timeout=5.0)

        statuses = [
            e["status"] for e in events.events
            if e.get("type") == "teammate_status" and e.get("name") == "shutme"
        ]
        assert "shutdown" in statuses

        # LLM should never have been called (shutdown happened before LLM call)
        assert len(teammate_llm.calls) == 0

    async def test_shutdown_all_cancels_tasks(self, tmp_path):
        """shutdown_all() cancels all running teammate tasks."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        # Create a teammate that will loop for a while
        many_responses = [
            _tool_response([("tc_1", "think", {"thought": f"thinking {i}"})]) for i in range(20)
        ] + [_text_response("Done.")]
        teammate_llm = ScriptedLLMClient(many_responses)
        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm,
        )

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            await tm.spawn("long_runner", "coder", "Long task")
            # Let the teammate run a couple of turns
            await asyncio.sleep(0.1)

            # Cancel all
            await tm.shutdown_all()

        assert tm._tasks["long_runner"].done()


# ---------------------------------------------------------------------------
# TestLeadLoopWithTeams
# ---------------------------------------------------------------------------


class TestLeadLoopWithTeams:
    """Lead agent loop wired with team tools."""

    async def test_spawn_via_tool(self, tmp_path):
        """Lead calls spawn_teammate → teammate runs."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        # Teammate LLM: simple text response
        teammate_llm = ScriptedLLMClient([
            _text_response("Teammate done."),
        ])

        config = _make_settings(ws)
        events = EventCollector()
        bus = MessageBus()
        tracker = ProtocolTracker()
        tm = TeammateManager(
            workspace=ws, bus=bus, llm=teammate_llm,
            config=config, send_event=events,
        )

        # Lead LLM: spawn a teammate, then finish
        lead_llm = ScriptedLLMClient([
            _tool_response([
                ("tc_1", "spawn_teammate", {
                    "name": "helper",
                    "role": "coder",
                    "prompt": "Write hello.py",
                })
            ]),
            _text_response("Spawned the helper."),
        ])

        messages = [{"role": "user", "content": "Create a team"}]

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            await agent_loop(
                messages=messages,
                config=config,
                llm=lead_llm,
                skill_loader=_make_skill_loader(ws),
                todo=TodoManager(),
                send_event=events,
                team_manager=tm,
                message_bus=bus,
                protocol_tracker=tracker,
            )
            # Wait for teammate to finish
            if "helper" in tm._tasks:
                await asyncio.wait_for(tm._tasks["helper"], timeout=5.0)

        # spawn_teammate tool should have been called
        tool_calls = events.of_type("tool_call")
        assert any(tc.get("tool") == "spawn_teammate" for tc in tool_calls)

        # Teammate status events should appear
        teammate_events = [
            e for e in events.events
            if e.get("type") == "teammate_status" and e.get("name") == "helper"
        ]
        assert len(teammate_events) >= 1

    async def test_send_message_tool(self, tmp_path):
        """Lead calls send_message → message lands in recipient's inbox."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        config = _make_settings(ws)
        events = EventCollector()
        bus = MessageBus()
        tracker = ProtocolTracker()
        tm = TeammateManager(
            workspace=ws, bus=bus, llm=ScriptedLLMClient([]),
            config=config, send_event=events,
        )
        # Register a fake teammate so member_names() works
        from agent_service.agent.teammate_manager import TeammateConfig
        tm._teammates["alice"] = TeammateConfig(name="alice", role="coder", status="working")

        lead_llm = ScriptedLLMClient([
            _tool_response([
                ("tc_1", "send_message", {"to": "alice", "content": "Please review"})
            ]),
            _text_response("Message sent."),
        ])

        messages = [{"role": "user", "content": "Send a message"}]
        await agent_loop(
            messages=messages,
            config=config,
            llm=lead_llm,
            skill_loader=_make_skill_loader(ws),
            todo=TodoManager(),
            send_event=events,
            team_manager=tm,
            message_bus=bus,
            protocol_tracker=tracker,
        )

        # Message should be in alice's inbox
        inbox = await bus.read_inbox("alice")
        assert len(inbox) == 1
        assert inbox[0].content == "Please review"
        assert inbox[0].sender == "lead"

    async def test_lead_reads_inbox(self, tmp_path):
        """Messages from teammates are drained into lead's context."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        config = _make_settings(ws)
        events = EventCollector()
        bus = MessageBus()
        tracker = ProtocolTracker()
        tm = TeammateManager(
            workspace=ws, bus=bus, llm=ScriptedLLMClient([]),
            config=config, send_event=events,
        )

        # Pre-load a message from a teammate to the lead
        await bus.send("alice", "lead", "Task complete!", "message")

        lead_llm = ScriptedLLMClient([
            _text_response("I see alice finished."),
        ])

        messages = [{"role": "user", "content": "Check status"}]
        await agent_loop(
            messages=messages,
            config=config,
            llm=lead_llm,
            skill_loader=_make_skill_loader(ws),
            todo=TodoManager(),
            send_event=events,
            team_manager=tm,
            message_bus=bus,
            protocol_tracker=tracker,
        )

        # The lead's LLM call should have the inbox message in context
        assert len(lead_llm.calls) == 1
        all_content = json.dumps(lead_llm.calls[0]["messages"])
        assert "Task complete!" in all_content

    async def test_broadcast_tool(self, tmp_path):
        """Lead calls broadcast → all active teammates receive."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        config = _make_settings(ws)
        events = EventCollector()
        bus = MessageBus()
        tracker = ProtocolTracker()
        tm = TeammateManager(
            workspace=ws, bus=bus, llm=ScriptedLLMClient([]),
            config=config, send_event=events,
        )
        from agent_service.agent.teammate_manager import TeammateConfig
        tm._teammates["alice"] = TeammateConfig(name="alice", role="coder", status="working")
        tm._teammates["bob"] = TeammateConfig(name="bob", role="tester", status="working")

        lead_llm = ScriptedLLMClient([
            _tool_response([
                ("tc_1", "broadcast", {"content": "All stop!"})
            ]),
            _text_response("Broadcast sent."),
        ])

        messages = [{"role": "user", "content": "Broadcast"}]
        await agent_loop(
            messages=messages,
            config=config,
            llm=lead_llm,
            skill_loader=_make_skill_loader(ws),
            todo=TodoManager(),
            send_event=events,
            team_manager=tm,
            message_bus=bus,
            protocol_tracker=tracker,
        )

        alice_inbox = await bus.read_inbox("alice")
        bob_inbox = await bus.read_inbox("bob")
        assert len(alice_inbox) == 1
        assert alice_inbox[0].content == "All stop!"
        assert len(bob_inbox) == 1

    async def test_team_tools_registered(self, tmp_path):
        """build_registry includes team tools when team_manager + bus are provided."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        events = EventCollector()
        bus = MessageBus()
        tracker = ProtocolTracker()
        tm = TeammateManager(
            workspace=ws, bus=bus, llm=ScriptedLLMClient([]),
            config=config, send_event=events,
        )

        async def noop(event): pass

        registry = build_registry(
            config=config,
            workspace=ws,
            todo=TodoManager(),
            skill_loader=_make_skill_loader(ws),
            send_event=noop,
            llm=ScriptedLLMClient([]),
            team_manager=tm,
            message_bus=bus,
            protocol_tracker=tracker,
        )

        names = registry.get_names()
        for tool in ["spawn_teammate", "list_teammates", "send_message", "read_inbox", "broadcast"]:
            assert tool in names, f"{tool} not registered"

    async def test_protocol_tools_registered(self, tmp_path):
        """build_registry includes protocol tools when tracker is provided."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        config = _make_settings(ws)
        events = EventCollector()
        bus = MessageBus()
        tracker = ProtocolTracker()
        tm = TeammateManager(
            workspace=ws, bus=bus, llm=ScriptedLLMClient([]),
            config=config, send_event=events,
        )

        async def noop(event): pass

        registry = build_registry(
            config=config,
            workspace=ws,
            todo=TodoManager(),
            skill_loader=_make_skill_loader(ws),
            send_event=noop,
            llm=ScriptedLLMClient([]),
            team_manager=tm,
            message_bus=bus,
            protocol_tracker=tracker,
        )

        names = registry.get_names()
        for tool in ["shutdown_request", "check_protocol", "plan_review"]:
            assert tool in names, f"{tool} not registered"


# ---------------------------------------------------------------------------
# TestShutdownProtocol
# ---------------------------------------------------------------------------


class TestShutdownProtocol:
    """End-to-end shutdown: lead → tracker → bus → teammate exits."""

    async def test_shutdown_end_to_end(self, tmp_path):
        """Lead sends shutdown_request tool → teammate exits gracefully."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        # Teammate LLM: will loop thinking until shutdown_request arrives
        teammate_llm = ScriptedLLMClient([
            _tool_response([("tc_1", "think", {"thought": "working..."})]),
            _tool_response([("tc_2", "think", {"thought": "still working..."})]),
            _text_response("Done."),
        ])

        config = _make_settings(ws)
        events = EventCollector()
        bus = MessageBus()
        tracker = ProtocolTracker()
        tm = TeammateManager(
            workspace=ws, bus=bus, llm=teammate_llm,
            config=config, send_event=events,
        )

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            # Spawn teammate
            await tm.spawn("target", "coder", "Work on something")
            # Give it a moment to start
            await asyncio.sleep(0.05)

            # Lead calls shutdown_request tool handler directly
            from agent_service.agent.tools.team_tools import run_shutdown_request
            result = await run_shutdown_request(
                {"teammate": "target"}, bus=bus, tracker=tracker,
            )
            assert "pending" in result

            # Wait for teammate to finish (it should get the shutdown message)
            await asyncio.wait_for(tm._tasks["target"], timeout=5.0)

        statuses = [
            e["status"] for e in events.events
            if e.get("type") == "teammate_status" and e.get("name") == "target"
        ]
        assert "shutdown" in statuses


# ---------------------------------------------------------------------------
# TestPlanApprovalProtocol
# ---------------------------------------------------------------------------


class TestPlanApprovalProtocol:
    """Plan approval roundtrip via ProtocolTracker + MessageBus."""

    async def test_approval_roundtrip(self, tmp_path):
        """Teammate submits plan → lead approves → teammate gets approval."""
        bus = MessageBus()
        tracker = ProtocolTracker()

        # Teammate creates a plan approval request
        req = await tracker.create_request("plan_approval", "builder")
        assert req.status == "pending"

        # Teammate sends the plan to lead via bus
        await bus.send(
            "builder", "lead",
            f"Plan: refactor module X. request_id={req.id}",
            "plan_approval_request",
        )

        # Lead reads inbox
        lead_inbox = await bus.read_inbox("lead")
        assert len(lead_inbox) == 1
        assert "refactor" in lead_inbox[0].content

        # Lead approves via plan_review handler
        from agent_service.agent.tools.team_tools import run_plan_review
        result = await run_plan_review(
            {"request_id": req.id, "approve": True, "feedback": "Looks good"},
            bus=bus, tracker=tracker,
        )
        assert "approved" in result

        # Teammate reads the approval response
        builder_inbox = await bus.read_inbox("builder")
        assert len(builder_inbox) == 1
        assert builder_inbox[0].type == "plan_approval_response"
        assert builder_inbox[0].extra["approve"] is True

        # Tracker status updated
        resolved = await tracker.get(req.id)
        assert resolved.status == "approved"

    async def test_rejection_roundtrip(self, tmp_path):
        """Lead rejects plan → teammate gets rejection."""
        bus = MessageBus()
        tracker = ProtocolTracker()

        req = await tracker.create_request("plan_approval", "builder")
        await bus.send(
            "builder", "lead",
            f"Plan: delete everything. request_id={req.id}",
            "plan_approval_request",
        )

        # Lead rejects
        from agent_service.agent.tools.team_tools import run_plan_review
        result = await run_plan_review(
            {"request_id": req.id, "approve": False, "feedback": "Too dangerous"},
            bus=bus, tracker=tracker,
        )
        assert "rejected" in result

        builder_inbox = await bus.read_inbox("builder")
        assert len(builder_inbox) == 1
        assert builder_inbox[0].extra["approve"] is False
        assert "dangerous" in builder_inbox[0].content.lower() or "Too dangerous" in builder_inbox[0].extra.get("feedback", "")

        resolved = await tracker.get(req.id)
        assert resolved.status == "rejected"


# ---------------------------------------------------------------------------
# TestTeammateIdlePhase
# ---------------------------------------------------------------------------


class TestTeammateIdlePhase:
    """Teammate IDLE phase: resume on inbox, auto-claim, timeout."""

    async def test_resume_on_inbox_message(self, tmp_path):
        """Teammate goes IDLE, receives message → resumes WORK."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        # Turn 1: text-only (done=True → enters IDLE)
        # After resume: text-only (done=True → enters IDLE again → timeout)
        teammate_llm = ScriptedLLMClient([
            _text_response("Initial work done, going idle."),
            # After resume from inbox message:
            _text_response("Processed inbox message, done again."),
        ])
        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm,
        )

        wait_count = 0

        async def inject_wait_for(coro, *, timeout=None):
            nonlocal wait_count
            wait_count += 1
            # On the first IDLE wait, inject a message to trigger the event
            if wait_count == 1:
                await bus.send("lead", "idle_test", "New work for you", "message")
                await asyncio.sleep(0)
            try:
                return await _original_wait_for(coro, timeout=0.001)
            except asyncio.TimeoutError:
                raise

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=inject_wait_for):
            await tm.spawn("idle_test", "coder", "Initial task")
            await _original_wait_for(tm._tasks["idle_test"], timeout=5.0)

        # Should have had at least 2 LLM calls (initial work + resumed work)
        assert len(teammate_llm.calls) >= 2

        statuses = [
            e["status"] for e in events.events
            if e.get("type") == "teammate_status" and e.get("name") == "idle_test"
        ]
        # working → idle → working → idle → shutdown
        assert statuses.count("working") >= 2
        assert statuses.count("idle") >= 1

    async def test_auto_claim_from_task_board(self, tmp_path):
        """Teammate in IDLE auto-claims unclaimed task from task board."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        task_mgr = TaskManager(ws)
        # Create an unclaimed task
        from agent_service.agent.task_manager import Task
        await task_mgr.create(subject="Fix bug #42", description="Fix the login bug")

        # Turn 1: done → IDLE
        # After auto-claim: done → IDLE → timeout
        teammate_llm = ScriptedLLMClient([
            _text_response("Initial work done."),
            # After auto-claim:
            _text_response("Fixed bug #42."),
        ])

        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm, task_manager=task_mgr,
        )

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            await tm.spawn("claimer", "coder", "Waiting for tasks")
            await _original_wait_for(tm._tasks["claimer"], timeout=5.0)

        # Task should now be claimed by "claimer"
        tasks = await task_mgr.list_all()
        assert len(tasks) == 1
        assert tasks[0].owner == "claimer"
        assert tasks[0].status == "in_progress"

        # Teammate should have made at least 2 LLM calls
        assert len(teammate_llm.calls) >= 2

    async def test_idle_timeout_shutdown(self, tmp_path):
        """Teammate in IDLE with no messages/tasks times out and shuts down."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        teammate_llm = ScriptedLLMClient([
            _text_response("Work done, going idle."),
        ])
        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm,
        )

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            await tm.spawn("timeout_test", "coder", "Quick task")
            await _original_wait_for(tm._tasks["timeout_test"], timeout=5.0)

        statuses = [
            e["status"] for e in events.events
            if e.get("type") == "teammate_status" and e.get("name") == "timeout_test"
        ]
        # Should end in shutdown due to idle timeout
        assert statuses[-1] == "shutdown"


# ---------------------------------------------------------------------------
# TestIdentityReinjection
# ---------------------------------------------------------------------------


class TestIdentityReinjection:
    """Identity re-injected when len(messages) <= 3 after auto-claim."""

    async def test_identity_reinjected_on_short_context(self, tmp_path):
        """When context is very short (simulating post-compaction), identity is re-injected."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        task_mgr = TaskManager(ws)
        await task_mgr.create(subject="Deploy v2", description="Deploy the new version")

        # We need the teammate to go IDLE with a very short message history (<=3)
        # Turn 1: done immediately (messages will be [user_prompt, assistant_reply] = 2 entries)
        # In IDLE, auto-claim fires → identity should be re-injected because len(messages)<=3
        teammate_llm = ScriptedLLMClient([
            _text_response("OK."),  # Short response, done=True → IDLE
            _text_response("Deployed v2."),  # After auto-claim with identity
        ])

        bus, tm, tracker, events, config = _make_team_stack(
            ws, teammate_llm=teammate_llm, task_manager=task_mgr,
        )

        with patch("agent_service.agent.teammate_manager.asyncio.wait_for", side_effect=_fast_wait_for):
            await tm.spawn("deployer", "devops", "Stand by for tasks")
            await _original_wait_for(tm._tasks["deployer"], timeout=5.0)

        # The second LLM call should contain the identity injection
        assert len(teammate_llm.calls) >= 2
        second_call_messages = teammate_llm.calls[1]["messages"]
        all_content = json.dumps(second_call_messages)
        assert "<identity>" in all_content
        assert "deployer" in all_content
        assert "devops" in all_content
