"""
Provider-agnostic LLM client abstraction.

The agent loop talks to this interface, not to any specific SDK.
Swap the adapter to switch providers (Anthropic, OpenAI, Ollama, etc.).

Internal message format (close to Anthropic, adapters translate):
    user text:      {"role": "user",      "content": "hello"}
    assistant:      {"role": "assistant",  "content": [{"type": "text", ...}, {"type": "tool_use", ...}]}
    tool results:   {"role": "user",      "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}

Tool definitions use Anthropic-style schema:
    {"name": "...", "description": "...", "input_schema": {...}}
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    """Provider-agnostic model response."""

    content: list[dict[str, Any]]  # normalised content blocks as dicts
    tool_calls: list[ToolCall]  # extracted for convenience
    done: bool  # True when model did NOT request tool use
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""  # e.g. "end_turn", "tool_use", "max_tokens"


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class LLMStream(Protocol):
    """Async-iterable of stream deltas; call get_response() after iteration."""

    def __aiter__(self) -> AsyncIterator[str | dict[str, Any]]: ...
    async def get_response(self) -> LLMResponse: ...


@runtime_checkable
class LLMClient(Protocol):
    """
    Provider-agnostic LLM client.

    Implement ``create`` (non-streaming) and ``stream`` (streaming) to
    add a new provider.  Both accept the same parameters in the internal
    message/tool format documented at the top of this module.
    """

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
    ) -> LLMResponse: ...

    def stream(
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
    ) -> contextlib.AbstractAsyncContextManager[LLMStream]: ...


def _normalize_thinking_effort(value: str | None) -> str:
    value = (value or "high").strip().lower()
    return "max" if value in {"max", "xhigh"} else "high"


def _add_anthropic_thinking(
    kwargs: dict[str, Any],
    *,
    thinking_enabled: bool | None,
    thinking_effort: str | None,
) -> None:
    if thinking_enabled is None:
        return
    kwargs["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}
    if thinking_enabled:
        kwargs["output_config"] = {
            "effort": _normalize_thinking_effort(thinking_effort),
        }


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------


def _anthropic_to_response(raw: Any) -> LLMResponse:
    """Convert an ``anthropic.types.Message`` to an ``LLMResponse``.

    Handles ``mcp_tool_use`` / ``mcp_tool_result`` blocks from Anthropic's
    remote MCP integration.  These are added to ``content`` for context but
    NOT to ``tool_calls`` because they are executed server-side by Anthropic.
    """
    content: list[dict[str, Any]] = []
    tool_calls: list[ToolCall] = []

    for block in raw.content:
        if hasattr(block, "model_dump"):
            d = block.model_dump()
        elif isinstance(block, dict):
            d = block
        else:
            d = {"type": "text", "text": str(block)}
        content.append(d)

        btype = d.get("type", "")
        if btype == "tool_use":
            tool_calls.append(
                ToolCall(id=d["id"], name=d["name"], input=d["input"])
            )
        # mcp_tool_use blocks are server-side — do NOT add to tool_calls

    # done = no tool calls to execute.
    # Using len(tool_calls) instead of stop_reason because some providers
    # (e.g. DeepSeek) may return tool_use blocks with stop_reason != "tool_use".
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        done=len(tool_calls) == 0,
        input_tokens=raw.usage.input_tokens,
        output_tokens=raw.usage.output_tokens,
        stop_reason=getattr(raw, "stop_reason", "") or "",
    )


class _AnthropicStream:
    """Wraps ``anthropic.MessageStream`` to satisfy ``LLMStream``."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    async def _iter_events(self) -> AsyncIterator[str | dict[str, Any]]:
        async for event in self._stream:
            if getattr(event, "type", None) == "thinking":
                thinking = getattr(event, "thinking", "")
                if thinking:
                    yield {"type": "thinking_delta", "content": thinking}
            elif getattr(event, "type", None) == "text":
                text = getattr(event, "text", "")
                if text:
                    yield text

    def __aiter__(self) -> AsyncIterator[str | dict[str, Any]]:
        return self._iter_events()

    async def get_response(self) -> LLMResponse:
        message = await self._stream.get_final_message()
        return _anthropic_to_response(message)


class AnthropicAdapter:
    """``LLMClient`` implementation backed by the Anthropic Python SDK."""

    def __init__(self, client: Any) -> None:  # accepts AsyncAnthropic
        self._client = client
        self._mcp_servers: list[dict] | None = None

    async def create(
        self,
        *,
        model: str,
        system: str = "",
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
        temperature: float = 1.0,
        thinking_enabled: bool | None = None,
        thinking_effort: str | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        _add_anthropic_thinking(
            kwargs,
            thinking_enabled=thinking_enabled,
            thinking_effort=thinking_effort,
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        if self._mcp_servers:
            kwargs["mcp_servers"] = self._mcp_servers
            kwargs["betas"] = ["mcp-client-2025-04-04"]
            raw = await self._client.beta.messages.create(**kwargs)
        else:
            raw = await self._client.messages.create(**kwargs)
        return _anthropic_to_response(raw)

    @contextlib.asynccontextmanager
    async def stream(
        self,
        *,
        model: str,
        system: str = "",
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
        temperature: float = 1.0,
        thinking_enabled: bool | None = None,
        thinking_effort: str | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        _add_anthropic_thinking(
            kwargs,
            thinking_enabled=thinking_enabled,
            thinking_effort=thinking_effort,
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        if self._mcp_servers:
            kwargs["mcp_servers"] = self._mcp_servers
            kwargs["betas"] = ["mcp-client-2025-04-04"]
            async with self._client.beta.messages.stream(**kwargs) as raw_stream:
                yield _AnthropicStream(raw_stream)
        else:
            async with self._client.messages.stream(**kwargs) as raw_stream:
                yield _AnthropicStream(raw_stream)


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------


def _map_openai_finish_reason(reason: str | None) -> str:
    mapping = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
    }
    return mapping.get(reason or "", reason or "")


def _parse_tool_arguments(arguments: str | None) -> dict[str, Any]:
    if not arguments:
        return {}
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        logger.warning("OpenAI tool arguments were not valid JSON: %r", arguments)
        return {"raw_arguments": arguments}
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def _openai_tools_from_internal(tools: list[dict] | None) -> list[dict]:
    converted: list[dict] = []
    for tool in tools or []:
        converted.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return converted


def _add_openai_thinking(
    kwargs: dict[str, Any],
    *,
    thinking_enabled: bool | None,
    thinking_effort: str | None,
) -> None:
    if thinking_enabled is None:
        return
    kwargs["extra_body"] = {
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
    }
    if thinking_enabled:
        kwargs["reasoning_effort"] = _normalize_thinking_effort(thinking_effort)


def _openai_messages_from_internal(
    *,
    system: str,
    messages: list[dict],
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []

    if system:
        converted.append({"role": "system", "content": system})

    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if isinstance(content, str):
            converted.append({"role": role, "content": content})
            continue

        if role == "assistant" and isinstance(content, list):
            text_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    text_parts.append(str(block))
                    continue
                btype = block.get("type")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "thinking":
                    reasoning_parts.append(block.get("thinking") or block.get("text") or "")
                elif btype == "tool_use":
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    })
            converted_msg = {
                "role": "assistant",
                "content": "".join(text_parts) or None,
                **({"tool_calls": tool_calls} if tool_calls else {}),
            }
            reasoning_content = "".join(reasoning_parts)
            if reasoning_content:
                converted_msg["reasoning_content"] = reasoning_content
            converted.append(converted_msg)
            continue

        if role == "user" and isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    text_parts.append(str(block))
                    continue
                btype = block.get("type")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_result":
                    if text_parts:
                        converted.append({"role": "user", "content": "".join(text_parts)})
                        text_parts = []
                    converted.append({
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": str(block.get("content", "")),
                    })
            if text_parts:
                converted.append({"role": "user", "content": "".join(text_parts)})
            continue

        converted.append({"role": role, "content": str(content)})

    return converted


def _openai_to_response(raw: Any) -> LLMResponse:
    choice = raw.choices[0]
    message = choice.message

    content: list[dict[str, Any]] = []
    tool_calls: list[ToolCall] = []

    reasoning_content = getattr(message, "reasoning_content", None)
    if reasoning_content:
        content.append({"type": "thinking", "thinking": reasoning_content})

    if getattr(message, "content", None):
        content.append({"type": "text", "text": message.content})

    for tool_call in getattr(message, "tool_calls", None) or []:
        tool_input = _parse_tool_arguments(tool_call.function.arguments)
        block = {
            "type": "tool_use",
            "id": tool_call.id,
            "name": tool_call.function.name,
            "input": tool_input,
        }
        content.append(block)
        tool_calls.append(
            ToolCall(
                id=tool_call.id,
                name=tool_call.function.name,
                input=tool_input,
            )
        )

    usage = getattr(raw, "usage", None)
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        done=len(tool_calls) == 0,
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        stop_reason=_map_openai_finish_reason(choice.finish_reason),
    )


class _OpenAIStream:
    """Accumulates streamed chat completion chunks into an ``LLMResponse``."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._thinking_parts: list[str] = []
        self._text_parts: list[str] = []
        self._tool_calls: dict[int, dict[str, Any]] = {}
        self._usage: Any = None
        self._finish_reason: str = ""

    async def _iter_text(self) -> AsyncIterator[str | dict[str, Any]]:
        async for chunk in self._stream:
            if getattr(chunk, "usage", None) is not None:
                self._usage = chunk.usage

            if not getattr(chunk, "choices", None):
                continue

            choice = chunk.choices[0]
            if choice.finish_reason:
                self._finish_reason = _map_openai_finish_reason(choice.finish_reason)

            delta = choice.delta
            if delta is None:
                continue

            if getattr(delta, "reasoning_content", None):
                self._thinking_parts.append(delta.reasoning_content)
                yield {
                    "type": "thinking_delta",
                    "content": delta.reasoning_content,
                }

            if getattr(delta, "content", None):
                self._text_parts.append(delta.content)
                yield delta.content

            for tool_call in getattr(delta, "tool_calls", None) or []:
                current = self._tool_calls.setdefault(
                    tool_call.index,
                    {"id": tool_call.id or f"tool_{tool_call.index}", "name": "", "arguments": []},
                )
                if tool_call.id:
                    current["id"] = tool_call.id
                if getattr(tool_call, "function", None):
                    if getattr(tool_call.function, "name", None):
                        current["name"] = tool_call.function.name
                    if getattr(tool_call.function, "arguments", None):
                        current["arguments"].append(tool_call.function.arguments)

    def __aiter__(self) -> AsyncIterator[str | dict[str, Any]]:
        return self._iter_text()

    async def get_response(self) -> LLMResponse:
        content: list[dict[str, Any]] = []
        tool_calls: list[ToolCall] = []

        text = "".join(self._text_parts)
        thinking = "".join(self._thinking_parts)
        if thinking:
            content.append({"type": "thinking", "thinking": thinking})
        if text:
            content.append({"type": "text", "text": text})

        for _, tool_call in sorted(self._tool_calls.items()):
            tool_input = _parse_tool_arguments("".join(tool_call["arguments"]))
            block = {
                "type": "tool_use",
                "id": tool_call["id"],
                "name": tool_call["name"],
                "input": tool_input,
            }
            content.append(block)
            tool_calls.append(
                ToolCall(
                    id=tool_call["id"],
                    name=tool_call["name"],
                    input=tool_input,
                )
            )

        usage = self._usage
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            done=len(tool_calls) == 0,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            stop_reason=self._finish_reason,
        )


class OpenAIAdapter:
    """``LLMClient`` implementation backed by the OpenAI Python SDK."""

    def __init__(self, client: Any) -> None:  # accepts AsyncOpenAI
        self._client = client

    async def create(
        self,
        *,
        model: str,
        system: str = "",
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
        temperature: float = 1.0,
        thinking_enabled: bool | None = None,
        thinking_effort: str | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _openai_messages_from_internal(system=system, messages=messages),
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }
        _add_openai_thinking(
            kwargs,
            thinking_enabled=thinking_enabled,
            thinking_effort=thinking_effort,
        )
        openai_tools = _openai_tools_from_internal(tools)
        if openai_tools:
            kwargs["tools"] = openai_tools

        raw = await self._client.chat.completions.create(**kwargs)
        return _openai_to_response(raw)

    @contextlib.asynccontextmanager
    async def stream(
        self,
        *,
        model: str,
        system: str = "",
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
        temperature: float = 1.0,
        thinking_enabled: bool | None = None,
        thinking_effort: str | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _openai_messages_from_internal(system=system, messages=messages),
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        _add_openai_thinking(
            kwargs,
            thinking_enabled=thinking_enabled,
            thinking_effort=thinking_effort,
        )
        openai_tools = _openai_tools_from_internal(tools)
        if openai_tools:
            kwargs["tools"] = openai_tools

        raw_stream = await self._client.chat.completions.create(**kwargs)
        try:
            yield _OpenAIStream(raw_stream)
        finally:
            close = getattr(raw_stream, "close", None)
            if callable(close):
                close()


def build_raw_llm_client(
    *,
    provider: str,
    anthropic_api_key: str = "",
    anthropic_base_url: str | None = None,
    openai_api_key: str = "",
    openai_base_url: str | None = None,
) -> LLMClient:
    """Instantiate the configured provider adapter with lazy SDK imports."""

    normalized = provider.strip().lower()
    if normalized == "anthropic":
        from anthropic import AsyncAnthropic

        return AnthropicAdapter(
            AsyncAnthropic(
                api_key=anthropic_api_key or None,
                base_url=anthropic_base_url,
            )
        )
    if normalized == "openai":
        from openai import AsyncOpenAI

        return OpenAIAdapter(
            AsyncOpenAI(
                api_key=openai_api_key or None,
                base_url=openai_base_url,
            )
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tracing wrapper — emits raw request/response data via callback
# ---------------------------------------------------------------------------


class _TracingStream:
    """Wraps an LLMStream to emit a response event after iteration."""

    def __init__(self, inner: LLMStream, on_response) -> None:
        self._inner = inner
        self._on_response = on_response

    def __aiter__(self):
        return self._inner.__aiter__()

    async def get_response(self) -> LLMResponse:
        resp = await self._inner.get_response()
        await self._on_response(resp)
        return resp


_SECRET_PATTERNS = [
    re.compile(r'(?:sk-|api[_-]?key|token|secret|password|auth)["\s:=]+\S{8,}', re.IGNORECASE),
    re.compile(r'\b[A-Za-z0-9+/]{40,}={0,2}\b'),  # base64-like long strings
    re.compile(r'Bearer\s+\S{20,}', re.IGNORECASE),
]


def _redact_sensitive(value: Any) -> Any:
    """Recursively redact API keys, tokens, and known secret patterns from tracing data."""
    if isinstance(value, str):
        redacted = value
        for pat in _SECRET_PATTERNS:
            redacted = pat.sub("[REDACTED]", redacted)
        return redacted
    if isinstance(value, dict):
        return {k: _redact_sensitive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


class TracingLLMClient:
    """Wraps any LLMClient and emits ``llm_request`` / ``llm_response``
    events via an async callback for every API call.

    The callback receives a dict suitable for ``send_event()``::

        {"type": "llm_request",  "model": ..., "messages": ..., ...}
        {"type": "llm_response", "content": ..., "usage": ..., ...}

    This captures *all* LLM calls (main loop, subagents, teammates)
    because it wraps the client itself — not any specific call site.

    Sensitive data (API keys, tokens, secrets) is redacted before emission.
    """

    def __init__(self, inner, emit_event) -> None:
        self._inner = inner
        self._emit = emit_event
        self._call_seq = 0  # monotonic counter for pairing request/response

    async def _emit_request(
        self,
        seq: int,
        *,
        model,
        system,
        messages,
        tools,
        max_tokens,
        temperature,
        thinking_enabled=None,
        thinking_effort=None,
    ):
        await self._emit(_redact_sensitive({
            "type": "llm_request",
            "seq": seq,
            "model": model,
            "system": system,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "thinking_enabled": thinking_enabled,
            "thinking_effort": thinking_effort,
            "message_count": len(messages),
            "tool_count": len(tools) if tools else 0,
        }))

    async def _emit_response(self, seq: int, resp: LLMResponse):
        await self._emit(_redact_sensitive({
            "type": "llm_response",
            "seq": seq,
            "content": resp.content,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "input": tc.input}
                for tc in resp.tool_calls
            ],
            "done": resp.done,
            "usage": {
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
            },
        }))

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
        self._call_seq += 1
        seq = self._call_seq
        await self._emit_request(seq, model=model, system=system,
                                  messages=messages, tools=tools,
                                  max_tokens=max_tokens, temperature=temperature,
                                  thinking_enabled=thinking_enabled,
                                  thinking_effort=thinking_effort)
        resp = await self._inner.create(
            model=model, system=system, messages=messages,
            tools=tools, max_tokens=max_tokens, temperature=temperature,
            thinking_enabled=thinking_enabled, thinking_effort=thinking_effort,
        )
        await self._emit_response(seq, resp)
        return resp

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
    ):
        self._call_seq += 1
        seq = self._call_seq
        await self._emit_request(seq, model=model, system=system,
                                  messages=messages, tools=tools,
                                  max_tokens=max_tokens, temperature=temperature,
                                  thinking_enabled=thinking_enabled,
                                  thinking_effort=thinking_effort)

        async def _on_response(resp):
            await self._emit_response(seq, resp)

        async with self._inner.stream(
            model=model, system=system, messages=messages,
            tools=tools, max_tokens=max_tokens, temperature=temperature,
            thinking_enabled=thinking_enabled, thinking_effort=thinking_effort,
        ) as inner_stream:
            yield _TracingStream(inner_stream, _on_response)


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------


class RetryingLLMClient:
    """Wraps any LLMClient with exponential backoff retry on transient errors.

    Retries ``create()`` and the initial connection of ``stream()``.
    Mid-stream failures are NOT retried (rare and unrecoverable).
    The LLMClient protocol is unchanged — this wrapper is transparent.
    """

    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}

    def __init__(
        self,
        inner: LLMClient,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> None:
        self._inner = inner
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

    def _is_retryable(self, exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status in self._RETRYABLE_STATUS_CODES:
            return True
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True
        return False

    async def _retry_delay(self, attempt: int) -> None:
        delay = min(
            self._base_delay * (2 ** attempt) + random.uniform(0, 1),
            self._max_delay,
        )
        logger.warning("LLM call failed (attempt %d/%d), retrying in %.1fs",
                        attempt + 1, self._max_retries + 1, delay)
        await asyncio.sleep(delay)

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
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._inner.create(
                    model=model, system=system, messages=messages,
                    tools=tools, max_tokens=max_tokens, temperature=temperature,
                    thinking_enabled=thinking_enabled, thinking_effort=thinking_effort,
                )
            except Exception as e:
                last_exc = e
                if not self._is_retryable(e) or attempt == self._max_retries:
                    raise
                await self._retry_delay(attempt)
        raise last_exc  # unreachable but satisfies type checker

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
    ):
        """Retry only the initial connection (``__aenter__``), not mid-stream."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                cm = self._inner.stream(
                    model=model, system=system, messages=messages,
                    tools=tools, max_tokens=max_tokens, temperature=temperature,
                    thinking_enabled=thinking_enabled, thinking_effort=thinking_effort,
                )
                stream_obj = await cm.__aenter__()
                try:
                    yield stream_obj
                finally:
                    await cm.__aexit__(None, None, None)
                return
            except Exception as e:
                last_exc = e
                if not self._is_retryable(e) or attempt == self._max_retries:
                    raise
                await self._retry_delay(attempt)
        raise last_exc  # unreachable
