"""Tests for _micro_compact from agent_service.agent.loop."""

from __future__ import annotations

import copy

import pytest

from agent_service.agent.loop import MICRO_COMPACT_KEEP, _micro_compact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_exchange(
    tool_id: str, tool_name: str, result_content: str
) -> list[dict]:
    """Return an [assistant, user] pair simulating a tool call + result."""
    return [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": {},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_content,
                }
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_few_results_untouched():
    """Messages with <= MICRO_COMPACT_KEEP tool results should be unchanged."""
    messages = []
    for i in range(MICRO_COMPACT_KEEP):
        messages.extend(
            _make_tool_exchange(f"t{i}", "bash", "x" * 200)
        )
    original = copy.deepcopy(messages)
    _micro_compact(messages)
    assert messages == original


def test_old_results_replaced():
    """Old results with long content should be replaced with placeholders."""
    messages = []
    n = MICRO_COMPACT_KEEP + 3  # 3 old results to replace
    for i in range(n):
        messages.extend(
            _make_tool_exchange(f"t{i}", f"tool_{i}", "A" * 200)
        )
    _micro_compact(messages)

    # Count tool_result blocks
    results = []
    for msg in messages:
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    results.append(part)

    # First 3 (old) should be replaced
    for r in results[:3]:
        assert r["content"].startswith("[Previous:")
    # Last MICRO_COMPACT_KEEP should be untouched
    for r in results[-MICRO_COMPACT_KEEP:]:
        assert r["content"] == "A" * 200


def test_recent_results_kept_intact():
    """The most recent MICRO_COMPACT_KEEP results should not be modified."""
    messages = []
    n = MICRO_COMPACT_KEEP + 2
    for i in range(n):
        messages.extend(
            _make_tool_exchange(f"t{i}", "read_file", "B" * 300)
        )
    _micro_compact(messages)

    results = []
    for msg in messages:
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    results.append(part)

    # Last MICRO_COMPACT_KEEP should be original content
    for r in results[-MICRO_COMPACT_KEEP:]:
        assert r["content"] == "B" * 300


def test_short_content_not_replaced():
    """Content <= 100 chars should NOT be replaced even if old."""
    messages = []
    # Old result with short content
    messages.extend(_make_tool_exchange("t0", "bash", "short"))
    # Then enough results to make t0 "old"
    for i in range(1, MICRO_COMPACT_KEEP + 2):
        messages.extend(
            _make_tool_exchange(f"t{i}", "bash", "Y" * 200)
        )
    _micro_compact(messages)

    # Find the first tool_result (t0)
    for msg in messages:
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "tool_result"
                    and part.get("tool_use_id") == "t0"
                ):
                    assert part["content"] == "short"  # NOT replaced
                    return
    pytest.fail("Did not find t0 tool_result")
