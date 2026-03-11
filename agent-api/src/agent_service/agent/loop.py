"""
Core agentic loop — the heart of the system.

Pattern (same as reference v0-v4):
    while not done:
        response = model(messages, tools)
        if no tool calls: return
        execute tools, append results, continue

Streaming: text deltas are pushed via *send_event* callback.
Subagents: the task tool re-enters this loop with isolated context.

Provider-agnostic: the loop talks to LLMClient, not any specific SDK.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Callable

from agent_service.agent.background_manager import BackgroundManager
from agent_service.agent.message_bus import MessageBus
from agent_service.agent.protocol_tracker import ProtocolTracker
from agent_service.agent.task_manager import TaskManager
from agent_service.agent.teammate_manager import TeammateManager
from agent_service.agent.tools.background_tools import (
    BACKGROUND_RUN_DEFINITION,
    CHECK_BACKGROUND_DEFINITION,
    run_background,
    run_check_background,
)
from agent_service.agent.tools.team_tools import (
    BROADCAST_DEFINITION,
    CHECK_PROTOCOL_DEFINITION,
    LIST_TEAMMATES_DEFINITION,
    PLAN_REVIEW_DEFINITION,
    READ_INBOX_DEFINITION,
    SEND_MESSAGE_DEFINITION,
    SHUTDOWN_REQUEST_DEFINITION,
    SPAWN_TEAMMATE_DEFINITION,
    run_broadcast,
    run_check_protocol,
    run_list_teammates,
    run_plan_review,
    run_read_inbox,
    run_send_message,
    run_shutdown_request,
    run_spawn_teammate,
)
from agent_service.agent.tools.compact_tool import (
    COMPACT_SENTINEL,
    DEFINITION as COMPACT_DEF,
    run_compact,
)
from agent_service.agent.tools.plan_mode_tool import (
    ENTER_PLAN_SENTINEL,
    EXIT_PLAN_SENTINEL,
    ENTER_DEFINITION as ENTER_PLAN_DEF,
    EXIT_DEFINITION as EXIT_PLAN_DEF,
    run_enter_plan_mode,
    run_exit_plan_mode,
)
from agent_service.agent.tools.thinking_tool import (
    DEFINITION as THINK_DEF,
    run_think,
)
from agent_service.agent.tools.task_mgmt_tools import (
    TASK_CREATE_DEFINITION,
    TASK_GET_DEFINITION,
    TASK_LIST_DEFINITION,
    TASK_UPDATE_DEFINITION,
    run_task_create,
    run_task_get,
    run_task_list,
    run_task_update,
)

from agent_service.agent.llm import LLMClient, LLMResponse
from agent_service.agent.memory import MemoryManager
from agent_service.agent.prompt_loader import PromptLoader
from agent_service.agent.skill_loader import SkillLoader
from agent_service.agent.todo_manager import TodoManager
from agent_service.agent.tools.bash_tool import DEFINITION as BASH_DEF
from agent_service.agent.tools.bash_tool import run_bash
from agent_service.agent.tools.code_nav_tools import (
    FIND_REFERENCES_DEFINITION,
    LIST_SYMBOLS_DEFINITION,
    READ_FILE_RANGE_DEFINITION,
    SEARCH_CODE_DEFINITION,
    run_find_references,
    run_list_symbols,
    run_read_file_range,
    run_search_code,
)
from agent_service.agent.tools.file_tools import (
    EDIT_DEFINITION,
    READ_DEFINITION,
    WRITE_DEFINITION,
    run_edit_file,
    run_read_file,
    run_write_file,
)
from agent_service.agent.tools.registry import ToolRegistry
from agent_service.agent.tools.skill_tools import (
    LIST_SKILLS_DEFINITION,
    READ_SKILL_DEFINITION,
    run_list_skills,
    run_read_skill,
)
from agent_service.agent.tools.task_tool import (
    AGENT_TYPES,
    TASK_DEFINITION,
    get_agent_descriptions,
)
from agent_service.agent.tools.todo_tools import (
    TODO_ADD_DEFINITION,
    TODO_COMPLETE_DEFINITION,
    TODO_LIST_DEFINITION,
    TODOWRITE_DEFINITION,
    run_todo_add,
    run_todo_complete,
    run_todo_list,
    run_todo_write,
)
from agent_service.config import Settings

logger = logging.getLogger(__name__)

# Type alias for the event callback
SendEvent = Callable[[dict[str, Any]], Awaitable[None]]

# Read-only / side-effect-free tools that auto-approve (no user confirmation needed)
SAFE_TOOLS: frozenset[str] = frozenset({
    "think", "read_file", "read_file_range", "search_code",
    "list_symbols", "find_references", "list_skills", "read_skill",
    "todo_list", "task_list", "task_get",
    "check_background", "read_inbox", "list_teammates",
    "check_protocol", "compact",
    "enter_plan_mode", "exit_plan_mode",
})

APPROVAL_TIMEOUT = 300  # 5 minutes

# Tools allowed in plan mode (read-only exploration only)
PLAN_MODE_TOOLS: frozenset[str] = frozenset({
    "think", "read_file", "read_file_range", "search_code",
    "list_symbols", "find_references", "list_skills", "read_skill",
    "todo_list", "task_list", "task_get",
    "check_background", "read_inbox", "list_teammates",
    "check_protocol", "compact",
    "task_create", "task_update",
    "exit_plan_mode",
})


# ---------------------------------------------------------------------------
# Context compaction
# ---------------------------------------------------------------------------

COMPACT_KEEP_RECENT = 8  # keep last 8 messages (~4 turns) when compacting
MICRO_COMPACT_KEEP = 3  # keep last N tool results intact during micro-compaction

# --- Wrap-up & continuation constants ---
WRAPUP_TURNS_REMAINING = 3  # inject wrap-up hint this many turns before max
WRAPUP_HINT = (
    "\n\n[IMPORTANT: You are approaching the turn limit. "
    "Wrap up your work now and provide a final response with results. "
    "Do not start new tasks or tool calls unless critical to completing "
    "the current work.]"
)

FINAL_SUMMARY_PROMPT = (
    "You have reached the maximum number of turns. Please provide a concise "
    "final summary:\n"
    "1. What was accomplished\n"
    "2. Any remaining issues or unfinished work\n"
    "3. Suggested next steps if applicable"
)

MAX_CONTINUATIONS = 3  # max times to continue a truncated (max_tokens) response

PLAN_MODE_PROMPT = (
    "\n\n=== PLAN MODE (READ-ONLY) ===\n"
    "You are in PLAN MODE. You can ONLY use read-only tools to explore the "
    "codebase and design a step-by-step implementation plan.\n\n"
    "ALLOWED TOOLS: read_file, read_file_range, search_code, list_symbols, "
    "find_references, think, list_skills, read_skill, task_list, task_get, "
    "task_create, task_update, compact, exit_plan_mode.\n\n"
    "FORBIDDEN: bash, write_file, edit_file, or any tool that modifies state.\n\n"
    "WORKFLOW:\n"
    "1. Explore with search_code/list_symbols/find_references/read_file_range\n"
    "2. Identify patterns, conventions, and dependencies\n"
    "3. Design a step-by-step plan\n"
    "4. Present the plan in your final response using this format:\n\n"
    "## Plan: <Title>\n"
    "### Objective\n<Summary>\n"
    "### Steps\n1. **<Step>** -- <files>\n   <Description>\n"
    "### Files to Modify\n- `path/file` -- <reason>\n\n"
    "5. Call exit_plan_mode to present your plan for user approval.\n\n"
    "Your plan will be shown to the user for approval before execution."
)


def _micro_compact(messages: list[dict]) -> None:
    """Layer 1: Replace old tool_result content with placeholders (in-place).

    Keeps the most recent MICRO_COMPACT_KEEP tool results unchanged.
    Older results with content > 100 chars are replaced with a short label.
    Zero LLM cost — runs every turn before the API call.
    """
    # Collect all tool_result locations
    tool_results: list[tuple[int, int, dict]] = []
    for msg_idx, msg in enumerate(messages):
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for part_idx, part in enumerate(msg["content"]):
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_results.append((msg_idx, part_idx, part))

    if len(tool_results) <= MICRO_COMPACT_KEEP:
        return

    # Build tool_use_id -> tool_name map from assistant messages
    tool_name_map: dict[str, str] = {}
    for msg in messages:
        if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_name_map[block["id"]] = block["name"]

    # Replace old results in-place
    to_clear = tool_results[:-MICRO_COMPACT_KEEP]
    for _, _, result in to_clear:
        content = result.get("content", "")
        if isinstance(content, str) and len(content) > 100:
            tool_id = result.get("tool_use_id", "")
            tool_name = tool_name_map.get(tool_id, "unknown")
            result["content"] = f"[Previous: used {tool_name}]"


def _messages_to_summary_text(messages: list[dict]) -> str:
    """Render messages as compact text for the summariser."""
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


async def _compact_messages(
    messages: list[dict],
    llm: LLMClient,
    model: str,
    workspace: Path | None = None,
    temperature: float = 0.2,
) -> list[dict]:
    """
    Summarise older messages so the next API call fits in the context window.

    Strategy:
    - Save a transcript for audit/recovery (if workspace provided).
    - Keep the most recent COMPACT_KEEP_RECENT messages intact.
    - Summarise everything before that into a single exchange.
    - Return a valid alternating [user, assistant, ...] sequence.
    """
    if len(messages) <= COMPACT_KEEP_RECENT + 2:
        return messages  # too few to compact

    # Find a split point that lands on a user message so alternation is valid
    split_idx = max(len(messages) - COMPACT_KEEP_RECENT, 1)
    while split_idx < len(messages) and messages[split_idx]["role"] != "user":
        split_idx += 1

    if split_idx >= len(messages) - 2:
        return messages  # nothing useful to compact

    old = messages[:split_idx]
    recent = messages[split_idx:]

    # Layer 2: Save transcript before compaction for audit trail
    transcript_path: str | None = None
    if workspace:
        transcript_dir = workspace / ".transcripts"
        try:
            transcript_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            path = transcript_dir / f"transcript_{ts}.jsonl"

            def _write_transcript():
                with open(path, "w") as f:
                    for msg in messages:
                        f.write(json.dumps(msg, default=str) + "\n")

            await asyncio.to_thread(_write_transcript)
            transcript_path = str(path.relative_to(workspace))
            logger.info("Transcript saved: %s", transcript_path)
        except (OSError, IOError) as e:
            logger.warning("Transcript save failed (attempt 1): %s — retrying", e)
            try:
                await asyncio.to_thread(_write_transcript)
                transcript_path = str(path.relative_to(workspace))
            except (OSError, IOError) as e2:
                logger.error("Transcript save failed (attempt 2): %s", e2)

    summary_input = _messages_to_summary_text(old)

    try:
        resp = await llm.create(
            model=model,
            system="",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarise the following conversation history concisely. "
                        "Include: key decisions made, files modified, current task "
                        "state, and any important tool outputs. Be factual.\n\n"
                        + summary_input
                    ),
                }
            ],
            tools=[],
            max_tokens=1024,
            temperature=temperature,
        )
        summary = ""
        for block in resp.content:
            if isinstance(block, dict) and block.get("type") == "text":
                summary = block["text"]
                break
        if not summary:
            raise ValueError("No text block in compaction response")
    except Exception:
        logger.warning("LLM compaction failed, falling back to hard truncation")
        # Fallback: drop old messages, keep recent with a note
        truncated: list[dict] = [
            {
                "role": "user",
                "content": (
                    "[Earlier conversation context was dropped due to length. "
                    f"Approximately {len(old)} messages were removed.]"
                ),
            },
            {
                "role": "assistant",
                "content": "Understood. Continuing with available context.",
            },
        ]
        truncated.extend(recent)
        logger.info(
            "Hard-truncated %d messages → %d (dropped %d, kept %d recent)",
            len(messages),
            len(truncated),
            len(old),
            len(recent),
        )
        return truncated

    # Include transcript path in summary for reference
    transcript_note = ""
    if transcript_path:
        transcript_note = f"[Transcript: {transcript_path}]\n"

    compacted: list[dict] = [
        {
            "role": "user",
            "content": f"{transcript_note}[Conversation summary]\n{summary}",
        },
        {
            "role": "assistant",
            "content": (
                "Understood. I have the context from the conversation summary. "
                "Continuing with the task."
            ),
        },
    ]
    compacted.extend(recent)

    logger.info(
        "Compacted %d messages → %d (removed %d, kept %d recent)",
        len(messages),
        len(compacted),
        len(old),
        len(recent),
    )
    return compacted


# ---------------------------------------------------------------------------
# Agent context — bundles build_registry parameters
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Bundles workspace, managers, and config for tool registration.

    Reduces the parameter count of ``build_registry()`` from 17 to 1.
    Callers can construct this once and pass it through.
    """

    config: Settings
    workspace: Path
    todo: TodoManager
    skill_loader: SkillLoader
    send_event: SendEvent
    llm: Any  # LLMClient
    task_manager: TaskManager | None = None
    background_manager: BackgroundManager | None = None
    team_manager: TeammateManager | None = None
    message_bus: MessageBus | None = None
    protocol_tracker: ProtocolTracker | None = None
    include_task: bool = True
    depth: int = 0
    usage_tracker: dict[str, int] | None = None
    cancelled: asyncio.Event | None = None
    mcp_manager: Any | None = None


# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------


def build_registry(
    config: Settings,
    workspace: Path,
    todo: TodoManager,
    skill_loader: SkillLoader,
    send_event: SendEvent,
    llm: LLMClient,
    *,
    task_manager: TaskManager | None = None,
    background_manager: BackgroundManager | None = None,
    team_manager: TeammateManager | None = None,
    message_bus: MessageBus | None = None,
    protocol_tracker: ProtocolTracker | None = None,
    include_task: bool = True,
    depth: int = 0,
    usage_tracker: dict[str, int] | None = None,
    cancelled: asyncio.Event | None = None,
    mcp_manager: Any | None = None,
) -> ToolRegistry:
    """Create a ToolRegistry with all built-in tools wired up.

    Tip: for new code, construct an ``AgentContext`` and call
    ``build_registry_from_context(ctx)`` instead.
    """

    registry = ToolRegistry()

    # -- bash ---------------------------------------------------------------
    registry.register(
        "bash",
        BASH_DEF,
        partial(
            run_bash,
            workspace=workspace,
            timeout=config.bash_timeout,
            allowed_commands=config.allowed_commands or None,
        ),
    )

    # -- file tools ---------------------------------------------------------
    registry.register(
        "read_file", READ_DEFINITION, partial(run_read_file, workspace=workspace)
    )
    registry.register(
        "read_file_range",
        READ_FILE_RANGE_DEFINITION,
        partial(run_read_file_range, workspace=workspace),
    )
    registry.register(
        "search_code",
        SEARCH_CODE_DEFINITION,
        partial(run_search_code, workspace=workspace),
    )
    registry.register(
        "list_symbols",
        LIST_SYMBOLS_DEFINITION,
        partial(run_list_symbols, workspace=workspace),
    )
    registry.register(
        "find_references",
        FIND_REFERENCES_DEFINITION,
        partial(run_find_references, workspace=workspace),
    )
    registry.register(
        "write_file", WRITE_DEFINITION, partial(run_write_file, workspace=workspace)
    )
    registry.register(
        "edit_file", EDIT_DEFINITION, partial(run_edit_file, workspace=workspace)
    )

    # -- todo tools ---------------------------------------------------------
    registry.register(
        "todo_write", TODOWRITE_DEFINITION, partial(run_todo_write, todo=todo)
    )
    registry.register(
        "todo_add", TODO_ADD_DEFINITION, partial(run_todo_add, todo=todo)
    )
    registry.register(
        "todo_complete", TODO_COMPLETE_DEFINITION, partial(run_todo_complete, todo=todo)
    )
    registry.register(
        "todo_list", TODO_LIST_DEFINITION, partial(run_todo_list, todo=todo)
    )

    # -- skill tools --------------------------------------------------------
    registry.register(
        "list_skills",
        LIST_SKILLS_DEFINITION,
        partial(run_list_skills, skill_loader=skill_loader),
    )
    registry.register(
        "read_skill",
        READ_SKILL_DEFINITION,
        partial(run_read_skill, skill_loader=skill_loader),
    )

    # -- thinking tool ------------------------------------------------------
    registry.register("think", THINK_DEF, run_think)

    # -- compact tool -------------------------------------------------------
    registry.register("compact", COMPACT_DEF, run_compact)

    # -- plan mode tools ----------------------------------------------------
    registry.register("enter_plan_mode", ENTER_PLAN_DEF, run_enter_plan_mode)
    registry.register("exit_plan_mode", EXIT_PLAN_DEF, run_exit_plan_mode)

    # -- persistent task tools ----------------------------------------------
    if task_manager:
        registry.register(
            "task_create",
            TASK_CREATE_DEFINITION,
            partial(run_task_create, task_manager=task_manager),
        )
        registry.register(
            "task_get",
            TASK_GET_DEFINITION,
            partial(run_task_get, task_manager=task_manager),
        )
        registry.register(
            "task_update",
            TASK_UPDATE_DEFINITION,
            partial(run_task_update, task_manager=task_manager),
        )
        registry.register(
            "task_list",
            TASK_LIST_DEFINITION,
            partial(run_task_list, task_manager=task_manager),
        )

    # -- background tools ---------------------------------------------------
    if background_manager:
        registry.register(
            "background_run",
            BACKGROUND_RUN_DEFINITION,
            partial(run_background, bg_manager=background_manager),
        )
        registry.register(
            "check_background",
            CHECK_BACKGROUND_DEFINITION,
            partial(run_check_background, bg_manager=background_manager),
        )

    # -- team tools ---------------------------------------------------------
    if team_manager and message_bus:
        registry.register(
            "spawn_teammate",
            SPAWN_TEAMMATE_DEFINITION,
            partial(run_spawn_teammate, team_manager=team_manager),
        )
        registry.register(
            "list_teammates",
            LIST_TEAMMATES_DEFINITION,
            partial(run_list_teammates, team_manager=team_manager),
        )
        registry.register(
            "send_message",
            SEND_MESSAGE_DEFINITION,
            partial(run_send_message, bus=message_bus, sender="lead"),
        )
        registry.register(
            "read_inbox",
            READ_INBOX_DEFINITION,
            partial(run_read_inbox, bus=message_bus, name="lead"),
        )
        registry.register(
            "broadcast",
            BROADCAST_DEFINITION,
            partial(run_broadcast, bus=message_bus, team_manager=team_manager),
        )

        # Protocol tools (shutdown + plan approval)
        if protocol_tracker:
            registry.register(
                "shutdown_request",
                SHUTDOWN_REQUEST_DEFINITION,
                partial(run_shutdown_request, bus=message_bus, tracker=protocol_tracker),
            )
            registry.register(
                "check_protocol",
                CHECK_PROTOCOL_DEFINITION,
                partial(run_check_protocol, tracker=protocol_tracker),
            )
            registry.register(
                "plan_review",
                PLAN_REVIEW_DEFINITION,
                partial(run_plan_review, bus=message_bus, tracker=protocol_tracker),
            )

    # -- task tool (subagent) — only for main agent, max depth 2 -----------
    if include_task and depth < 2:

        async def _run_task(args: dict) -> str:
            remaining_budget: int | None = None
            if usage_tracker is not None:
                used = usage_tracker["input"] + usage_tracker["output"]
                remaining_budget = max(config.max_token_budget - used, 0)
            return await run_subagent(
                description=args["description"],
                prompt=args["prompt"],
                agent_type=args["agent_type"],
                config=config,
                workspace=workspace,
                todo=todo,
                skill_loader=skill_loader,
                send_event=send_event,
                llm=llm,
                depth=depth + 1,
                token_budget=remaining_budget,
                cancelled=cancelled,
            )

        registry.register("task", TASK_DEFINITION, _run_task)

    # -- MCP tools (client-mode) -------------------------------------------
    if mcp_manager:
        mcp_manager.register_tools(registry)

    return registry


def build_registry_from_context(ctx: AgentContext) -> ToolRegistry:
    """Convenience wrapper — build a ToolRegistry from an AgentContext."""
    return build_registry(
        config=ctx.config,
        workspace=ctx.workspace,
        todo=ctx.todo,
        skill_loader=ctx.skill_loader,
        send_event=ctx.send_event,
        llm=ctx.llm,
        task_manager=ctx.task_manager,
        background_manager=ctx.background_manager,
        team_manager=ctx.team_manager,
        message_bus=ctx.message_bus,
        protocol_tracker=ctx.protocol_tracker,
        include_task=ctx.include_task,
        depth=ctx.depth,
        usage_tracker=ctx.usage_tracker,
        cancelled=ctx.cancelled,
        mcp_manager=ctx.mcp_manager,
    )


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------


def build_system_prompt(
    workspace: Path,
    skill_loader: SkillLoader,
    *,
    agent_type: str | None = None,
    memory_content: str | None = None,
    preset: str | None = None,
    prompt_loader: PromptLoader | None = None,
    mcp_tool_descriptions: str | None = None,
) -> str:
    # Subagent mode — unchanged
    if agent_type and agent_type in AGENT_TYPES:
        cfg = AGENT_TYPES[agent_type]
        return (
            f"You are a {agent_type} subagent. Workspace: {workspace}\n\n"
            f"{cfg['prompt']}\n\n"
            "Complete the task and return a clear, concise summary."
        )

    # Load preset body (or fall back to hardcoded coding prompt)
    if prompt_loader and preset:
        body = prompt_loader.get_body(preset)
        if body:
            base = body.replace("{workspace}", str(workspace))
        else:
            base = (
                f"You are a coding agent. Workspace: {workspace}\n\n"
                f"Loop: plan -> act with tools -> report."
            )
    else:
        base = (
            f"You are a coding agent. Workspace: {workspace}\n\n"
            f"Loop: plan -> act with tools -> report."
        )

    # Append dynamic sections
    memory_section = ""
    if memory_content:
        memory_section = (
            f"**Memory from previous sessions** (use this context):\n"
            f"{memory_content}\n\n"
        )

    skills_section = (
        f"**Skills available** (invoke with read_skill when task matches):\n"
        f"{skill_loader.get_descriptions()}"
    )

    subagents_section = (
        f"**Subagents available** (invoke with task tool for focused subtasks):\n"
        f"{get_agent_descriptions()}"
    )

    mcp_section = ""
    if mcp_tool_descriptions:
        mcp_section = (
            f"\n\n**MCP tools available** (external tools from MCP servers):\n"
            f"{mcp_tool_descriptions}"
        )

    return f"{base}\n\n{memory_section}{skills_section}\n\n{subagents_section}{mcp_section}"


# ---------------------------------------------------------------------------
# Subagent execution
# ---------------------------------------------------------------------------


async def run_subagent(
    *,
    description: str,
    prompt: str,
    agent_type: str,
    config: Settings,
    workspace: Path,
    todo: TodoManager,
    skill_loader: SkillLoader,
    send_event: SendEvent,
    llm: LLMClient,
    depth: int,
    token_budget: int | None = None,
    cancelled: asyncio.Event | None = None,
) -> str:
    """Run a child agent loop with isolated context (v3 pattern)."""

    if agent_type not in AGENT_TYPES:
        return f"Error: Unknown agent type '{agent_type}'"

    subagent_id = uuid.uuid4().hex[:8]
    await send_event({
        "type": "subagent_start",
        "subagent_id": subagent_id,
        "task": description,
        "agent_type": agent_type,
    })

    # Build a filtered registry for the subagent
    sub_registry = build_registry(
        config=config,
        workspace=workspace,
        todo=todo,
        skill_loader=skill_loader,
        send_event=send_event,
        llm=llm,
        include_task=False,  # subagents can't spawn more subagents
        depth=depth,
    )

    # Determine allowed tools
    allowed = AGENT_TYPES[agent_type].get("tools", "*")
    if allowed == "*":
        exclude: set[str] = {"task"}  # everything except task
    else:
        all_names = set(sub_registry.get_names())
        exclude = all_names - set(allowed)

    tool_defs = sub_registry.get_definitions(exclude=exclude)

    sub_system = build_system_prompt(workspace, skill_loader, agent_type=agent_type)
    sub_messages: list[dict] = [{"role": "user", "content": prompt}]

    budget = token_budget if token_budget is not None else config.max_token_budget

    start = time.time()
    tool_count = 0
    total_input = 0
    total_output = 0
    response: LLMResponse | None = None

    for _ in range(config.max_turns):
        # Micro-compact subagent context too
        _micro_compact(sub_messages)

        # Check cancellation at start of each subagent turn
        if cancelled and cancelled.is_set():
            break

        response = await llm.create(
            model=config.subagent_model or config.model,
            system=sub_system,
            messages=sub_messages,
            tools=tool_defs,
            max_tokens=config.max_output_tokens,
            temperature=config.subagent_temperature,
        )

        total_input += response.input_tokens
        total_output += response.output_tokens

        if response.done:
            break

        # Execute tool calls in parallel
        async def _sub_exec(tc):
            return {
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": await sub_registry.execute(tc.name, tc.input),
            }

        results = list(
            await asyncio.gather(
                *[_sub_exec(tc) for tc in response.tool_calls]
            )
        )
        tool_count += len(response.tool_calls)

        sub_messages.append({"role": "assistant", "content": response.content})
        sub_messages.append({"role": "user", "content": results})

        # Budget check
        if total_input + total_output > budget:
            break

        # Auto-compact if approaching context limit
        if response.input_tokens > config.context_window * config.compact_threshold:
            sub_messages[:] = await _compact_messages(
                sub_messages, llm, config.compact_model or config.model,
                workspace=workspace, temperature=config.compact_temperature,
            )

    elapsed = time.time() - start

    # Extract final text
    summary = "(subagent returned no text)"
    if response:
        for block in response.content:
            if block.get("type") == "text":
                summary = block["text"]
                break

    await send_event(
        {
            "type": "subagent_end",
            "subagent_id": subagent_id,
            "summary": summary[:2000],
            "tool_count": tool_count,
            "elapsed": round(elapsed, 1),
            "agent_type": agent_type,
            "usage": {"input_tokens": total_input, "output_tokens": total_output},
        }
    )

    return summary


# ---------------------------------------------------------------------------
# Plan text extraction helper
# ---------------------------------------------------------------------------


def _extract_plan_text(messages: list[dict], since_index: int = 0) -> str:
    """Extract plan text from assistant messages starting at *since_index*.

    Concatenates all text blocks from every assistant message generated
    during plan mode so the full plan is captured even when the model
    spreads it across multiple turns interspersed with tool calls.
    """
    parts: list[str] = []
    for msg in messages[since_index:]:
        if msg["role"] != "assistant":
            continue
        content = msg["content"]
        if isinstance(content, str):
            if content.strip():
                parts.append(content.strip())
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block["text"].strip()
                    if text:
                        parts.append(text)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Remote MCP helper
# ---------------------------------------------------------------------------


def _attach_mcp_remote(llm: Any, params: list[dict]) -> None:
    """Walk the LLM wrapper chain to find AnthropicAdapter and set _mcp_servers.

    The chain is typically: AnthropicAdapter -> RetryingLLMClient -> TracingLLMClient.
    Each wrapper stores its inner client in ``_inner``.
    """
    current = llm
    while current is not None:
        if hasattr(current, "_mcp_servers"):
            current._mcp_servers = params
            return
        current = getattr(current, "_inner", None)


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------


async def agent_loop(
    *,
    messages: list[dict],
    config: Settings,
    llm: LLMClient,
    skill_loader: SkillLoader,
    todo: TodoManager,
    send_event: SendEvent,
    system_prompt: str | None = None,
    preset: str | None = None,
    prompt_loader: PromptLoader | None = None,
    cancelled: asyncio.Event | None = None,
    task_manager: TaskManager | None = None,
    background_manager: BackgroundManager | None = None,
    team_manager: TeammateManager | None = None,
    message_bus: MessageBus | None = None,
    protocol_tracker: ProtocolTracker | None = None,
    approval_queue: asyncio.Queue | None = None,
    plan_mode: bool = False,
    mcp_manager: Any | None = None,
) -> dict[str, int]:
    """
    Run the agentic loop. Streams events via *send_event*.

    Returns cumulative token usage: {"input_tokens": N, "output_tokens": N}
    """

    workspace = Path(config.workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    usage_tracker: dict[str, int] = {"input": 0, "output": 0}

    registry = build_registry(
        config=config,
        workspace=workspace,
        todo=todo,
        skill_loader=skill_loader,
        send_event=send_event,
        llm=llm,
        task_manager=task_manager,
        background_manager=background_manager,
        team_manager=team_manager,
        message_bus=message_bus,
        protocol_tracker=protocol_tracker,
        usage_tracker=usage_tracker,
        cancelled=cancelled,
        mcp_manager=mcp_manager,
    )

    # Read persistent memory if enabled
    memory_content: str | None = None
    if config.enable_memory:
        memory_content = MemoryManager(workspace).read() or None

    _plan_mode = plan_mode  # mutable local — can change mid-loop
    _plan_start_idx = 0  # index into messages when plan mode began
    _plan_ready_emitted = False  # track if plan_ready already sent by sentinel

    # MCP tool descriptions for system prompt injection
    mcp_tool_desc: str | None = None
    if mcp_manager:
        desc = mcp_manager.get_tool_descriptions()
        if desc:
            mcp_tool_desc = desc

    base_system = system_prompt or build_system_prompt(
        workspace,
        skill_loader,
        memory_content=memory_content,
        preset=preset or config.default_preset,
        prompt_loader=prompt_loader,
        mcp_tool_descriptions=mcp_tool_desc,
    )

    # Attach remote MCP server params to the AnthropicAdapter (if any)
    if mcp_manager and mcp_manager.has_remote_servers():
        _attach_mcp_remote(llm, mcp_manager.get_remote_server_params())

    def _get_system():
        return base_system + PLAN_MODE_PROMPT if _plan_mode else base_system

    def _get_tool_defs():
        if _plan_mode:
            excluded = set(registry.get_names()) - PLAN_MODE_TOOLS
            return registry.get_definitions(exclude=excluded)
        return registry.get_definitions(exclude={"exit_plan_mode"})

    system = _get_system()
    tool_defs = _get_tool_defs()

    tool_use_occurred = False
    continuation_count = 0

    total_input = 0
    total_output = 0
    last_input_tokens = 0

    for turn in range(config.max_turns):
        # Layer 1: micro-compact old tool results (zero LLM cost)
        _micro_compact(messages)

        # Drain background task notifications and inject before LLM call
        if background_manager:
            notifs = await background_manager.drain_notifications()
            if notifs:
                notif_text = "\n".join(
                    f"[bg:{n['task_id']}] {n['status']}: {n['result']}"
                    for n in notifs
                )
                messages.append({
                    "role": "user",
                    "content": (
                        f"<background-results>\n{notif_text}\n"
                        "</background-results>"
                    ),
                })
                messages.append({
                    "role": "assistant",
                    "content": "Noted background results.",
                })
                await send_event({
                    "type": "background_result",
                    "notifications": notifs,
                })

        # Drain lead's inbox (team messages from teammates)
        if message_bus:
            inbox = await message_bus.read_inbox("lead")
            if inbox:
                from dataclasses import asdict
                inbox_data = [asdict(m) for m in inbox]
                messages.append({
                    "role": "user",
                    "content": f"<inbox>{json.dumps(inbox_data, indent=2)}</inbox>",
                })
                messages.append({
                    "role": "assistant",
                    "content": "Noted inbox messages from teammates.",
                })

        # Check cancellation before LLM call
        if cancelled and cancelled.is_set():
            await send_event({"type": "error", "message": "Cancelled"})
            break

        # Inject wrap-up hint into system prompt near turn limit
        turn_system = system
        remaining_turns = config.max_turns - turn - 1
        if remaining_turns <= WRAPUP_TURNS_REMAINING and tool_use_occurred:
            turn_system = system + WRAPUP_HINT

        # Stream the model's response
        try:
            async with llm.stream(
                model=config.model,
                system=turn_system,
                messages=messages,
                tools=tool_defs,
                max_tokens=config.max_output_tokens,
                temperature=config.temperature,
            ) as stream:
                async for text in stream:
                    await send_event({"type": "text_delta", "content": text})

                response = await stream.get_response()
        except Exception as e:
            await send_event({"type": "error", "message": str(e)})
            break

        total_input += response.input_tokens
        total_output += response.output_tokens
        last_input_tokens = response.input_tokens
        usage_tracker["input"] = total_input
        usage_tracker["output"] = total_output

        # Content is already dicts — append directly
        messages.append({"role": "assistant", "content": response.content})

        # Handle truncated response: model hit max_tokens mid-generation.
        # The response looks "done" (no complete tool_use blocks) but the
        # model was actually cut off.  Ask it to continue.
        if (response.done
                and response.stop_reason == "max_tokens"
                and continuation_count < MAX_CONTINUATIONS):
            continuation_count += 1
            logger.info("Response truncated (max_tokens), requesting "
                        "continuation %d/%d", continuation_count,
                        MAX_CONTINUATIONS)
            messages.append({
                "role": "user",
                "content": (
                    "[Your previous response was cut off at the token limit. "
                    "Please continue from where you left off.]"
                ),
            })
            continue

        # No tool calls — agent has decided it's done.
        if response.done:
            break

        # Check cancellation before tool execution
        if cancelled and cancelled.is_set():
            await send_event({"type": "error", "message": "Cancelled"})
            break

        # --- Parallel tool execution ---
        if any(tc.name not in SAFE_TOOLS for tc in response.tool_calls):
            tool_use_occurred = True

        # 1. Emit all tool_call events upfront so the client sees intent
        for tc in response.tool_calls:
            await send_event(
                {"type": "tool_call", "tool": tc.name, "input": tc.input}
            )

        # 2. Approval gate — pause for user approval if any tool is unsafe
        unsafe_tools = [tc for tc in response.tool_calls if tc.name not in SAFE_TOOLS]
        denied_tool_names: set[str] = set()

        if approval_queue is not None and unsafe_tools:
            # Send approval request to client
            await send_event({
                "type": "tool_approval_request",
                "tools": [
                    {"name": tc.name, "input": tc.input, "id": tc.id}
                    for tc in unsafe_tools
                ],
            })

            # Wait for user decision (with cancellation + timeout)
            try:
                cancel_wait = asyncio.ensure_future(
                    cancelled.wait() if cancelled else asyncio.sleep(APPROVAL_TIMEOUT)
                )
                queue_wait = asyncio.ensure_future(approval_queue.get())

                done, pending = await asyncio.wait(
                    [cancel_wait, queue_wait],
                    timeout=APPROVAL_TIMEOUT,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for p in pending:
                    p.cancel()
                    try:
                        await p
                    except asyncio.CancelledError:
                        pass

                if not done or cancel_wait in done:
                    # Cancelled or timed out
                    if not done:
                        await send_event({
                            "type": "error",
                            "message": "Tool approval timed out",
                        })
                    break

                decision = queue_wait.result()
            except asyncio.CancelledError:
                break

            if decision == "auto_approve":
                # Disable approval for rest of session
                approval_queue = None
            elif decision == "deny":
                denied_tool_names = {tc.name for tc in unsafe_tools}
                await send_event({
                    "type": "tool_approval_result",
                    "decision": "denied",
                    "tools": [tc.name for tc in unsafe_tools],
                })

        # 3. Execute all tools concurrently (denied tools return denial message)
        async def _exec_one(tc):
            if tc.name in denied_tool_names:
                output = "User denied this tool call"
                await send_event(
                    {"type": "tool_result", "tool": tc.name, "result": output}
                )
            else:
                output = await registry.execute(tc.name, tc.input)
                # Stream result event as soon as this tool finishes
                preview = output[:2000] + "..." if len(output) > 2000 else output
                await send_event(
                    {"type": "tool_result", "tool": tc.name, "result": preview}
                )
            if tc.name in ("todo_write", "todo_add", "todo_complete"):
                await send_event({"type": "todo_update", "todos": todo.as_list()})
            if tc.name in ("task_create", "task_update", "task_list") and task_manager:
                tasks = await task_manager.list_all()
                await send_event({
                    "type": "task_update",
                    "tasks": task_manager.as_dicts(tasks),
                })
            return {
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": output,
            }

        results = list(
            await asyncio.gather(*[_exec_one(tc) for tc in response.tool_calls])
        )

        messages.append({"role": "user", "content": results})

        # Layer 3: manual compact — check if the compact tool was invoked
        compact_requested = any(
            isinstance(r.get("content"), str) and r["content"] == COMPACT_SENTINEL
            for r in results
        )
        if compact_requested:
            await send_event(
                {"type": "compact", "message": "Manual compaction triggered"}
            )
            messages[:] = await _compact_messages(
                messages, llm, config.compact_model or config.model,
                workspace=workspace, temperature=config.compact_temperature,
            )

        # enter_plan_mode sentinel — switch to plan mode mid-loop
        enter_plan = any(
            isinstance(r.get("content"), str)
            and r["content"] == ENTER_PLAN_SENTINEL
            for r in results
        )
        if enter_plan and not _plan_mode:
            _plan_mode = True
            _plan_start_idx = len(messages)
            system = _get_system()
            tool_defs = _get_tool_defs()
            await send_event({"type": "plan_mode_changed", "enabled": True})

        # exit_plan_mode sentinel — present plan for approval, break loop
        exit_plan = any(
            isinstance(r.get("content"), str)
            and r["content"] == EXIT_PLAN_SENTINEL
            for r in results
        )
        if exit_plan and _plan_mode:
            # Prefer the plan text from the tool call input parameter
            plan_text = ""
            for tc in response.tool_calls:
                if tc.name == "exit_plan_mode":
                    plan_text = (tc.input or {}).get("plan", "")
                    break
            # Fallback: extract from assistant messages
            if not plan_text:
                plan_text = _extract_plan_text(messages, _plan_start_idx)
            if plan_text:
                await send_event({"type": "plan_ready", "plan": plan_text})
            _plan_ready_emitted = True
            break

        # Budget check
        if total_input + total_output > config.max_token_budget:
            await send_event(
                {"type": "error", "message": "Token budget exceeded"}
            )
            break

        # --- Auto-compact if approaching context limit ---
        if response.input_tokens > config.context_window * config.compact_threshold:
            await send_event(
                {
                    "type": "compact",
                    "message": (
                        f"Compacting context ({response.input_tokens} tokens used)"
                    ),
                }
            )
            messages[:] = await _compact_messages(
                messages, llm, config.compact_model or config.model,
                workspace=workspace, temperature=config.compact_temperature,
            )

    else:
        # for-loop exhausted all turns without the model finishing on its own.
        # Give it one final chance to produce a text summary (no tools).
        if tool_use_occurred:
            logger.info("Max turns (%d) exhausted — forcing final summary",
                        config.max_turns)
            await send_event({
                "type": "text_delta",
                "content": (
                    "\n\n---\n*Turn limit reached — generating final "
                    "summary...*\n\n"
                ),
            })
            messages.append({"role": "user", "content": FINAL_SUMMARY_PROMPT})
            try:
                async with llm.stream(
                    model=config.model,
                    system=system,
                    messages=messages,
                    tools=[],  # no tools — force text-only response
                    max_tokens=config.max_output_tokens,
                    temperature=config.temperature,
                ) as stream:
                    async for text in stream:
                        await send_event({
                            "type": "text_delta", "content": text,
                        })
                    final_resp = await stream.get_response()
                total_input += final_resp.input_tokens
                total_output += final_resp.output_tokens
                messages.append({
                    "role": "assistant", "content": final_resp.content,
                })
            except Exception as e:
                logger.warning("Final summary generation failed: %s", e)
                await send_event({
                    "type": "error",
                    "message": "Turn limit reached; could not generate summary.",
                })

    # Emit plan_ready event if plan mode is active (fallback for natural loop end)
    if _plan_mode and messages and not _plan_ready_emitted:
        plan_text = _extract_plan_text(messages, _plan_start_idx)
        if plan_text:
            await send_event({"type": "plan_ready", "plan": plan_text})

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "last_input_tokens": last_input_tokens,
        "plan_mode": _plan_mode,
    }
