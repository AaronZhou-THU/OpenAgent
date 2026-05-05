"""
Teammate manager — spawn and manage persistent named agent teammates.

Adapted from learn-claude-code s09-s11. Each teammate runs its own
agent loop in an asyncio.Task with inbox draining.

Config persisted to workspace/.team/config.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Callable

from agent_service.agent.llm import LLMClient, LLMResponse
from agent_service.agent.message_bus import MessageBus, TeamMessage
from agent_service.agent.task_manager import TaskManager
from agent_service.agent.tools.bash_tool import DEFINITION as BASH_DEF, run_bash
from agent_service.agent.tools.file_tools import (
    EDIT_DEFINITION,
    READ_DEFINITION,
    WRITE_DEFINITION,
    run_edit_file,
    run_read_file,
    run_write_file,
)
from agent_service.agent.tools.registry import ToolRegistry
from agent_service.agent.tools.thinking_tool import DEFINITION as THINK_DEF, run_think
from agent_service.config import Settings

logger = logging.getLogger(__name__)

SendEvent = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class TeammateConfig:
    name: str
    role: str
    status: str  # working | idle | shutdown


class TeammateManager:
    """Manages persistent named agent teammates.

    Each teammate runs its own simplified agent loop in an asyncio.Task
    with inbox draining before each LLM call.
    """

    def __init__(
        self,
        workspace: Path,
        bus: MessageBus,
        llm: LLMClient,
        config: Settings,
        send_event: SendEvent,
        task_manager: TaskManager | None = None,
    ) -> None:
        self.workspace = workspace
        self.team_dir = workspace / ".team"
        self.team_dir.mkdir(parents=True, exist_ok=True)
        self.bus = bus
        self.llm = llm
        self.config = config
        self.send_event = send_event
        self._task_manager = task_manager
        self._teammates: dict[str, TeammateConfig] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._team_config = self._load_config()

        # Restore teammate state from config
        for member in self._team_config.get("members", []):
            name = member["name"]
            self._teammates[name] = TeammateConfig(
                name=name,
                role=member.get("role", "worker"),
                status=member.get("status", "idle"),
            )

    def _load_config(self) -> dict:
        path = self.team_dir / "config.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"team_name": "default", "members": []}

    def _save_config(self) -> None:
        path = self.team_dir / "config.json"
        path.write_text(
            json.dumps(self._team_config, indent=2), encoding="utf-8"
        )

    def _update_member_status(self, name: str, status: str) -> None:
        if name in self._teammates:
            self._teammates[name].status = status
        members = self._team_config.setdefault("members", [])
        for m in members:
            if m["name"] == name:
                m["status"] = status
                break
        self._save_config()

    async def spawn(self, name: str, role: str, prompt: str) -> str:
        """Spawn a teammate as an asyncio.Task running its own agent loop."""
        if name in self._teammates and self._teammates[name].status == "working":
            return f"Error: '{name}' is currently working"

        teammate = TeammateConfig(name=name, role=role, status="working")
        self._teammates[name] = teammate

        # Update persisted config
        members = self._team_config.setdefault("members", [])
        existing = next((m for m in members if m["name"] == name), None)
        if existing:
            existing["status"] = "working"
            existing["role"] = role
        else:
            members.append({"name": name, "role": role, "status": "working"})
        self._save_config()

        # Launch teammate loop
        self._tasks[name] = asyncio.create_task(
            self._teammate_loop(name, role, prompt)
        )

        await self.send_event({
            "type": "teammate_status",
            "name": name,
            "role": role,
            "status": "working",
        })

        return f"Spawned '{name}' (role: {role})"

    def _build_teammate_registry(self, name: str) -> ToolRegistry:
        """Build a tool registry for a teammate (limited tools, no spawning)."""
        registry = ToolRegistry()

        registry.register(
            "bash", BASH_DEF,
            partial(run_bash, workspace=self.workspace,
                    timeout=self.config.bash_timeout,
                    allowed_commands=self.config.allowed_commands or None),
        )
        registry.register(
            "read_file", READ_DEFINITION,
            partial(run_read_file, workspace=self.workspace),
        )
        registry.register(
            "write_file", WRITE_DEFINITION,
            partial(run_write_file, workspace=self.workspace),
        )
        registry.register(
            "edit_file", EDIT_DEFINITION,
            partial(run_edit_file, workspace=self.workspace),
        )

        # Think tool
        registry.register("think", THINK_DEF, run_think)

        # Messaging tools
        async def _send_msg(args: dict) -> str:
            return await self.bus.send(
                sender=name,
                to=args["to"],
                content=args["content"],
                msg_type=args.get("msg_type", "message"),
            )

        async def _read_inbox(args: dict) -> str:
            msgs = await self.bus.read_inbox(name)
            if not msgs:
                return "(inbox empty)"
            return json.dumps([asdict(m) for m in msgs], indent=2)

        registry.register("send_message", {
            "name": "send_message",
            "description": "Send a message to another teammate or the lead.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient name"},
                    "content": {"type": "string", "description": "Message content"},
                    "msg_type": {
                        "type": "string",
                        "description": "Message type (default: message)",
                        "enum": ["message", "shutdown_response", "plan_approval_request"],
                    },
                },
                "required": ["to", "content"],
            },
        }, _send_msg)

        registry.register("read_inbox", {
            "name": "read_inbox",
            "description": "Read and drain all messages from your inbox.",
            "input_schema": {"type": "object", "properties": {}},
        }, _read_inbox)

        # Idle tool — signals transition from WORK to IDLE phase
        async def _idle(args: dict) -> str:
            return "Entering idle phase. Will poll for new tasks."

        registry.register("idle", {
            "name": "idle",
            "description": (
                "Signal that you have no more work to do. "
                "Enters idle phase where you'll poll for inbox messages "
                "and unclaimed tasks on the task board."
            ),
            "input_schema": {"type": "object", "properties": {}},
        }, _idle)

        return registry

    async def _teammate_loop(self, name: str, role: str, prompt: str) -> None:
        """Teammate agent loop with WORK/IDLE state machine.

        WORK phase: standard agent loop with inbox draining.
        IDLE phase: poll inbox + task board every 5s for 60s, then shutdown.

        Adapted from learn-claude-code s11 autonomous pattern.
        """
        team_name = self._team_config.get("team_name", "default")
        sys_prompt = (
            f"You are '{name}', role: {role}, workspace: {self.workspace}. "
            f"Use send_message to communicate with teammates and the lead. "
            f"Use the idle tool when you have no more work to do. "
            f"Complete your task and report results via send_message."
        )

        messages: list[dict] = [{"role": "user", "content": prompt}]
        registry = self._build_teammate_registry(name)
        tool_defs = registry.get_definitions()

        try:
            while True:
                # === WORK PHASE ===
                self._update_member_status(name, "working")
                idle_requested = False

                for _ in range(self.config.max_turns):
                    # Drain inbox before each LLM call
                    inbox = await self.bus.read_inbox(name)
                    for msg in inbox:
                        if msg.type == "shutdown_request":
                            logger.info("Teammate '%s' received shutdown", name)
                            self._update_member_status(name, "shutdown")
                            await self.send_event({
                                "type": "teammate_status",
                                "name": name,
                                "status": "shutdown",
                            })
                            return

                        messages.append({
                            "role": "user",
                            "content": (
                                f"<inbox-message>{json.dumps(asdict(msg))}"
                                "</inbox-message>"
                            ),
                        })
                        messages.append({
                            "role": "assistant",
                            "content": "Noted inbox message.",
                        })

                    try:
                        response = await self.llm.create(
                            model=self.config.teammate_model or self.config.model,
                            system=sys_prompt,
                            messages=messages,
                            tools=tool_defs,
                            max_tokens=self.config.max_output_tokens,
                            temperature=self.config.teammate_temperature,
                            thinking_enabled=self.config.thinking_enabled,
                            thinking_effort=self.config.thinking_effort,
                        )
                    except Exception:
                        logger.exception("Teammate '%s' LLM call failed", name)
                        idle_requested = True
                        break

                    messages.append({"role": "assistant", "content": response.content})

                    if response.done:
                        idle_requested = True
                        break

                    # Execute tool calls
                    results: list[dict] = []
                    for block in response.content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        if block["name"] == "idle":
                            idle_requested = True
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": "Entering idle phase. Will poll for new tasks.",
                            })
                        else:
                            output = await registry.execute(block["name"], block["input"])
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": output,
                            })

                    if results:
                        messages.append({"role": "user", "content": results})

                    if idle_requested:
                        break

                if not idle_requested:
                    # Max turns reached without idle — just stop
                    break

                # === IDLE PHASE ===
                self._update_member_status(name, "idle")
                await self.send_event({
                    "type": "teammate_status",
                    "name": name,
                    "status": "idle",
                })

                POLL_INTERVAL = 5
                IDLE_TIMEOUT = 60
                polls = IDLE_TIMEOUT // max(POLL_INTERVAL, 1)
                resume = False

                # Use event-driven notification for faster wakeup on message delivery
                notify = self.bus.notify_event(name)
                notify.clear()

                for _ in range(polls):
                    # Wait for event or poll interval (event fires on message delivery)
                    try:
                        await asyncio.wait_for(notify.wait(), timeout=POLL_INTERVAL)
                    except asyncio.TimeoutError:
                        pass
                    notify.clear()

                    # Check inbox
                    inbox = await self.bus.read_inbox(name)
                    if inbox:
                        for msg in inbox:
                            if msg.type == "shutdown_request":
                                self._update_member_status(name, "shutdown")
                                await self.send_event({
                                    "type": "teammate_status",
                                    "name": name,
                                    "status": "shutdown",
                                })
                                return
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"<inbox-message>{json.dumps(asdict(msg))}"
                                    "</inbox-message>"
                                ),
                            })
                            messages.append({
                                "role": "assistant",
                                "content": "Noted inbox message.",
                            })
                        resume = True
                        break

                    # Check task board (if task_manager available)
                    if self._task_manager:
                        unclaimed = await self._task_manager.scan_unclaimed()
                        if unclaimed:
                            task = unclaimed[0]
                            try:
                                await self._task_manager.claim(task.id, name)
                                task_prompt = (
                                    f"<auto-claimed>Task #{task.id}: {task.subject}\n"
                                    f"{task.description}</auto-claimed>"
                                )
                                # Re-inject identity if context was compressed
                                if len(messages) <= 3:
                                    messages.insert(0, {
                                        "role": "user",
                                        "content": (
                                            f"<identity>You are '{name}', role: {role}, "
                                            f"team: {team_name}. Continue your work."
                                            "</identity>"
                                        ),
                                    })
                                    messages.insert(1, {
                                        "role": "assistant",
                                        "content": f"I am {name}. Continuing.",
                                    })
                                messages.append({"role": "user", "content": task_prompt})
                                messages.append({
                                    "role": "assistant",
                                    "content": f"Claimed task #{task.id}. Working on it.",
                                })
                                resume = True
                                break
                            except ValueError:
                                pass  # task already claimed by someone else

                if not resume:
                    # Timeout — shutdown
                    logger.info("Teammate '%s' idle timeout, shutting down", name)
                    self._update_member_status(name, "shutdown")
                    await self.send_event({
                        "type": "teammate_status",
                        "name": name,
                        "status": "shutdown",
                    })
                    return

                # Resume to WORK phase
                self._update_member_status(name, "working")
                await self.send_event({
                    "type": "teammate_status",
                    "name": name,
                    "status": "working",
                })

        except asyncio.CancelledError:
            logger.info("Teammate '%s' was cancelled", name)
        except Exception:
            logger.exception("Teammate '%s' loop failed", name)
        finally:
            tc = self._teammates.get(name)
            if tc and tc.status not in ("shutdown", "idle"):
                self._update_member_status(name, "idle")
                await self.send_event({
                    "type": "teammate_status",
                    "name": name,
                    "status": "idle",
                })

    def list_all(self) -> str:
        if not self._teammates:
            return "No teammates."
        team_name = self._team_config.get("team_name", "default")
        lines = [f"Team: {team_name}"]
        for name, tc in self._teammates.items():
            lines.append(f"  {name} ({tc.role}): {tc.status}")
        return "\n".join(lines)

    def member_names(self) -> list[str]:
        return [
            name for name, tc in self._teammates.items()
            if tc.status != "shutdown"
        ]

    async def shutdown_all(self) -> None:
        """Cancel all running teammate tasks. Called on session disconnect."""
        for name, task in self._tasks.items():
            if not task.done():
                task.cancel()
                logger.debug("Cancelled teammate '%s'", name)
        # Wait briefly for tasks to clean up
        if self._tasks:
            done, pending = await asyncio.wait(
                self._tasks.values(), timeout=5.0
            )
            for t in pending:
                t.cancel()
