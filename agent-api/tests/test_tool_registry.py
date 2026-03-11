"""Tests for agent_service.agent.tools.registry.ToolRegistry."""

from __future__ import annotations

import pytest

from agent_service.agent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DUMMY_DEFINITION = {
    "name": "greet",
    "description": "Says hello",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
}


async def _greet_handler(args: dict) -> str:
    return f"Hello, {args['name']}!"


async def _fail_handler(args: dict) -> str:
    raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_register_and_execute():
    reg = ToolRegistry()
    reg.register("greet", DUMMY_DEFINITION, _greet_handler)
    result = await reg.execute("greet", {"name": "World"})
    assert result == "Hello, World!"


async def test_execute_unknown_tool():
    reg = ToolRegistry()
    result = await reg.execute("nonexistent", {})
    assert "Unknown tool" in result


async def test_get_definitions_returns_registered():
    reg = ToolRegistry()
    reg.register("greet", DUMMY_DEFINITION, _greet_handler)
    defs = reg.get_definitions()
    assert len(defs) == 1
    assert defs[0]["name"] == "greet"


async def test_get_definitions_exclude():
    reg = ToolRegistry()
    reg.register("greet", DUMMY_DEFINITION, _greet_handler)
    other_def = {**DUMMY_DEFINITION, "name": "farewell"}
    reg.register("farewell", other_def, _greet_handler)

    defs = reg.get_definitions(exclude={"greet"})
    assert len(defs) == 1
    assert defs[0]["name"] == "farewell"


async def test_has():
    reg = ToolRegistry()
    assert not reg.has("greet")
    reg.register("greet", DUMMY_DEFINITION, _greet_handler)
    assert reg.has("greet")


async def test_get_names():
    reg = ToolRegistry()
    reg.register("greet", DUMMY_DEFINITION, _greet_handler)
    reg.register("farewell", {**DUMMY_DEFINITION, "name": "farewell"}, _greet_handler)
    names = reg.get_names()
    assert set(names) == {"greet", "farewell"}


async def test_execute_handles_exception():
    reg = ToolRegistry()
    reg.register("fail", DUMMY_DEFINITION, _fail_handler)
    result = await reg.execute("fail", {})
    assert "Error" in result
    assert "boom" in result
