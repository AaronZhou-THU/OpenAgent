"""Tests for agent_cli.commands — slash command dispatch and handlers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_cli.commands import CommandContext, CommandResult, dispatch, get_commands
from agent_cli.config import CLIConfig
from agent_cli.cost import CostTracker
from agent_cli.session import SessionStore


@pytest.fixture
def store(tmp_path) -> SessionStore:
    return SessionStore(tmp_path / "conversations")


@pytest.fixture
def ctx(tmp_path, store) -> CommandContext:
    config = CLIConfig(agent_dir=tmp_path / ".agent")
    config.agent_dir.mkdir(parents=True, exist_ok=True)
    ct = CostTracker("claude-sonnet-4-5-20250929")
    meta = store.create(preset="coding", model="claude-sonnet-4-5-20250929")
    return CommandContext(
        config=config,
        cost_tracker=ct,
        session_store=store,
        session_id=meta.id,
        model="claude-sonnet-4-5-20250929",
        preset="coding",
        thinking_enabled=False,
        thinking_effort="high",
    )


class TestDispatch:
    """Test command dispatch logic."""

    async def test_non_command_returns_none(self, ctx):
        result = await dispatch("hello world", ctx)
        assert result is None

    async def test_unknown_command(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/unknown", ctx)
        assert result is not None
        assert result.handled is True

    async def test_help_command(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/help", ctx)
        assert result.handled is True
        assert result.quit is False

    async def test_quit_command(self, ctx):
        result = await dispatch("/quit", ctx)
        assert result.quit is True

    async def test_exit_command(self, ctx):
        result = await dispatch("/exit", ctx)
        assert result.quit is True

    async def test_clear_command(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/clear", ctx)
        assert result.clear is True
        assert result.new_session_id is not None

    async def test_compact_command(self, ctx):
        result = await dispatch("/compact", ctx)
        assert result.compact is True

    async def test_cost_command(self, ctx):
        ctx.cost_tracker.add(5000, 1000)
        with patch("agent_cli.commands.console"):
            result = await dispatch("/cost", ctx)
        assert result.handled is True

    async def test_model_no_args_shows_current(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/model", ctx)
        assert result.handled is True

    async def test_model_with_arg_switches(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/model claude-opus-4-6", ctx)
        assert hasattr(result, "_new_model")
        assert result._new_model == "claude-opus-4-6"


class TestGetCommands:
    """Test command registry."""

    def test_has_help(self):
        cmds = get_commands()
        assert "help" in cmds

    def test_has_quit(self):
        cmds = get_commands()
        assert "quit" in cmds

    def test_has_all_expected_commands(self):
        cmds = get_commands()
        expected = {
            "help",
            "clear",
            "compact",
            "model",
            "history",
            "resume",
            "cost",
            "quit",
            "exit",
            "thinking",
        }
        assert expected.issubset(set(cmds.keys()))


class TestHistoryCommand:
    """Test /history command."""

    async def test_history_empty(self, ctx):
        # Clear any sessions created by fixture
        with patch("agent_cli.commands.console"):
            result = await dispatch("/history", ctx)
        assert result.handled is True

    async def test_history_with_sessions(self, ctx, store):
        store.create(preset="coding", model="m1")
        store.create(preset="work", model="m2")
        with patch("agent_cli.commands.console"):
            result = await dispatch("/history", ctx)
        assert result.handled is True


class TestResumeCommand:
    """Test /resume command."""

    async def test_resume_no_sessions(self, tmp_path):
        empty_store = SessionStore(tmp_path / "empty_convos")
        config = CLIConfig(agent_dir=tmp_path / ".agent")
        ct = CostTracker("m")
        empty_ctx = CommandContext(
            config=config,
            cost_tracker=ct,
            session_store=empty_store,
            session_id="x",
            model="m",
            preset="coding",
            thinking_enabled=False,
            thinking_effort="high",
        )
        with patch("agent_cli.commands.console"):
            result = await dispatch("/resume", empty_ctx)
        assert result.handled is True
        assert result.new_session_id is None

    async def test_resume_with_id(self, ctx, store):
        meta = store.create(preset="coding", model="m")
        with patch("agent_cli.commands.console"):
            result = await dispatch(f"/resume {meta.id}", ctx)
        assert result.new_session_id == meta.id

    async def test_resume_nonexistent_id(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/resume nonexistent", ctx)
        assert result.new_session_id is None


class TestTeamsCommand:
    """Test /teams command."""

    async def test_teams_on(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/teams on", ctx)
        assert result.teams is True

    async def test_teams_off(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/teams off", ctx)
        assert result.teams is False

    async def test_teams_no_args_shows_usage(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/teams", ctx)
        assert result.teams is None

    async def test_teams_invalid_arg_shows_usage(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/teams maybe", ctx)
        assert result.teams is None


class TestApprovalCommand:
    """Test /approval command."""

    async def test_approval_on(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/approval on", ctx)
        assert result.approval is True

    async def test_approval_off(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/approval off", ctx)
        assert result.approval is False

    async def test_approval_no_args_shows_usage(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/approval", ctx)
        assert result.approval is None

    async def test_approval_invalid_arg_shows_usage(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/approval yes", ctx)
        assert result.approval is None


class TestThinkingCommand:
    """Test /thinking command."""

    async def test_thinking_no_args_shows_current(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/thinking", ctx)
        assert result.thinking is None
        assert result.thinking_effort is None

    async def test_thinking_on(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/thinking on", ctx)
        assert result.thinking is True
        assert result.thinking_effort is None

    async def test_thinking_off(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/thinking off", ctx)
        assert result.thinking is False
        assert result.thinking_effort is None

    async def test_thinking_high_sets_level_and_enables(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/thinking high", ctx)
        assert result.thinking is True
        assert result.thinking_effort == "high"

    async def test_thinking_max_sets_level_and_enables(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/thinking max", ctx)
        assert result.thinking is True
        assert result.thinking_effort == "max"

    async def test_thinking_invalid_arg_shows_usage(self, ctx):
        with patch("agent_cli.commands.console"):
            result = await dispatch("/thinking medium", ctx)
        assert result.thinking is None
        assert result.thinking_effort is None
