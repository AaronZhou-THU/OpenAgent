"""Tests for MCP manager — config parsing, tool registration, env substitution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_service.agent.mcp_manager import (
    MCPManager,
    MCPServerConfig,
    MCPConnection,
    _call_mcp_tool,
    _substitute_env,
)
from agent_service.agent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# _substitute_env
# ---------------------------------------------------------------------------


class TestSubstituteEnv:
    def test_replaces_known_var(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret123")
        assert _substitute_env("token=${MY_KEY}") == "token=secret123"

    def test_leaves_missing_var(self):
        result = _substitute_env("${DOES_NOT_EXIST_XYZ}")
        assert result == "${DOES_NOT_EXIST_XYZ}"

    def test_handles_nested_dict(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        obj = {"url": "http://${HOST}", "nested": {"key": "${HOST}"}}
        result = _substitute_env(obj)
        assert result == {"url": "http://localhost", "nested": {"key": "localhost"}}

    def test_handles_list(self, monkeypatch):
        monkeypatch.setenv("VAL", "abc")
        assert _substitute_env(["${VAL}", "plain"]) == ["abc", "plain"]

    def test_passthrough_non_string(self):
        assert _substitute_env(42) == 42
        assert _substitute_env(None) is None
        assert _substitute_env(True) is True


# ---------------------------------------------------------------------------
# MCPManager.from_config_file
# ---------------------------------------------------------------------------


class TestFromConfigFile:
    def test_missing_file_returns_none(self, tmp_path):
        result = MCPManager.from_config_file(tmp_path / "nonexistent.json")
        assert result is None

    def test_empty_servers_returns_none(self, tmp_path):
        cfg = tmp_path / "mcp.json"
        cfg.write_text(json.dumps({"servers": {}}))
        assert MCPManager.from_config_file(cfg) is None

    def test_invalid_json_returns_none(self, tmp_path):
        cfg = tmp_path / "mcp.json"
        cfg.write_text("not json {{{")
        assert MCPManager.from_config_file(cfg) is None

    def test_parses_stdio_server(self, tmp_path):
        cfg = tmp_path / "mcp.json"
        cfg.write_text(json.dumps({
            "servers": {
                "fs": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@mcp/fs", "/tmp"],
                    "mode": "client",
                }
            }
        }))
        mgr = MCPManager.from_config_file(cfg)
        assert mgr is not None
        assert "fs" in mgr._configs
        assert mgr._configs["fs"].transport == "stdio"
        assert mgr._configs["fs"].command == "npx"
        assert mgr._configs["fs"].args == ["-y", "@mcp/fs", "/tmp"]
        assert mgr._configs["fs"].mode == "client"

    def test_parses_remote_server_with_auth(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRAVE_KEY", "sk-test")
        cfg = tmp_path / "mcp.json"
        cfg.write_text(json.dumps({
            "servers": {
                "brave": {
                    "transport": "http",
                    "url": "https://mcp.brave.com/search",
                    "authorization_token": "${BRAVE_KEY}",
                    "mode": "remote",
                }
            }
        }))
        mgr = MCPManager.from_config_file(cfg)
        assert mgr is not None
        assert mgr._configs["brave"].authorization_token == "sk-test"
        assert mgr._configs["brave"].headers["Authorization"] == "Bearer sk-test"
        assert mgr.has_remote_servers()

    def test_defaults_mode_to_client(self, tmp_path):
        cfg = tmp_path / "mcp.json"
        cfg.write_text(json.dumps({
            "servers": {
                "test": {"transport": "stdio", "command": "echo"}
            }
        }))
        mgr = MCPManager.from_config_file(cfg)
        assert mgr is not None
        assert mgr._configs["test"].mode == "client"


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


class TestRegisterTools:
    def test_injects_tools_into_registry(self):
        cfg = MCPServerConfig(name="fs", transport="stdio", mode="client")
        conn = MCPConnection(
            config=cfg,
            session=MagicMock(),
            tools=[
                {
                    "name": "mcp__fs__read",
                    "description": "Read a file",
                    "input_schema": {"type": "object"},
                },
                {
                    "name": "mcp__fs__write",
                    "description": "Write a file",
                    "input_schema": {"type": "object"},
                },
            ],
        )
        mgr = MCPManager({})
        mgr._connections["fs"] = conn

        registry = ToolRegistry()
        mgr.register_tools(registry)

        assert registry.has("mcp__fs__read")
        assert registry.has("mcp__fs__write")
        names = registry.get_names()
        assert "mcp__fs__read" in names
        assert "mcp__fs__write" in names

    def test_tool_definitions_included(self):
        cfg = MCPServerConfig(name="s", transport="stdio", mode="client")
        conn = MCPConnection(
            config=cfg,
            session=MagicMock(),
            tools=[
                {
                    "name": "mcp__s__tool1",
                    "description": "Tool 1",
                    "input_schema": {"type": "object"},
                },
            ],
        )
        mgr = MCPManager({})
        mgr._connections["s"] = conn

        registry = ToolRegistry()
        mgr.register_tools(registry)

        defs = registry.get_definitions()
        assert len(defs) == 1
        assert defs[0]["name"] == "mcp__s__tool1"


# ---------------------------------------------------------------------------
# _call_mcp_tool
# ---------------------------------------------------------------------------


class TestCallMcpTool:
    @pytest.mark.asyncio
    async def test_success(self):
        block = MagicMock()
        block.text = "hello world"
        result_obj = MagicMock()
        result_obj.content = [block]

        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=result_obj)

        result = await _call_mcp_tool(
            {"path": "/tmp"}, session=session, tool_name="read"
        )
        assert result == "hello world"
        session.call_tool.assert_called_once_with("read", arguments={"path": "/tmp"})

    @pytest.mark.asyncio
    async def test_error_returns_message(self):
        session = AsyncMock()
        session.call_tool = AsyncMock(side_effect=RuntimeError("connection lost"))

        result = await _call_mcp_tool(
            {}, session=session, tool_name="broken"
        )
        assert "MCP tool error" in result
        assert "connection lost" in result

    @pytest.mark.asyncio
    async def test_empty_result(self):
        result_obj = MagicMock()
        result_obj.content = []

        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=result_obj)

        result = await _call_mcp_tool(
            {}, session=session, tool_name="empty"
        )
        assert result == "(empty result)"

    @pytest.mark.asyncio
    async def test_multiple_content_blocks(self):
        block1 = MagicMock()
        block1.text = "line1"
        block2 = MagicMock()
        block2.text = "line2"
        result_obj = MagicMock()
        result_obj.content = [block1, block2]

        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=result_obj)

        result = await _call_mcp_tool(
            {}, session=session, tool_name="multi"
        )
        assert result == "line1\nline2"


# ---------------------------------------------------------------------------
# get_remote_server_params
# ---------------------------------------------------------------------------


class TestGetRemoteServerParams:
    def test_builds_params(self):
        cfg = MCPServerConfig(
            name="brave",
            transport="http",
            mode="remote",
            url="https://mcp.brave.com/search",
            authorization_token="sk-test",
        )
        mgr = MCPManager({"brave": cfg})
        params = mgr.get_remote_server_params()

        assert len(params) == 1
        assert params[0]["type"] == "url"
        assert params[0]["url"] == "https://mcp.brave.com/search"
        assert params[0]["name"] == "brave"
        assert params[0]["authorization_token"] == "sk-test"

    def test_empty_when_no_remote(self):
        cfg = MCPServerConfig(name="fs", transport="stdio", mode="client")
        mgr = MCPManager({"fs": cfg})
        assert mgr.get_remote_server_params() == []
        assert not mgr.has_remote_servers()

    def test_skips_auth_when_empty(self):
        cfg = MCPServerConfig(
            name="pub",
            transport="http",
            mode="remote",
            url="https://public.mcp.example.com",
        )
        mgr = MCPManager({"pub": cfg})
        params = mgr.get_remote_server_params()
        assert "authorization_token" not in params[0]


# ---------------------------------------------------------------------------
# get_tool_info / get_tool_names / get_tool_descriptions
# ---------------------------------------------------------------------------


class TestToolInfo:
    def _make_manager_with_connection(self):
        cfg = MCPServerConfig(name="s", transport="stdio", mode="client")
        conn = MCPConnection(
            config=cfg,
            session=MagicMock(),
            tools=[
                {"name": "mcp__s__foo", "description": "Do foo"},
                {"name": "mcp__s__bar", "description": "Do bar"},
            ],
        )
        mgr = MCPManager({})
        mgr._connections["s"] = conn
        return mgr

    def test_get_tool_names(self):
        mgr = self._make_manager_with_connection()
        names = mgr.get_tool_names()
        assert names == ["mcp__s__foo", "mcp__s__bar"]

    def test_get_tool_info(self):
        mgr = self._make_manager_with_connection()
        info = mgr.get_tool_info()
        assert len(info) == 2
        assert info[0] == {"name": "mcp__s__foo", "description": "Do foo"}

    def test_get_tool_descriptions(self):
        mgr = self._make_manager_with_connection()
        desc = mgr.get_tool_descriptions()
        assert "mcp__s__foo: Do foo" in desc
        assert "mcp__s__bar: Do bar" in desc
