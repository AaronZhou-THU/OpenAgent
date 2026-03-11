"""Pluggable ToolRegistry — register name, JSON-schema definition, and async handler."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    definition: dict[str, Any]
    handler: Callable[..., Awaitable[str]]


class ToolRegistry:
    """
    Central registry for agent tools.

    Tools are registered with:
    - name: unique identifier
    - definition: Anthropic tool JSON schema
    - handler: async callable(args: dict) -> str
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        definition: dict[str, Any],
        handler: Callable[..., Awaitable[str]],
    ) -> None:
        self._tools[name] = ToolSpec(definition=definition, handler=handler)

    def get_definitions(self, exclude: set[str] | None = None) -> list[dict]:
        exclude = exclude or set()
        return [
            spec.definition
            for name, spec in self._tools.items()
            if name not in exclude
        ]

    def get_names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, args: dict) -> str:
        if name not in self._tools:
            return f"Unknown tool: {name}"
        try:
            return await self._tools[name].handler(args)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.exception("Tool '%s' failed", name)
            return f"Error: {e}"

    def has(self, name: str) -> bool:
        return name in self._tools
