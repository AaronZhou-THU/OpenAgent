"""Todo tools — todo_add, todo_complete, todo_list (v2 pattern)."""

from __future__ import annotations

from agent_service.agent.todo_manager import TodoManager

# ---------------------------------------------------------------------------
# TodoWrite — replaces the entire list (same as v2)
# ---------------------------------------------------------------------------

TODOWRITE_DEFINITION = {
    "name": "todo_write",
    "description": "Update the full task list. Use to plan and track progress on multi-step tasks.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "Complete list of tasks (replaces existing)",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Task description",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                            "description": "Task status",
                        },
                        "activeForm": {
                            "type": "string",
                            "description": "Present tense action, e.g. 'Reading files'",
                        },
                    },
                    "required": ["content", "status", "activeForm"],
                },
            }
        },
        "required": ["items"],
    },
}


async def run_todo_write(args: dict, *, todo: TodoManager) -> str:
    try:
        return todo.update(args["items"])
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Convenience tools: todo_add, todo_complete, todo_list
# ---------------------------------------------------------------------------

TODO_ADD_DEFINITION = {
    "name": "todo_add",
    "description": "Add a single task to the todo list.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Task description"},
            "activeForm": {
                "type": "string",
                "description": "Present tense action, e.g. 'Adding tests'",
            },
        },
        "required": ["content", "activeForm"],
    },
}


async def run_todo_add(args: dict, *, todo: TodoManager) -> str:
    try:
        if len(todo.items) >= 20:
            return "Error: Max 20 todos"
        new_item = {
            "content": args["content"],
            "status": "pending",
            "activeForm": args["activeForm"],
        }
        todo.items.append(new_item)
        return todo.render()
    except Exception as e:
        return f"Error: {e}"


TODO_COMPLETE_DEFINITION = {
    "name": "todo_complete",
    "description": "Mark a task as completed by its content (exact match).",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Exact content of the task to mark as completed",
            }
        },
        "required": ["content"],
    },
}


async def run_todo_complete(args: dict, *, todo: TodoManager) -> str:
    content = args["content"]
    for item in todo.items:
        if item["content"] == content:
            item["status"] = "completed"
            return todo.render()
    return f"Error: Todo not found: {content}"


TODO_LIST_DEFINITION = {
    "name": "todo_list",
    "description": "Show the current task list.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


async def run_todo_list(args: dict, *, todo: TodoManager) -> str:
    return todo.render()
