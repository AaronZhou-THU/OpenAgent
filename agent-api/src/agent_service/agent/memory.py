"""
Persistent session memory — learns from conversations across sessions.

At session end (WebSocket disconnect), an LLM analyzes the full conversation
and merges extracted facts/preferences/decisions into workspace/.agent/memory.md.
This memory is injected into the system prompt for all future conversations.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from agent_service.agent.llm import LLMClient

logger = logging.getLogger(__name__)

MAX_MEMORY_BYTES = 4096

ANALYSIS_PROMPT = """\
You are a memory analyst for a coding agent. Given the existing memory and a completed
conversation session, produce an updated memory.md file.

Rules:
- Keep total output under 2KB
- Use these sections: ## User Preferences, ## Project Context, ## Decisions, ## Corrections
- Merge new learnings with existing memory (don't duplicate)
- Remove outdated entries that are contradicted by new information
- Only record durable facts (not transient task details)
- NEVER record the assistant's role or persona (e.g. "coding agent", "work assistant") — that is determined by the preset, not memory
- Be concise — bullet points, not paragraphs

Existing memory:
{existing_memory}

Session transcript:
{session_text}

Output the complete updated memory.md:"""


class MemoryManager:
    """Read/write workspace/.agent/memory.md."""

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / ".agent" / "memory.md"

    def read(self) -> str:
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return ""

    def write(self, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Enforce max size — truncate from top to stay under limit
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_MEMORY_BYTES:
            lines = content.splitlines(keepends=True)
            while lines and len("".join(lines).encode("utf-8")) > MAX_MEMORY_BYTES:
                lines.pop(0)
            content = "".join(lines)
        self.path.write_text(content, encoding="utf-8")


def _messages_to_compact_text(messages: list[dict]) -> str:
    """Render messages as compact text for memory analysis."""
    parts: list[str] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            parts.append(f"[{role}] {content[:300]}")
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    parts.append(f"[{role}] {block['text'][:300]}")
                elif btype == "tool_use":
                    inp = json.dumps(block.get("input", {}))[:150]
                    parts.append(f"[tool_call] {block['name']}({inp})")
                elif btype == "tool_result":
                    parts.append(
                        f"[tool_result] {str(block.get('content', ''))[:150]}"
                    )
    return "\n".join(parts)[:20_000]


async def analyze_session(
    messages: list[dict],
    existing_memory: str,
    llm: LLMClient,
    model: str,
) -> str:
    """Call LLM to produce updated memory.md from conversation + existing memory."""
    session_text = _messages_to_compact_text(messages)
    prompt = ANALYSIS_PROMPT.format(
        existing_memory=existing_memory or "(empty — first session)",
        session_text=session_text,
    )
    resp = await llm.create(
        model=model,
        system="",
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        max_tokens=2048,
    )
    # Extract text from response
    for block in resp.content:
        if isinstance(block, dict) and block.get("type") == "text":
            return block["text"]
    return existing_memory  # fallback: keep existing if extraction fails


async def save_session_memory(
    conv_id: str,
    llm: LLMClient,
    config: "Settings",  # noqa: F821  — forward ref to avoid circular import
) -> None:
    """Load conversation from DB, analyze, and save memory. Called at disconnect."""
    from agent_service import database as db
    from agent_service.models import Message
    from sqlalchemy import select

    workspace = Path(config.workspace_dir).resolve()

    async with db.async_session_factory() as session:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at)
        )
        messages = [{"role": m.role, "content": m.content} for m in result.scalars().all()]

    if len(messages) < 2:
        logger.debug("Skipping memory save for conv %s — too few messages", conv_id)
        return

    mgr = MemoryManager(workspace)
    existing = mgr.read()

    try:
        updated = await analyze_session(messages, existing, llm, config.model)
        mgr.write(updated)
        logger.info("Memory saved for conv %s (%d bytes)", conv_id, len(updated))
    except Exception:
        logger.exception("Failed to save session memory for conv %s", conv_id)


# ---------------------------------------------------------------------------
# Workspace cleanup
# ---------------------------------------------------------------------------

PRESERVED_DIRS = {".agent", ".transcripts", ".tasks", ".team"}


def clean_workspace(workspace: Path) -> None:
    """Remove all files and directories in workspace except .agent/ (memory).

    Called after a task completes or a session disconnects.
    """
    if not workspace.exists():
        return

    for item in workspace.iterdir():
        if item.name in PRESERVED_DIRS:
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            logger.debug("Cleaned workspace item: %s", item.name)
        except Exception:
            logger.warning("Failed to clean workspace item: %s", item.name)

    logger.info("Workspace cleaned: %s", workspace)
