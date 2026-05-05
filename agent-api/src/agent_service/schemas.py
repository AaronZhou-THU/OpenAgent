"""Pydantic request / response schemas for the API."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel


# --- Chat -------------------------------------------------------------------

class CreateChatRequest(BaseModel):
    system_prompt: str | None = None
    preset: str | None = None
    enable_teams: bool = False
    enable_tracing: bool = False
    enable_approval: bool = False
    enable_plan_mode: bool = False
    enable_thinking: bool | None = None
    thinking_effort: str | None = None


class CreateChatResponse(BaseModel):
    conversation_id: str


# --- Conversations -----------------------------------------------------------

class ConversationInfo(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime.datetime
    message_count: int


class ConversationDetail(BaseModel):
    id: str
    title: str | None = None
    system_prompt: str | None = None
    preset: str | None = None
    enable_teams: bool = False
    enable_tracing: bool = False
    enable_approval: bool = False
    enable_plan_mode: bool = False
    enable_thinking: bool = False
    thinking_effort: str = "high"
    created_at: datetime.datetime
    messages: list[MessageInfo]
    total_input_tokens: int
    total_output_tokens: int


class MessageInfo(BaseModel):
    role: str
    content: Any
    created_at: datetime.datetime


# --- Tools -------------------------------------------------------------------

class ToolInfo(BaseModel):
    name: str
    description: str


# --- Skills ------------------------------------------------------------------

class SkillInfo(BaseModel):
    name: str
    description: str


class PresetInfo(BaseModel):
    name: str
    description: str


class UploadSkillRequest(BaseModel):
    name: str
    description: str
    body: str
