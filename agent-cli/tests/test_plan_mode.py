"""Integration tests for CLI plan mode approval flow.

Mocks agent_loop to simulate the backend and verifies that the CLI
correctly handles plan approval, rejection, and feedback.
"""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**overrides) -> SimpleNamespace:
    """Build a minimal args namespace matching what _build_parser produces."""
    defaults = dict(
        preset="coding",
        workspace=None,
        model=None,
        no_memory=True,
        no_approval=True,
        max_turns=None,
        teams=False,
        plan=False,
        resume=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class EventCollector:
    """Collects send_event calls for assertions."""

    def __init__(self):
        self.events: list[dict] = []

    async def __call__(self, event: dict) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.get("type", "") for e in self.events]

    def of_type(self, etype: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == etype]


def _plan_result(plan_mode: bool = True) -> dict:
    return {
        "input_tokens": 500,
        "output_tokens": 200,
        "last_input_tokens": 500,
        "plan_mode": plan_mode,
    }


def _exec_result() -> dict:
    return {
        "input_tokens": 1000,
        "output_tokens": 400,
        "last_input_tokens": 1000,
        "plan_mode": False,
    }


def _make_prompt_session(responses: list[str]):
    """Build a mock PromptSession that yields responses in order, then EOFError."""
    it = iter(responses)

    async def prompt_async(message=None):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    mock = MagicMock()
    mock.prompt_async = prompt_async
    return mock


# Context manager that patches everything run_repl needs so only the
# agent_loop and user input are faked.
#
# Patched at source modules because run_repl does late imports.

def _repl_patches(fake_agent_loop, prompt_session, events: EventCollector):
    """Return a combined context manager with all patches needed."""
    import contextlib

    @contextlib.asynccontextmanager
    async def ctx():
        with (
            # Make stdin look interactive so we enter the REPL path
            patch("sys.stdin") as mock_stdin,
            # agent_loop — the core function under test
            patch(
                "agent_service.agent.loop.agent_loop",
                side_effect=fake_agent_loop,
            ),
            # Renderer — return our event collector
            patch(
                "agent_cli.renderer.make_send_event",
                return_value=events,
            ),
            # Prompt session — return our scripted inputs
            patch(
                "agent_cli.input.create_session",
                return_value=prompt_session,
            ),
            # Suppress console output to keep test logs clean
            patch("agent_cli.app.console"),
        ):
            mock_stdin.isatty.return_value = True
            yield

    return ctx()


async def _run(args, fake_agent_loop, responses: list[str], events: EventCollector):
    """Helper to run run_repl with the given fake loop and user inputs."""
    prompt_session = _make_prompt_session(responses)

    async with _repl_patches(fake_agent_loop, prompt_session, events):
        from agent_cli.app import run_repl
        await run_repl(args)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPlanApproval:
    """Approving a plan injects execution message and re-runs agent_loop."""

    async def test_approve_injects_message_and_reruns(self, tmp_path):
        call_count = 0
        events = EventCollector()

        async def fake_loop(*, messages, plan_mode, send_event, **kw):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # Plan phase
                assert plan_mode is True
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan: Refactor auth"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan: Refactor auth"})
                return _plan_result()

            elif call_count == 2:
                # Execution phase — plan_mode should now be False
                assert plan_mode is False
                last_user = [m for m in messages if m["role"] == "user"][-1]
                assert "Plan approved" in last_user["content"]
                assert "execute" in last_user["content"].lower()
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Done."}],
                })
                return _exec_result()

            raise AssertionError("agent_loop called too many times")

        args = _make_args(plan=True, workspace=str(tmp_path / "ws"))
        await _run(args, fake_loop, [
            "refactor the auth module",  # user message
            "a",                          # approve plan
        ], events)

        assert call_count == 2
        assert "plan_approved" in events.types()
        assert "plan_mode_changed" in events.types()
        mode_events = events.of_type("plan_mode_changed")
        assert any(e.get("enabled") is False for e in mode_events)


class TestPlanFeedback:
    """Feedback re-runs agent in plan mode with rejection message."""

    async def test_feedback_reruns_in_plan_mode(self, tmp_path):
        call_count = 0
        events = EventCollector()

        async def fake_loop(*, messages, plan_mode, send_event, **kw):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                assert plan_mode is True
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan: v1"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan: v1"})
                return _plan_result()

            elif call_count == 2:
                # After feedback — still plan mode
                assert plan_mode is True
                last_user = [m for m in messages if m["role"] == "user"][-1]
                assert "rejected" in last_user["content"].lower()
                assert "add error handling" in last_user["content"].lower()
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan: v2"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan: v2"})
                return _plan_result()

            elif call_count == 3:
                assert plan_mode is False
                return _exec_result()

            raise AssertionError("Too many calls")

        args = _make_args(plan=True, workspace=str(tmp_path / "ws"))
        await _run(args, fake_loop, [
            "build it",          # user message
            "f",                 # choose feedback
            "add error handling",  # feedback text
            "a",                 # approve revised plan
        ], events)

        assert call_count == 3
        rejected = events.of_type("plan_rejected")
        assert len(rejected) >= 1
        assert rejected[0].get("feedback") == "add error handling"
        assert "plan_approved" in events.types()


class TestPlanRejection:
    """Rejection without feedback stays in plan mode; user types new message."""

    async def test_reject_stays_in_plan_mode(self, tmp_path):
        call_count = 0
        events = EventCollector()

        async def fake_loop(*, messages, plan_mode, send_event, **kw):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                assert plan_mode is True
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan: bad"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan: bad"})
                return _plan_result()

            elif call_count == 2:
                # User rejected and typed a new message
                assert plan_mode is True
                last_user = [m for m in messages if m["role"] == "user"][-1]
                assert last_user["content"] == "try a different approach"
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan: better"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan: better"})
                return _plan_result()

            elif call_count == 3:
                assert plan_mode is False
                return _exec_result()

            raise AssertionError("Too many calls")

        args = _make_args(plan=True, workspace=str(tmp_path / "ws"))
        await _run(args, fake_loop, [
            "build it",                # user message
            "r",                       # reject
            "try a different approach", # new message (normal prompt)
            "a",                       # approve
        ], events)

        assert call_count == 3
        rejected = events.of_type("plan_rejected")
        assert len(rejected) >= 1


class TestPlanReadyGating:
    """Approval prompt only appears when plan_ready event was emitted."""

    async def test_no_approval_prompt_without_plan_ready(self, tmp_path):
        """If agent returns in plan mode but didn't emit plan_ready,
        user should get the normal > prompt, not plan>."""
        call_count = 0
        events = EventCollector()

        async def fake_loop(*, messages, plan_mode, send_event, **kw):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # Agent exploring — no plan_ready
                assert plan_mode is True
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Still exploring..."}],
                })
                return _plan_result()

            elif call_count == 2:
                # Agent finishes plan
                assert plan_mode is True
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan: done"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan: done"})
                return _plan_result()

            elif call_count == 3:
                assert plan_mode is False
                return _exec_result()

            raise AssertionError("Too many calls")

        args = _make_args(plan=True, workspace=str(tmp_path / "ws"))
        await _run(args, fake_loop, [
            "explore codebase",  # first message → no plan_ready → normal prompt
            "now make plan",     # second message → plan_ready → plan prompt
            "a",                 # approve
        ], events)

        assert call_count == 3
        # plan_approved emitted exactly once
        assert events.types().count("plan_approved") == 1


class TestPlanModeAgentInitiated:
    """Agent calls enter_plan_mode mid-loop (not started with --plan)."""

    async def test_agent_enters_plan_mode(self, tmp_path):
        call_count = 0
        events = EventCollector()

        async def fake_loop(*, messages, plan_mode, send_event, **kw):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # Agent decides to plan on its own
                assert plan_mode is False
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Complex task. Planning..."}],
                })
                await send_event({"type": "plan_mode_changed", "enabled": True})
                await send_event({"type": "plan_ready", "plan": "## Plan: complex"})
                return _plan_result(plan_mode=True)

            elif call_count == 2:
                assert plan_mode is False  # approved → execution
                return _exec_result()

            raise AssertionError("Too many calls")

        args = _make_args(plan=False, workspace=str(tmp_path / "ws"))
        await _run(args, fake_loop, [
            "do something complex",
            "a",
        ], events)

        assert call_count == 2
        assert "plan_approved" in events.types()


class TestPlanEmptyFeedbackSkipped:
    """Empty feedback (just Enter) returns to normal prompt without re-running."""

    async def test_empty_feedback_returns_to_prompt(self, tmp_path):
        call_count = 0
        events = EventCollector()

        async def fake_loop(*, messages, plan_mode, send_event, **kw):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan: v1"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan: v1"})
                return _plan_result()

            elif call_count == 2:
                # After empty feedback → user typed new message (normal prompt)
                assert plan_mode is True
                last_user = [m for m in messages if m["role"] == "user"][-1]
                assert last_user["content"] == "ok try again"
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan: v2"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan: v2"})
                return _plan_result()

            elif call_count == 3:
                assert plan_mode is False
                return _exec_result()

            raise AssertionError("Too many calls")

        args = _make_args(plan=True, workspace=str(tmp_path / "ws"))
        await _run(args, fake_loop, [
            "build it",
            "f",            # choose feedback
            "",             # empty → skipped
            "ok try again", # new message via normal prompt
            "a",            # approve
        ], events)

        assert call_count == 3
        # No plan_rejected with feedback content
        rejected_with_fb = [
            e for e in events.of_type("plan_rejected") if e.get("feedback")
        ]
        assert len(rejected_with_fb) == 0


class TestPlanCtrlCDefaultsToReject:
    """Ctrl+C (KeyboardInterrupt) during plan prompt defaults to reject."""

    async def test_ctrl_c_rejects(self, tmp_path):
        call_count = 0
        events = EventCollector()

        async def fake_loop(*, messages, plan_mode, send_event, **kw):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan"})
                return _plan_result()

            elif call_count == 2:
                assert plan_mode is True
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": "## Plan v2"}],
                })
                await send_event({"type": "plan_ready", "plan": "## Plan v2"})
                return _plan_result()

            elif call_count == 3:
                assert plan_mode is False
                return _exec_result()

            raise AssertionError("Too many calls")

        responses = ["start planning"]
        prompt_call = 0

        async def fake_prompt_async(message=None):
            nonlocal prompt_call
            prompt_call += 1
            if prompt_call == 1:
                return "start planning"  # initial message
            elif prompt_call == 2:
                raise KeyboardInterrupt  # Ctrl+C at plan prompt → reject
            elif prompt_call == 3:
                return "try again"  # new message after reject
            elif prompt_call == 4:
                return "a"  # approve
            raise EOFError

        mock_ps = MagicMock()
        mock_ps.prompt_async = fake_prompt_async

        import contextlib

        @contextlib.asynccontextmanager
        async def ctx():
            with (
                patch("sys.stdin") as mock_stdin,
                patch("agent_service.agent.loop.agent_loop", side_effect=fake_loop),
                patch("agent_cli.renderer.make_send_event", return_value=events),
                patch("agent_cli.input.create_session", return_value=mock_ps),
                patch("agent_cli.app.console"),
            ):
                mock_stdin.isatty.return_value = True
                yield

        async with ctx():
            from agent_cli.app import run_repl
            args = _make_args(plan=True, workspace=str(tmp_path / "ws"))
            await run_repl(args)

        assert call_count == 3
        rejected = events.of_type("plan_rejected")
        assert len(rejected) >= 1
