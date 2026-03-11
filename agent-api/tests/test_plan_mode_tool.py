"""Unit tests for plan_mode_tool — sentinel values, definitions, handlers."""

from __future__ import annotations

import pytest

from agent_service.agent.tools.plan_mode_tool import (
    ENTER_PLAN_SENTINEL,
    EXIT_PLAN_SENTINEL,
    ENTER_DEFINITION,
    EXIT_DEFINITION,
    run_enter_plan_mode,
    run_exit_plan_mode,
)


class TestSentinelValues:
    def test_enter_sentinel_is_string(self):
        assert isinstance(ENTER_PLAN_SENTINEL, str)
        assert ENTER_PLAN_SENTINEL == "__ENTER_PLAN_MODE__"

    def test_exit_sentinel_is_string(self):
        assert isinstance(EXIT_PLAN_SENTINEL, str)
        assert EXIT_PLAN_SENTINEL == "__PLAN_READY__"

    def test_sentinels_are_distinct(self):
        assert ENTER_PLAN_SENTINEL != EXIT_PLAN_SENTINEL


class TestDefinitions:
    def test_enter_definition_structure(self):
        assert ENTER_DEFINITION["name"] == "enter_plan_mode"
        assert "description" in ENTER_DEFINITION
        assert "input_schema" in ENTER_DEFINITION
        assert ENTER_DEFINITION["input_schema"]["type"] == "object"

    def test_exit_definition_structure(self):
        assert EXIT_DEFINITION["name"] == "exit_plan_mode"
        assert "description" in EXIT_DEFINITION
        assert "input_schema" in EXIT_DEFINITION
        assert EXIT_DEFINITION["input_schema"]["type"] == "object"

    def test_enter_description_mentions_plan_mode(self):
        assert "plan mode" in ENTER_DEFINITION["description"].lower()

    def test_exit_description_mentions_approval(self):
        assert "approval" in EXIT_DEFINITION["description"].lower()


class TestHandlers:
    async def test_enter_returns_sentinel(self):
        result = await run_enter_plan_mode({})
        assert result == ENTER_PLAN_SENTINEL

    async def test_exit_returns_sentinel(self):
        result = await run_exit_plan_mode({})
        assert result == EXIT_PLAN_SENTINEL

    async def test_enter_ignores_args(self):
        result = await run_enter_plan_mode({"extra": "value"})
        assert result == ENTER_PLAN_SENTINEL

    async def test_exit_ignores_args(self):
        result = await run_exit_plan_mode({"extra": "value"})
        assert result == EXIT_PLAN_SENTINEL
