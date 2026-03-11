"""
Persistent task system with dependency graph (from learn-claude-code s07 pattern).

Tasks survive context compaction, server restarts, and session disconnects.
Storage: workspace/.tasks/task_{id}.json
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_STATUSES = {"pending", "in_progress", "completed"}


@dataclass
class Task:
    id: int
    subject: str
    description: str = ""
    status: str = "pending"
    blocked_by: list[int] = field(default_factory=list)
    blocks: list[int] = field(default_factory=list)
    owner: str = ""
    active_form: str = ""
    metadata: dict = field(default_factory=dict)


def _task_to_dict(task: Task) -> dict:
    """Serialize to the on-disk JSON format (camelCase keys for consistency)."""
    return {
        "id": task.id,
        "subject": task.subject,
        "description": task.description,
        "status": task.status,
        "blockedBy": task.blocked_by,
        "blocks": task.blocks,
        "owner": task.owner,
        "activeForm": task.active_form,
        "metadata": task.metadata,
    }


def _dict_to_task(data: dict) -> Task:
    """Deserialize from on-disk JSON format."""
    return Task(
        id=data["id"],
        subject=data["subject"],
        description=data.get("description", ""),
        status=data.get("status", "pending"),
        blocked_by=data.get("blockedBy", []),
        blocks=data.get("blocks", []),
        owner=data.get("owner", ""),
        active_form=data.get("activeForm", ""),
        metadata=data.get("metadata", {}),
    )


class TaskManager:
    """File-persisted task system with dependency graph.

    Unlike TodoManager (in-memory, lost on disconnect), tasks persist to disk.
    Supports dependencies (blockedBy/blocks) with automatic cascade on completion.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self, workspace: Path) -> None:
        self.dir = workspace / ".tasks"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._next_id = self._compute_next_id()
        # In-memory reverse dependency map: task_id -> set of tasks that depend on it
        self._reverse_deps: dict[int, set[int]] = self._build_reverse_deps()

    def _compute_next_id(self) -> int:
        ids: list[int] = []
        for f in self.dir.glob("task_*.json"):
            try:
                ids.append(int(f.stem.split("_")[1]))
            except (IndexError, ValueError):
                pass
        return (max(ids) + 1) if ids else 1

    def _build_reverse_deps(self) -> dict[int, set[int]]:
        """Build in-memory reverse dependency map from disk.

        Maps dependency_id -> set of task_ids that have it in blockedBy.
        """
        rdeps: dict[int, set[int]] = {}
        for f in self.dir.glob("task_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                task_id = data["id"]
                for dep_id in data.get("blockedBy", []):
                    rdeps.setdefault(dep_id, set()).add(task_id)
            except (json.JSONDecodeError, OSError, KeyError):
                pass
        return rdeps

    def _path(self, task_id: int) -> Path:
        return self.dir / f"task_{task_id}.json"

    def _load_sync(self, task_id: int) -> Task:
        path = self._path(task_id)
        if not path.exists():
            raise ValueError(f"Task {task_id} not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        return _dict_to_task(data)

    def _save_sync(self, task: Task) -> None:
        self._path(task.id).write_text(
            json.dumps(_task_to_dict(task), indent=2), encoding="utf-8"
        )

    async def create(
        self, subject: str, description: str = "", active_form: str = ""
    ) -> Task:
        async with self._lock:
            task = Task(
                id=self._next_id,
                subject=subject,
                description=description,
                active_form=active_form or f"Working on: {subject}",
            )
            await asyncio.to_thread(self._save_sync, task)
            self._next_id += 1
            return task

    async def get(self, task_id: int) -> Task:
        return await asyncio.to_thread(self._load_sync, task_id)

    async def update(
        self,
        task_id: int,
        *,
        status: str | None = None,
        subject: str | None = None,
        description: str | None = None,
        active_form: str | None = None,
        owner: str | None = None,
        add_blocked_by: list[int] | None = None,
        add_blocks: list[int] | None = None,
        metadata: dict | None = None,
    ) -> Task:
        async with self._lock:
            task = await asyncio.to_thread(self._load_sync, task_id)

            # Deletion
            if status == "deleted":
                path = self._path(task_id)
                if path.exists():
                    path.unlink()
                task.status = "deleted"
                return task

            # Status update
            if status:
                if status not in VALID_STATUSES:
                    raise ValueError(
                        f"Invalid status: {status}. Valid: {', '.join(VALID_STATUSES)}"
                    )
                task.status = status
                if status == "completed":
                    await asyncio.to_thread(self._clear_dependency_sync, task_id)

            if subject is not None:
                task.subject = subject
            if description is not None:
                task.description = description
            if active_form is not None:
                task.active_form = active_form
            if owner is not None:
                task.owner = owner
            if metadata:
                task.metadata.update(
                    {k: v for k, v in metadata.items() if v is not None}
                )
                # Remove keys set to None
                for k, v in metadata.items():
                    if v is None:
                        task.metadata.pop(k, None)

            # Bidirectional dependency management
            if add_blocked_by:
                task.blocked_by = list(set(task.blocked_by + add_blocked_by))
                # Update reverse dependency map
                for dep_id in add_blocked_by:
                    self._reverse_deps.setdefault(dep_id, set()).add(task_id)
            if add_blocks:
                task.blocks = list(set(task.blocks + add_blocks))
                for blocked_id in add_blocks:
                    try:
                        blocked = self._load_sync(blocked_id)
                        if task_id not in blocked.blocked_by:
                            blocked.blocked_by.append(task_id)
                            self._save_sync(blocked)
                    except ValueError:
                        pass

            await asyncio.to_thread(self._save_sync, task)
            return task

    def _clear_dependency_sync(self, completed_id: int) -> None:
        """Remove completed_id from dependent tasks' blockedBy lists.

        Uses the in-memory reverse dependency map for O(k) instead of O(n) scan
        where k is the number of tasks that depend on completed_id.
        """
        dependents = self._reverse_deps.pop(completed_id, set())
        for task_id in dependents:
            f = self._path(task_id)
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if completed_id in data.get("blockedBy", []):
                    data["blockedBy"].remove(completed_id)
                    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to clear dependency in %s: %s", f, e)

    async def list_all(self) -> list[Task]:
        def _list_sync() -> list[Task]:
            tasks: list[Task] = []
            for f in sorted(self.dir.glob("task_*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("status") != "deleted":
                        tasks.append(_dict_to_task(data))
                except Exception:
                    pass
            return tasks

        return await asyncio.to_thread(_list_sync)

    async def scan_unclaimed(self) -> list[Task]:
        """Find pending, unblocked, unowned tasks (for autonomous agents)."""
        all_tasks = await self.list_all()
        return [
            t
            for t in all_tasks
            if t.status == "pending" and not t.owner and not t.blocked_by
        ]

    async def claim(self, task_id: int, owner: str) -> Task:
        """Atomically claim a task (set owner + status to in_progress)."""
        async with self._lock:
            task = await asyncio.to_thread(self._load_sync, task_id)
            if task.owner:
                raise ValueError(f"Task {task_id} already claimed by {task.owner}")
            task.owner = owner
            task.status = "in_progress"
            await asyncio.to_thread(self._save_sync, task)
            return task

    @staticmethod
    def render(tasks: list[Task]) -> str:
        if not tasks:
            return "No tasks."
        lines: list[str] = []
        for t in tasks:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }.get(t.status, "[?]")
            parts = [f"{marker} #{t.id}: {t.subject}"]
            if t.blocked_by:
                parts.append(f"(blocked by: {t.blocked_by})")
            if t.owner:
                parts.append(f"@{t.owner}")
            if t.status == "in_progress" and t.active_form:
                parts.append(f"<- {t.active_form}")
            lines.append(" ".join(parts))
        done = sum(1 for t in tasks if t.status == "completed")
        lines.append(f"\n({done}/{len(tasks)} completed)")
        return "\n".join(lines)

    def as_dicts(self, tasks: list[Task]) -> list[dict]:
        return [_task_to_dict(t) for t in tasks]
