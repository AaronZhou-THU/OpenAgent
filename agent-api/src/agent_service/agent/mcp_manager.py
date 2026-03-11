"""MCP (Model Context Protocol) server management.

Manages connections to external MCP servers, exposing their tools to the
agent via the ToolRegistry (client-mode) or the Anthropic beta API
(remote-mode).

Follows the SkillLoader pattern: created at startup, injected where needed.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_service.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Regex for ${VAR} environment variable substitution
_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _substitute_env(obj: Any) -> Any:
    """Recursively replace ``${VAR}`` placeholders with environment values.

    Missing environment variables are left as-is (``${MISSING}``).
    Works on strings, dicts, and lists.
    """
    if isinstance(obj, str):
        return _ENV_RE.sub(
            lambda m: os.environ.get(m.group(1), m.group(0)), obj
        )
    if isinstance(obj, dict):
        return {k: _substitute_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_env(v) for v in obj]
    return obj


@dataclass
class MCPServerConfig:
    """Parsed configuration for a single MCP server."""

    name: str
    transport: str  # "stdio" or "http"
    mode: str  # "client" or "remote"

    # stdio transport
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    # http transport
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    authorization_token: str = ""


@dataclass
class MCPConnection:
    """Live connection to a client-mode MCP server."""

    config: MCPServerConfig
    session: Any = None  # mcp.ClientSession
    tools: list[dict] = field(default_factory=list)
    # Context managers for cleanup
    _cm_stack: list[Any] = field(default_factory=list)


class MCPManager:
    """Manages MCP server connections and tool registration.

    Client-mode servers: connected via mcp SDK, tools injected into ToolRegistry.
    Remote-mode servers: params passed to Anthropic beta API.
    """

    def __init__(self, configs: dict[str, MCPServerConfig]) -> None:
        self._configs = configs
        self._connections: dict[str, MCPConnection] = {}
        self._remote_configs: dict[str, MCPServerConfig] = {}

        for name, cfg in configs.items():
            if cfg.mode == "remote":
                self._remote_configs[name] = cfg

    @classmethod
    def from_config_file(cls, path: str | Path) -> MCPManager | None:
        """Load MCP config from a JSON file. Returns None if missing/empty."""
        p = Path(path)
        if not p.exists():
            logger.debug("MCP config file not found: %s", p)
            return None

        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to parse MCP config %s: %s", p, e)
            return None

        servers_raw = data.get("servers", {})
        if not servers_raw:
            return None

        # Substitute env vars in the entire config
        servers_raw = _substitute_env(servers_raw)

        configs: dict[str, MCPServerConfig] = {}
        for name, raw in servers_raw.items():
            transport = raw.get("transport", "stdio")
            mode = raw.get("mode", "client")
            headers = raw.get("headers", {})
            auth_token = raw.get("authorization_token", "")
            if auth_token and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {auth_token}"

            configs[name] = MCPServerConfig(
                name=name,
                transport=transport,
                mode=mode,
                command=raw.get("command", ""),
                args=raw.get("args", []),
                env=raw.get("env", {}),
                url=raw.get("url", ""),
                headers=headers,
                authorization_token=auth_token,
            )

        return cls(configs)

    async def connect_all(self) -> None:
        """Connect to all client-mode MCP servers."""
        for name, cfg in self._configs.items():
            if cfg.mode != "client":
                continue
            try:
                conn = await self._connect_server(cfg)
                self._connections[name] = conn
                logger.info(
                    "MCP server '%s' connected (%d tools)",
                    name,
                    len(conn.tools),
                )
            except Exception as e:
                logger.error("Failed to connect MCP server '%s': %s", name, e)

    async def _connect_server(self, cfg: MCPServerConfig) -> MCPConnection:
        """Establish a connection to a single client-mode MCP server."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client, StdioServerParameters

        conn = MCPConnection(config=cfg)

        if cfg.transport == "stdio":
            server_params = StdioServerParameters(
                command=cfg.command,
                args=cfg.args,
                env=cfg.env if cfg.env else None,
            )
            cm = stdio_client(server_params)
            read_stream, write_stream = await cm.__aenter__()
            conn._cm_stack.append(cm)

            session = ClientSession(read_stream, write_stream)
            session_cm = session
            await session_cm.__aenter__()
            conn._cm_stack.append(session_cm)
            conn.session = session
        elif cfg.transport == "http":
            from mcp.client.streamable_http import streamablehttp_client

            cm = streamablehttp_client(cfg.url, headers=cfg.headers)
            read_stream, write_stream, _ = await cm.__aenter__()
            conn._cm_stack.append(cm)

            session = ClientSession(read_stream, write_stream)
            session_cm = session
            await session_cm.__aenter__()
            conn._cm_stack.append(session_cm)
            conn.session = session
        else:
            raise ValueError(f"Unknown transport: {cfg.transport}")

        # Initialize and list tools
        await conn.session.initialize()
        result = await conn.session.list_tools()
        conn.tools = [
            {
                "name": f"mcp__{cfg.name}__{t.name}",
                "description": t.description or "",
                "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
            }
            for t in result.tools
        ]
        return conn

    async def disconnect_all(self) -> None:
        """Disconnect all client-mode MCP servers."""
        for name, conn in list(self._connections.items()):
            for cm in reversed(conn._cm_stack):
                try:
                    await cm.__aexit__(None, None, None)
                except Exception as e:
                    logger.debug("Error closing MCP '%s': %s", name, e)
            logger.info("MCP server '%s' disconnected", name)
        self._connections.clear()

    def register_tools(self, registry: ToolRegistry) -> None:
        """Inject client-mode MCP tools into a ToolRegistry."""
        from functools import partial

        for name, conn in self._connections.items():
            for tool_def in conn.tools:
                tool_name = tool_def["name"]
                # Extract the original MCP tool name (after mcp__{server}__)
                original_name = tool_name.split("__", 2)[2] if "__" in tool_name else tool_name
                registry.register(
                    tool_name,
                    tool_def,
                    partial(
                        _call_mcp_tool,
                        session=conn.session,
                        tool_name=original_name,
                    ),
                )

    def get_remote_server_params(self) -> list[dict]:
        """Build Anthropic API mcp_servers parameter for remote-mode servers."""
        params = []
        for name, cfg in self._remote_configs.items():
            entry: dict[str, Any] = {
                "type": "url",
                "url": cfg.url,
                "name": name,
            }
            if cfg.authorization_token:
                entry["authorization_token"] = cfg.authorization_token
            params.append(entry)
        return params

    def has_remote_servers(self) -> bool:
        return bool(self._remote_configs)

    def get_tool_names(self) -> list[str]:
        """Return names of all client-mode MCP tools."""
        names: list[str] = []
        for conn in self._connections.values():
            names.extend(t["name"] for t in conn.tools)
        return names

    def get_tool_info(self) -> list[dict]:
        """Return tool info dicts for the GET /api/tools endpoint."""
        info: list[dict] = []
        for conn in self._connections.values():
            for tool_def in conn.tools:
                info.append({
                    "name": tool_def["name"],
                    "description": tool_def.get("description", ""),
                })
        return info

    def get_tool_descriptions(self) -> str:
        """Return a formatted string of MCP tool descriptions for system prompt."""
        lines: list[str] = []
        for conn in self._connections.values():
            for tool_def in conn.tools:
                desc = tool_def.get("description", "No description")
                lines.append(f"- {tool_def['name']}: {desc}")
        return "\n".join(lines)


async def _call_mcp_tool(
    args: dict,
    *,
    session: Any,
    tool_name: str,
) -> str:
    """Call an MCP tool and extract text from the result."""
    try:
        result = await session.call_tool(tool_name, arguments=args)
    except Exception as e:
        return f"MCP tool error: {e}"

    # Extract text from content blocks
    parts: list[str] = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        elif hasattr(block, "model_dump"):
            d = block.model_dump()
            parts.append(d.get("text", str(d)))
        else:
            parts.append(str(block))

    return "\n".join(parts) if parts else "(empty result)"
