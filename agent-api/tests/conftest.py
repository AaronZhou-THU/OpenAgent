"""Shared fixtures for agent-service tests."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

from agent_service.agent.llm import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# Workspace fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Return a temporary workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Fake LLM client that returns a fixed LLMResponse.

    Attributes:
        calls: list of keyword-argument dicts from each ``create()`` call.
        response: the LLMResponse to return (override per-test if needed).
    """

    def __init__(self, response: LLMResponse | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = response or LLMResponse(
            content=[{"type": "text", "text": "Mock response"}],
            tool_calls=[],
            done=True,
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )

    async def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
        temperature: float = 1.0,
        thinking_enabled: bool | None = None,
        thinking_effort: str | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": messages,
                "tools": tools,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "thinking_enabled": thinking_enabled,
                "thinking_effort": thinking_effort,
            }
        )
        return self.response

    @contextlib.asynccontextmanager
    async def stream(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
        temperature: float = 1.0,
        thinking_enabled: bool | None = None,
        thinking_effort: str | None = None,
    ) -> AsyncIterator:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": messages,
                "tools": tools,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "thinking_enabled": thinking_enabled,
                "thinking_effort": thinking_effort,
            }
        )
        yield self  # not used in tests that only need create()

    def __aiter__(self) -> AsyncIterator[str | dict[str, Any]]:
        return self._stream_text()

    async def _stream_text(self) -> AsyncIterator[str | dict[str, Any]]:
        for block in self.response.content:
            if block.get("type") == "thinking":
                thinking = block.get("thinking") or block.get("text") or ""
                if thinking:
                    yield {"type": "thinking_delta", "content": thinking}
            if block.get("type") == "text":
                yield block["text"]

    async def get_response(self) -> LLMResponse:
        return self.response


@pytest.fixture
def mock_llm() -> MockLLMClient:
    """Return a MockLLMClient with a default text-only response."""
    return MockLLMClient()
