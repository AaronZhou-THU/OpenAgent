"""
Background task execution — fire-and-forget async subprocesses with notification queue.

Adapted from learn-claude-code s08 pattern. Uses asyncio.Task (not threads)
for native integration with the event loop.

Results are injected into the agent's message stream via drain_notifications()
which is called at the top of each agent loop turn.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_LIMIT = 50_000  # max chars per task output


@dataclass
class BackgroundTask:
    id: str
    command: str
    status: str = "running"  # running | completed | timeout | error
    result: str | None = None


class BackgroundManager:
    """Manages fire-and-forget subprocess execution with async notification queue."""

    def __init__(self, workspace: Path, timeout: int = 300) -> None:
        self.workspace = workspace
        self.timeout = timeout
        self.tasks: dict[str, BackgroundTask] = {}
        self._notifications: list[dict] = []
        self._lock = asyncio.Lock()
        self._running: dict[str, asyncio.Task] = {}

    async def run(self, command: str) -> str:
        """Start a background subprocess. Returns task_id immediately."""
        task_id = uuid.uuid4().hex[:8]
        bg_task = BackgroundTask(id=task_id, command=command)
        self.tasks[task_id] = bg_task

        self._running[task_id] = asyncio.create_task(
            self._execute(task_id, command)
        )
        return f"Background task {task_id} started: {command[:80]}"

    async def _execute(self, task_id: str, command: str) -> None:
        """Execute subprocess and push result to notification queue."""
        bg_task = self.tasks[task_id]
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            output = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
            bg_task.status = "completed"
            bg_task.result = output[:OUTPUT_LIMIT] or "(no output)"
        except asyncio.TimeoutError:
            bg_task.status = "timeout"
            bg_task.result = f"Error: Timeout ({self.timeout}s)"
            # Try to kill the process
            try:
                proc.kill()  # type: ignore[possibly-undefined]
            except (OSError, ProcessLookupError) as e:
                logger.warning("Failed to kill timed-out process for task %s: %s", task_id, e)
        except Exception as e:
            bg_task.status = "error"
            bg_task.result = f"Error: {e}"

        # Push to notification queue
        async with self._lock:
            self._notifications.append({
                "task_id": task_id,
                "status": bg_task.status,
                "command": command[:80],
                "result": (bg_task.result or "(no output)")[:500],
            })
        logger.info("Background task %s finished: %s", task_id, bg_task.status)

    async def check(self, task_id: str | None = None) -> str:
        """Check status of one task or list all."""
        if task_id:
            t = self.tasks.get(task_id)
            if not t:
                return f"Error: Unknown background task {task_id}"
            return f"[{t.status}] {t.command[:60]}\n{t.result or '(still running)'}"
        if not self.tasks:
            return "No background tasks."
        lines: list[str] = []
        for tid, t in self.tasks.items():
            lines.append(f"{tid}: [{t.status}] {t.command[:60]}")
        return "\n".join(lines)

    async def drain_notifications(self) -> list[dict]:
        """Return and clear all pending completion notifications."""
        async with self._lock:
            notifs = list(self._notifications)
            self._notifications.clear()
        return notifs

    async def cancel_all(self) -> None:
        """Cancel all running background tasks. Called on session disconnect."""
        for task_id, asyncio_task in self._running.items():
            if not asyncio_task.done():
                asyncio_task.cancel()
                logger.debug("Cancelled background task %s", task_id)
