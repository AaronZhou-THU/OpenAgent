"""Tests for agent_service.agent.llm — data classes, adapters, and wrappers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest import mock

import pytest

from agent_service.agent.llm import (
    LLMResponse,
    OpenAIAdapter,
    RetryingLLMClient,
    ToolCall,
    TracingLLMClient,
    _anthropic_to_response,
    _openai_messages_from_internal,
    _openai_to_response,
    build_raw_llm_client,
)


# ---------------------------------------------------------------------------
# Fake Anthropic response objects
# ---------------------------------------------------------------------------


@dataclass
class FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class FakeTextBlock:
    type: str = "text"
    text: str = "Hello"

    def model_dump(self) -> dict:
        return {"type": self.type, "text": self.text}


@dataclass
class FakeToolUseBlock:
    type: str = "tool_use"
    id: str = "tu_1"
    name: str = "bash"
    input: dict = None

    def __post_init__(self):
        if self.input is None:
            self.input = {"command": "ls"}

    def model_dump(self) -> dict:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


@dataclass
class FakeAnthropicMessage:
    content: list = None
    usage: FakeUsage = None
    stop_reason: str = "end_turn"

    def __post_init__(self):
        if self.content is None:
            self.content = [FakeTextBlock()]
        if self.usage is None:
            self.usage = FakeUsage()


# ---------------------------------------------------------------------------
# Fake OpenAI response objects
# ---------------------------------------------------------------------------


@dataclass
class FakeOpenAIUsage:
    prompt_tokens: int = 120
    completion_tokens: int = 45


@dataclass
class FakeOpenAIFunction:
    name: str
    arguments: str


@dataclass
class FakeOpenAIToolCall:
    id: str
    function: FakeOpenAIFunction


@dataclass
class FakeOpenAIMessage:
    content: str | None = "Hello from OpenAI"
    tool_calls: list | None = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


@dataclass
class FakeOpenAIChoice:
    message: FakeOpenAIMessage
    finish_reason: str = "stop"


@dataclass
class FakeOpenAIResponse:
    choices: list
    usage: FakeOpenAIUsage | None = None

    def __post_init__(self):
        if self.usage is None:
            self.usage = FakeOpenAIUsage()


# ---------------------------------------------------------------------------
# _anthropic_to_response tests
# ---------------------------------------------------------------------------


def test_text_only_response():
    raw = FakeAnthropicMessage(content=[FakeTextBlock(text="hi")])
    resp = _anthropic_to_response(raw)
    assert len(resp.content) == 1
    assert resp.content[0]["type"] == "text"
    assert resp.content[0]["text"] == "hi"
    assert resp.tool_calls == []
    assert resp.done is True
    assert resp.input_tokens == 100
    assert resp.output_tokens == 50


def test_tool_use_response():
    raw = FakeAnthropicMessage(
        content=[FakeTextBlock(text="Let me run that"), FakeToolUseBlock()],
        stop_reason="tool_use",
    )
    resp = _anthropic_to_response(raw)
    assert len(resp.content) == 2
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc.name == "bash"
    assert tc.id == "tu_1"
    assert tc.input == {"command": "ls"}
    assert resp.done is False  # has tool calls => not done


def test_done_true_when_no_tools():
    raw = FakeAnthropicMessage(content=[FakeTextBlock()])
    resp = _anthropic_to_response(raw)
    assert resp.done is True


def test_done_false_when_tools():
    raw = FakeAnthropicMessage(
        content=[FakeToolUseBlock()],
        stop_reason="tool_use",
    )
    resp = _anthropic_to_response(raw)
    assert resp.done is False


# ---------------------------------------------------------------------------
# OpenAI adapter helpers tests
# ---------------------------------------------------------------------------


def test_openai_text_only_response():
    raw = FakeOpenAIResponse(
        choices=[FakeOpenAIChoice(message=FakeOpenAIMessage(content="hi"))]
    )
    resp = _openai_to_response(raw)
    assert resp.content == [{"type": "text", "text": "hi"}]
    assert resp.tool_calls == []
    assert resp.done is True
    assert resp.stop_reason == "end_turn"
    assert resp.input_tokens == 120
    assert resp.output_tokens == 45


def test_openai_tool_call_response():
    raw = FakeOpenAIResponse(
        choices=[
            FakeOpenAIChoice(
                message=FakeOpenAIMessage(
                    content="Let me check",
                    tool_calls=[
                        FakeOpenAIToolCall(
                            id="call_1",
                            function=FakeOpenAIFunction(
                                name="bash",
                                arguments='{"command":"ls"}',
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ]
    )
    resp = _openai_to_response(raw)
    assert resp.content[0] == {"type": "text", "text": "Let me check"}
    assert resp.content[1] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "bash",
        "input": {"command": "ls"},
    }
    assert resp.tool_calls == [
        ToolCall(id="call_1", name="bash", input={"command": "ls"})
    ]
    assert resp.done is False
    assert resp.stop_reason == "tool_use"


def test_internal_messages_convert_to_openai_chat_shape():
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I will run a tool."},
                {"type": "tool_use", "id": "tu_1", "name": "bash", "input": {"command": "pwd"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": "/tmp"},
            ],
        },
    ]
    converted = _openai_messages_from_internal(system="sys", messages=messages)
    assert converted == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "I will run a tool.",
            "tool_calls": [
                {
                    "id": "tu_1",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": '{"command": "pwd"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tu_1", "content": "/tmp"},
    ]


def test_build_raw_llm_client_openai():
    client = build_raw_llm_client(
        provider="openai",
        openai_api_key="test-key",
    )
    assert isinstance(client, OpenAIAdapter)


# ---------------------------------------------------------------------------
# ToolCall and LLMResponse dataclasses
# ---------------------------------------------------------------------------


def test_tool_call_dataclass():
    tc = ToolCall(id="t1", name="read_file", input={"path": "x.py"})
    assert tc.id == "t1"
    assert tc.name == "read_file"
    assert tc.input == {"path": "x.py"}


def test_llm_response_defaults():
    resp = LLMResponse(content=[], tool_calls=[], done=True)
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0
    assert resp.stop_reason == ""


# ---------------------------------------------------------------------------
# RetryingLLMClient._is_retryable tests
# ---------------------------------------------------------------------------


def test_retryable_status_codes():
    from tests.conftest import MockLLMClient

    inner = MockLLMClient()
    client = RetryingLLMClient(inner)

    # 429 is retryable
    exc_429 = Exception("rate limit")
    exc_429.status_code = 429
    assert client._is_retryable(exc_429) is True

    # 500 is retryable
    exc_500 = Exception("server error")
    exc_500.status_code = 500
    assert client._is_retryable(exc_500) is True

    # 502, 503, 529 are retryable
    for code in (502, 503, 529):
        exc = Exception()
        exc.status_code = code
        assert client._is_retryable(exc) is True

    # 400 is NOT retryable
    exc_400 = Exception("bad request")
    exc_400.status_code = 400
    assert client._is_retryable(exc_400) is False

    # ConnectionError is retryable
    assert client._is_retryable(ConnectionError("refused")) is True

    # TimeoutError is retryable
    assert client._is_retryable(TimeoutError("timeout")) is True

    # Generic exception is NOT retryable
    assert client._is_retryable(ValueError("oops")) is False


# ---------------------------------------------------------------------------
# RetryingLLMClient.create tests
# ---------------------------------------------------------------------------


async def test_retry_succeeds_first_try():
    from tests.conftest import MockLLMClient

    inner = MockLLMClient()
    client = RetryingLLMClient(inner, max_retries=3)
    resp = await client.create(
        model="test", system="", messages=[], tools=[], max_tokens=100
    )
    assert resp.done is True
    assert len(inner.calls) == 1


@mock.patch("agent_service.agent.llm.asyncio.sleep", new_callable=mock.AsyncMock)
async def test_retry_on_retryable_error_then_succeeds(mock_sleep):
    """Retries on a retryable error, then succeeds."""
    from tests.conftest import MockLLMClient

    inner = MockLLMClient()
    call_count = 0
    original_create = inner.create

    async def flaky_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            exc = Exception("overloaded")
            exc.status_code = 529
            raise exc
        return await original_create(**kwargs)

    inner.create = flaky_create
    client = RetryingLLMClient(inner, max_retries=3, base_delay=0.01)
    resp = await client.create(
        model="test", system="", messages=[], tools=[], max_tokens=100
    )
    assert resp.done is True
    assert call_count == 2
    mock_sleep.assert_called_once()


async def test_retry_raises_on_non_retryable():
    """Non-retryable errors are raised immediately."""
    from tests.conftest import MockLLMClient

    inner = MockLLMClient()

    async def bad_create(**kwargs):
        exc = Exception("invalid request")
        exc.status_code = 400
        raise exc

    inner.create = bad_create
    client = RetryingLLMClient(inner, max_retries=3)
    with pytest.raises(Exception, match="invalid request"):
        await client.create(
            model="test", system="", messages=[], tools=[], max_tokens=100
        )


# ---------------------------------------------------------------------------
# TracingLLMClient tests
# ---------------------------------------------------------------------------


async def test_tracing_emits_events():
    from tests.conftest import MockLLMClient

    inner = MockLLMClient()
    events: list[dict] = []

    async def capture_event(event: dict):
        events.append(event)

    client = TracingLLMClient(inner, capture_event)
    resp = await client.create(
        model="test-model",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        max_tokens=100,
    )
    assert resp.done is True

    # Should have emitted request and response events
    assert len(events) == 2
    req_event = events[0]
    assert req_event["type"] == "llm_request"
    assert req_event["model"] == "test-model"
    assert req_event["seq"] == 1

    resp_event = events[1]
    assert resp_event["type"] == "llm_response"
    assert resp_event["seq"] == 1
    assert resp_event["done"] is True
