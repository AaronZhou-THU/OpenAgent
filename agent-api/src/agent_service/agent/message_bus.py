"""
Async message bus for agent team communication.

Adapted from learn-claude-code s09. Uses asyncio.Queue (not JSONL files)
as the primary messaging mechanism for zero-latency in-process delivery.
Optional JSONL persistence for crash recovery.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_MSG_TYPES = {
    "message",
    "broadcast",
    "shutdown_request",
    "shutdown_response",
    "plan_approval_request",
    "plan_approval_response",
}


@dataclass
class TeamMessage:
    type: str
    sender: str
    content: str
    timestamp: float = field(default_factory=time.time)
    extra: dict = field(default_factory=dict)


class MessageBus:
    """Async message bus with per-agent queues.

    Each agent has its own asyncio.Queue. Messages are delivered instantly
    in-process. Optional JSONL persistence for durability.

    Agents can ``await notify_event(name)`` instead of polling —
    the event is set whenever a message is delivered to that agent.
    """

    def __init__(self, persist_dir: Path | None = None) -> None:
        self._queues: dict[str, asyncio.Queue[TeamMessage]] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._persist_dir = persist_dir
        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _append_file(path: Path, line: str) -> None:
        with open(path, "a") as f:
            f.write(line)

    def _get_queue(self, name: str) -> asyncio.Queue[TeamMessage]:
        if name not in self._queues:
            self._queues[name] = asyncio.Queue()
        return self._queues[name]

    def notify_event(self, name: str) -> asyncio.Event:
        """Get or create an asyncio.Event for the given agent.

        The event is *set* whenever a message is delivered to this agent,
        allowing ``await event.wait()`` with timeout instead of polling.
        """
        if name not in self._events:
            self._events[name] = asyncio.Event()
        return self._events[name]

    async def send(
        self,
        sender: str,
        to: str,
        content: str,
        msg_type: str = "message",
        extra: dict | None = None,
    ) -> str:
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: Invalid type '{msg_type}'. Valid: {sorted(VALID_MSG_TYPES)}"

        msg = TeamMessage(
            type=msg_type,
            sender=sender,
            content=content,
            extra=extra or {},
        )
        queue = self._get_queue(to)
        await queue.put(msg)

        # Signal the recipient's notify event (event-driven wakeup)
        event = self._events.get(to)
        if event:
            event.set()

        # Optional: persist to JSONL (non-blocking)
        if self._persist_dir:
            path = self._persist_dir / f"{to}.jsonl"
            try:
                line = json.dumps(asdict(msg)) + "\n"
                await asyncio.to_thread(self._append_file, path, line)
            except (OSError, IOError) as e:
                logger.warning("Failed to persist message to %s: %s", path, e)

        logger.debug("Message sent: %s -> %s (%s)", sender, to, msg_type)
        return f"Sent {msg_type} to {to}"

    async def read_inbox(self, name: str) -> list[TeamMessage]:
        """Drain all messages from an agent's queue (non-blocking)."""
        queue = self._get_queue(name)
        messages: list[TeamMessage] = []
        while not queue.empty():
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        # Clear persistence file after drain (non-blocking)
        if self._persist_dir:
            path = self._persist_dir / f"{name}.jsonl"
            if path.exists():
                try:
                    await asyncio.to_thread(path.write_text, "")
                except (OSError, IOError) as e:
                    logger.warning("Failed to clear inbox file %s: %s", path, e)

        return messages

    async def broadcast(
        self, sender: str, content: str, recipients: list[str]
    ) -> str:
        count = 0
        for name in recipients:
            if name != sender:
                await self.send(sender, name, content, "broadcast")
                count += 1
        return f"Broadcast to {count} teammates"
