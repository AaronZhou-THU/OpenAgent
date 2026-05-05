"""Tests for agent_service.schemas — Pydantic models."""

from __future__ import annotations

import datetime

import pytest

from agent_service.schemas import (
    ConversationInfo,
    CreateChatRequest,
    PresetInfo,
    SkillInfo,
    ToolInfo,
)


# ---------------------------------------------------------------------------
# CreateChatRequest
# ---------------------------------------------------------------------------


def test_create_chat_request_defaults():
    req = CreateChatRequest()
    assert req.system_prompt is None
    assert req.preset is None
    assert req.enable_teams is False
    assert req.enable_tracing is False
    assert req.enable_approval is False
    assert req.enable_thinking is None
    assert req.thinking_effort is None


def test_create_chat_request_all_fields():
    req = CreateChatRequest(
        system_prompt="You are helpful",
        preset="coding",
        enable_teams=True,
        enable_tracing=True,
        enable_approval=True,
        enable_thinking=True,
        thinking_effort="max",
    )
    assert req.system_prompt == "You are helpful"
    assert req.preset == "coding"
    assert req.enable_teams is True
    assert req.enable_tracing is True
    assert req.enable_approval is True
    assert req.enable_thinking is True
    assert req.thinking_effort == "max"


# ---------------------------------------------------------------------------
# ConversationInfo
# ---------------------------------------------------------------------------


def test_conversation_info():
    now = datetime.datetime.now(datetime.timezone.utc)
    info = ConversationInfo(
        id="abc123",
        title="Test conv",
        created_at=now,
        message_count=5,
    )
    assert info.id == "abc123"
    assert info.title == "Test conv"
    assert info.created_at == now
    assert info.message_count == 5


def test_conversation_info_no_title():
    now = datetime.datetime.now(datetime.timezone.utc)
    info = ConversationInfo(id="x", created_at=now, message_count=0)
    assert info.title is None


# ---------------------------------------------------------------------------
# ToolInfo, SkillInfo, PresetInfo
# ---------------------------------------------------------------------------


def test_tool_info():
    ti = ToolInfo(name="bash", description="Run a shell command")
    assert ti.name == "bash"
    assert ti.description == "Run a shell command"


def test_skill_info():
    si = SkillInfo(name="code-review", description="Structured code reviews")
    assert si.name == "code-review"
    assert si.description == "Structured code reviews"


def test_preset_info():
    pi = PresetInfo(name="coding", description="Software development")
    assert pi.name == "coding"
    assert pi.description == "Software development"
