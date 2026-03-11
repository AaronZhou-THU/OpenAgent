"""WebSocket handler — streams the agentic loop as JSON events."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_service.agent.background_manager import BackgroundManager
from agent_service.agent.llm import LLMClient, TracingLLMClient
from agent_service.agent.message_bus import MessageBus
from agent_service.agent.protocol_tracker import ProtocolTracker
from agent_service.agent.teammate_manager import TeammateManager
from agent_service.agent.loop import agent_loop
from agent_service.agent.memory import save_session_memory, clean_workspace
from agent_service.agent.prompt_loader import PromptLoader
from agent_service.agent.skill_loader import SkillLoader
from agent_service.agent.task_manager import TaskManager
from agent_service.agent.todo_manager import TodoManager
from agent_service.config import Settings
from agent_service import database as db
from agent_service.models import Conversation, Message, TokenUsage

logger = logging.getLogger(__name__)

ws_router = APIRouter()

# Injected at startup by main.py
_settings: Settings | None = None
_client: LLMClient | None = None
_skill_loader: SkillLoader | None = None
_prompt_loader: PromptLoader | None = None
_mcp_manager: Any | None = None

# In-memory todo managers + locks per conversation
_todo_managers: dict[str, TodoManager] = {}
_conv_locks: dict[str, asyncio.Lock] = {}


def configure(
    settings: Settings,
    client: LLMClient,
    sl: SkillLoader,
    pl: PromptLoader,
    mcp_manager: Any | None = None,
) -> None:
    global _settings, _client, _skill_loader, _prompt_loader, _mcp_manager
    _settings = settings
    _client = client
    _skill_loader = sl
    _prompt_loader = pl
    _mcp_manager = mcp_manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_messages(conv_id: str, session: AsyncSession) -> list[dict]:
    """Load message history from DB and sanitize tool_use/tool_result pairing."""
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
    )
    messages = [{"role": m.role, "content": m.content} for m in result.scalars().all()]
    return _sanitize_messages(messages)


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """Fix orphaned tool_use blocks that lack matching tool_result messages.

    This can happen when a provider (e.g. DeepSeek) returns tool_use blocks
    with stop_reason != "tool_use", causing the loop to treat the response
    as done and skip tool execution.  The orphaned tool_use blocks then
    corrupt the conversation history for subsequent API calls.

    Strategy: for each assistant message with tool_use blocks, check that
    the *next* message contains matching tool_result blocks.  If not,
    strip the tool_use blocks from the assistant message (keeping any text).
    """
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
            tool_use_ids = {
                b["id"]
                for b in msg["content"]
                if isinstance(b, dict) and b.get("type") == "tool_use"
            }
            if tool_use_ids:
                # Check if next message has matching tool_results
                next_msg = messages[i + 1] if i + 1 < len(messages) else None
                has_results = False
                if (
                    next_msg
                    and next_msg["role"] == "user"
                    and isinstance(next_msg.get("content"), list)
                ):
                    result_ids = {
                        b.get("tool_use_id")
                        for b in next_msg["content"]
                        if isinstance(b, dict) and b.get("type") == "tool_result"
                    }
                    has_results = bool(tool_use_ids & result_ids)

                if not has_results:
                    # Strip tool_use blocks, keep text
                    cleaned = [
                        b for b in msg["content"]
                        if not (isinstance(b, dict) and b.get("type") == "tool_use")
                    ]
                    if not cleaned:
                        cleaned = [{"type": "text", "text": "(tool call skipped)"}]
                    msg["content"] = cleaned
                    logger.warning(
                        "Sanitized orphaned tool_use blocks in message %d "
                        "(ids: %s)", i, tool_use_ids,
                    )
        i += 1
    return messages


async def _save_messages(
    conv_id: str, messages: list[dict], start_idx: int, session: AsyncSession
) -> None:
    """Persist new messages (from start_idx onward) to DB."""
    for msg in messages[start_idx:]:
        session.add(
            Message(
                conversation_id=conv_id,
                role=msg["role"],
                content=msg["content"],
            )
        )
    await session.commit()


def _list_workspace_files(workspace: Path) -> list[dict]:
    """Walk workspace, skip .agent/, return [{name, path, size}]."""
    files = []
    if not workspace.exists():
        return files
    for item in workspace.rglob("*"):
        if not item.is_file():
            continue
        try:
            rel = item.relative_to(workspace)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in (".agent", ".transcripts", ".tasks", ".team"):
            continue
        files.append({
            "name": item.name,
            "path": str(rel),
            "size": item.stat().st_size,
        })
    return files


async def _deferred_cleanup(workspace: Path, delay: int) -> None:
    """Wait *delay* seconds, then clean the workspace."""
    await asyncio.sleep(delay)
    try:
        clean_workspace(workspace)
    except Exception:
        logger.debug("Deferred workspace cleanup failed for %s", workspace)


async def _save_usage(
    conv_id: str, usage: dict, model: str, session: AsyncSession
) -> None:
    session.add(
        TokenUsage(
            conversation_id=conv_id,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            model=model,
        )
    )
    await session.commit()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@ws_router.websocket("/api/chat/{conv_id}/ws")
async def chat_ws(ws: WebSocket, conv_id: str):
    if not (_settings and _client and _skill_loader):
        raise RuntimeError("WebSocket handler not configured")

    await ws.accept()

    # Verify conversation exists
    async with db.async_session_factory() as session:
        conv = await session.get(Conversation, conv_id)
        if not conv:
            await ws.send_json(
                {"type": "error", "message": "Conversation not found"}
            )
            await ws.close()
            return
        system_prompt = conv.system_prompt
        preset = conv.preset
        enable_teams = conv.enable_teams
        enable_tracing = conv.enable_tracing
        enable_approval = conv.enable_approval
        enable_plan_mode = conv.enable_plan_mode

    # Per-conversation todo manager + lock (shared across connections)
    if conv_id not in _todo_managers:
        _todo_managers[conv_id] = TodoManager()
    if conv_id not in _conv_locks:
        _conv_locks[conv_id] = asyncio.Lock()
    todo = _todo_managers[conv_id]
    lock = _conv_locks[conv_id]

    # Persistent task manager (file-backed, survives disconnects)
    workspace = Path(_settings.workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    task_manager = TaskManager(workspace)

    # Background task manager (per-session, cleaned up on disconnect)
    bg_manager = BackgroundManager(
        workspace, timeout=_settings.background_timeout
    )

    # Team communication (per-session, only when enabled)
    message_bus: MessageBus | None = None
    protocol_tracker: ProtocolTracker | None = None
    team_manager: TeammateManager | None = None

    cancelled = asyncio.Event()
    interrupt_queue: asyncio.Queue[str] = asyncio.Queue()
    approval_queue: asyncio.Queue | None = (
        asyncio.Queue() if enable_approval else None
    )
    plan_mode_active = enable_plan_mode

    async def send_event(event: dict[str, Any]) -> None:
        try:
            await ws.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            cancelled.set()  # client gone — signal the loop to stop

    # Per-session LLM client — with tracing wrapper when enabled
    session_llm = (
        TracingLLMClient(_client, send_event) if enable_tracing else _client
    )

    if enable_teams:
        message_bus = MessageBus(
            persist_dir=workspace / ".team" / "inbox"
        )
        protocol_tracker = ProtocolTracker()
        team_manager = TeammateManager(
            workspace=workspace,
            bus=message_bus,
            llm=session_llm,
            config=_settings,
            send_event=send_event,
            task_manager=task_manager,
        )

    try:
        pending_content: str | None = None

        while True:
            if pending_content is not None:
                # Re-entering loop with interrupt content — skip receive
                user_content = pending_content
                pending_content = None
            else:
                # Wait for user message
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"type": "message", "content": raw}

                msg_type = data.get("type", "message")

                # Toggle plan mode mid-conversation
                if msg_type == "toggle_plan_mode":
                    plan_mode_active = data.get("enabled", False)
                    await send_event({"type": "plan_mode_changed", "enabled": plan_mode_active})
                    async with db.async_session_factory() as s:
                        c = await s.get(Conversation, conv_id)
                        if c:
                            c.enable_plan_mode = plan_mode_active
                            await s.commit()
                    continue

                # Toggle teams mid-conversation
                if msg_type == "toggle_teams":
                    want_teams = data.get("enabled", False)
                    if want_teams and team_manager is None:
                        message_bus = MessageBus(
                            persist_dir=workspace / ".team" / "inbox"
                        )
                        protocol_tracker = ProtocolTracker()
                        team_manager = TeammateManager(
                            workspace=workspace,
                            bus=message_bus,
                            llm=session_llm,
                            config=_settings,
                            send_event=send_event,
                            task_manager=task_manager,
                        )
                    elif not want_teams and team_manager is not None:
                        await team_manager.shutdown_all()
                        team_manager = None
                        protocol_tracker = None
                        message_bus = None
                    await send_event({"type": "teams_changed", "enabled": team_manager is not None})
                    async with db.async_session_factory() as s:
                        c = await s.get(Conversation, conv_id)
                        if c:
                            c.enable_teams = team_manager is not None
                            await s.commit()
                    continue

                # Toggle tool approval mid-conversation
                if msg_type == "toggle_approval":
                    want_approval = data.get("enabled", False)
                    if want_approval:
                        approval_queue = asyncio.Queue()
                    else:
                        approval_queue = None
                    await send_event({"type": "approval_changed", "enabled": approval_queue is not None})
                    async with db.async_session_factory() as s:
                        c = await s.get(Conversation, conv_id)
                        if c:
                            c.enable_approval = approval_queue is not None
                            await s.commit()
                    continue

                # Plan approval/rejection
                if msg_type == "plan_approval":
                    decision = data.get("decision", "reject")
                    feedback = data.get("feedback", "")
                    if decision == "approve":
                        plan_mode_active = False
                        await send_event({"type": "plan_approved"})
                        await send_event({"type": "plan_mode_changed", "enabled": False})
                        async with db.async_session_factory() as s:
                            c = await s.get(Conversation, conv_id)
                            if c:
                                c.enable_plan_mode = False
                                await s.commit()
                        # Fall through to execute the plan with full tool access
                        data = {"type": "message", "content": "Plan approved. Now execute the plan above step by step."}
                    else:
                        await send_event({"type": "plan_rejected", "feedback": feedback})
                        if feedback:
                            # Inject feedback as a user message so agent can revise
                            data = {"type": "message", "content": f"Plan rejected. Feedback:\n{feedback}\n\nRevise the plan."}
                            # Fall through to normal message handling
                        else:
                            continue

                user_content = data.get("content", "")
                if not user_content:
                    await send_event({"type": "error", "message": "Empty message"})
                    continue

            # Acquire per-conversation lock to prevent concurrent mutations
            async with lock:
                # Load history from DB
                async with db.async_session_factory() as session:
                    messages = await _load_messages(conv_id, session)

                start_idx = len(messages)

                # Append user message
                messages.append({"role": "user", "content": user_content})

                # Listen for cancel / interrupt / approval messages from the client
                async def _cancel_listener() -> None:
                    try:
                        while True:
                            raw_msg = await ws.receive_text()
                            try:
                                msg = json.loads(raw_msg)
                            except json.JSONDecodeError:
                                continue
                            if msg.get("type") == "cancel":
                                cancelled.set()
                                return
                            if msg.get("type") == "interrupt":
                                await interrupt_queue.put(msg.get("content", ""))
                                cancelled.set()
                                return
                            if (
                                msg.get("type") == "tool_approval_response"
                                and approval_queue is not None
                            ):
                                await approval_queue.put(
                                    msg.get("decision", "deny")
                                )
                    except (WebSocketDisconnect, RuntimeError):
                        cancelled.set()

                cancelled.clear()  # reset for each turn
                listener = asyncio.create_task(_cancel_listener())

                # Run the agentic loop
                try:
                    usage = await agent_loop(
                        messages=messages,
                        config=_settings,
                        llm=session_llm,
                        skill_loader=_skill_loader,
                        todo=todo,
                        send_event=send_event,
                        system_prompt=system_prompt,
                        preset=preset,
                        prompt_loader=_prompt_loader,
                        cancelled=cancelled,
                        task_manager=task_manager,
                        background_manager=bg_manager,
                        team_manager=team_manager,
                        message_bus=message_bus,
                        protocol_tracker=protocol_tracker,
                        approval_queue=approval_queue,
                        plan_mode=plan_mode_active,
                        mcp_manager=_mcp_manager,
                    )
                finally:
                    listener.cancel()
                    try:
                        await listener
                    except asyncio.CancelledError:
                        pass

                # Sync plan mode if agent entered it mid-loop
                if usage.get("plan_mode") and not plan_mode_active:
                    plan_mode_active = True
                    async with db.async_session_factory() as s:
                        c = await s.get(Conversation, conv_id)
                        if c:
                            c.enable_plan_mode = True
                            await s.commit()

                # Persist new messages and usage
                async with db.async_session_factory() as session:
                    await _save_messages(conv_id, messages, start_idx, session)
                    await _save_usage(conv_id, usage, _settings.model, session)

                    # Auto-title: use first user message if no title yet
                    conv = await session.get(Conversation, conv_id)
                    if conv and not conv.title:
                        conv.title = user_content[:100]
                        await session.commit()

            # Check for interrupt: if cancelled was set AND there's content
            # in the interrupt queue, this was an interrupt (not a plain cancel)
            if cancelled.is_set():
                try:
                    interrupt_content = interrupt_queue.get_nowait()
                except asyncio.QueueEmpty:
                    interrupt_content = None

                if interrupt_content is not None:
                    # Send interrupted event (like done but signals continuation)
                    workspace = Path(_settings.workspace_dir).resolve()
                    files = _list_workspace_files(workspace)
                    await send_event(
                        {
                            "type": "interrupted",
                            "usage": usage,
                            "files": files,
                        }
                    )
                    pending_content = interrupt_content
                    continue
                else:
                    # Plain cancel or disconnect — stop
                    break

            # Scan workspace for files the agent created
            workspace = Path(_settings.workspace_dir).resolve()
            files = _list_workspace_files(workspace)

            await send_event(
                {
                    "type": "done",
                    "usage": usage,
                    "files": files,
                }
            )

    except (WebSocketDisconnect, RuntimeError):
        logger.info("Client disconnected from conversation %s", conv_id)
    except Exception as e:
        logger.exception("WebSocket error for conversation %s", conv_id)
        try:
            await send_event({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # Cancel any running background tasks and teammates
        try:
            await bg_manager.cancel_all()
        except Exception:
            logger.debug("Could not cancel background tasks for %s", conv_id)
        if team_manager:
            try:
                await team_manager.shutdown_all()
            except Exception:
                logger.debug("Could not shutdown teammates for %s", conv_id)

        # Save session memory (fire-and-forget so disconnect isn't blocked)
        if _settings.enable_memory:
            try:
                asyncio.create_task(
                    save_session_memory(conv_id, _client, _settings)
                )
            except Exception:
                logger.debug("Could not schedule memory save for %s", conv_id)

        # Deferred workspace cleanup (gives users time to download files)
        try:
            workspace = Path(_settings.workspace_dir).resolve()
            delay = _settings.workspace_cleanup_delay
            asyncio.create_task(_deferred_cleanup(workspace, delay))
        except Exception:
            logger.debug("Could not schedule workspace cleanup for %s", conv_id)

        # Clean up todo manager + lock only if no other connections hold the lock
        lock = _conv_locks.get(conv_id)
        if lock and not lock.locked():
            _todo_managers.pop(conv_id, None)
            _conv_locks.pop(conv_id, None)
