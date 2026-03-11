"""Task management tools — persistent task CRUD with dependency graph."""

from __future__ import annotations

import json
from agent_service.agent.task_manager import TaskManager, _task_to_dict

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TASK_CREATE_DEFINITION = {
    "name": "task_create",
    "description": (
        "Create a new task. Tasks persist to disk and survive context compaction. "
        "Use for tracking multi-step work."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Brief imperative title (e.g. 'Fix authentication bug')",
            },
            "description": {
                "type": "string",
                "description": "Detailed description of what needs to be done",
            },
            "activeForm": {
                "type": "string",
                "description": "Present continuous form for spinner (e.g. 'Fixing auth bug')",
            },
        },
        "required": ["subject"],
    },
}

TASK_GET_DEFINITION = {
    "name": "task_get",
    "description": "Get full details of a task by its ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "taskId": {"type": "integer", "description": "The task ID"},
        },
        "required": ["taskId"],
    },
}

TASK_UPDATE_DEFINITION = {
    "name": "task_update",
    "description": (
        "Update a task. Set status to 'completed' to finish, 'deleted' to remove. "
        "Use addBlockedBy/addBlocks to set dependencies between tasks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "taskId": {"type": "integer", "description": "The task ID to update"},
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed", "deleted"],
                "description": "New status",
            },
            "subject": {"type": "string", "description": "New title"},
            "description": {"type": "string", "description": "New description"},
            "activeForm": {"type": "string", "description": "New spinner text"},
            "owner": {"type": "string", "description": "Assigned agent name"},
            "addBlockedBy": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Task IDs that must complete before this one can start",
            },
            "addBlocks": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Task IDs that cannot start until this one completes",
            },
            "metadata": {
                "type": "object",
                "description": "Arbitrary metadata to merge (set key to null to delete)",
            },
        },
        "required": ["taskId"],
    },
}

TASK_LIST_DEFINITION = {
    "name": "task_list",
    "description": "List all tasks with their status, dependencies, and owners.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def run_task_create(args: dict, *, task_manager: TaskManager) -> str:
    try:
        task = await task_manager.create(
            subject=args["subject"],
            description=args.get("description", ""),
            active_form=args.get("activeForm", ""),
        )
        return json.dumps(_task_to_dict(task), indent=2)
    except Exception as e:
        return f"Error: {e}"


async def run_task_get(args: dict, *, task_manager: TaskManager) -> str:
    try:
        task = await task_manager.get(args["taskId"])
        return json.dumps(_task_to_dict(task), indent=2)
    except Exception as e:
        return f"Error: {e}"


async def run_task_update(args: dict, *, task_manager: TaskManager) -> str:
    try:
        task = await task_manager.update(
            task_id=args["taskId"],
            status=args.get("status"),
            subject=args.get("subject"),
            description=args.get("description"),
            active_form=args.get("activeForm"),
            owner=args.get("owner"),
            add_blocked_by=args.get("addBlockedBy"),
            add_blocks=args.get("addBlocks"),
            metadata=args.get("metadata"),
        )
        return json.dumps(_task_to_dict(task), indent=2)
    except Exception as e:
        return f"Error: {e}"


async def run_task_list(args: dict, *, task_manager: TaskManager) -> str:
    try:
        tasks = await task_manager.list_all()
        return task_manager.render(tasks)
    except Exception as e:
        return f"Error: {e}"
