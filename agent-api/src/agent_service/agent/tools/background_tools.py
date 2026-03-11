"""Background task tools — fire-and-forget subprocess execution."""

from __future__ import annotations

from agent_service.agent.background_manager import BackgroundManager

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

BACKGROUND_RUN_DEFINITION = {
    "name": "background_run",
    "description": (
        "Run a shell command in the background. Returns a task_id immediately. "
        "Use for long-running commands (builds, tests, installs). "
        "Results are delivered automatically when complete."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run in the background",
            },
        },
        "required": ["command"],
    },
}

CHECK_BACKGROUND_DEFINITION = {
    "name": "check_background",
    "description": (
        "Check the status of background tasks. "
        "Omit task_id to list all background tasks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Specific task ID to check (optional)",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def run_background(args: dict, *, bg_manager: BackgroundManager) -> str:
    try:
        return await bg_manager.run(args["command"])
    except Exception as e:
        return f"Error: {e}"


async def run_check_background(args: dict, *, bg_manager: BackgroundManager) -> str:
    try:
        return await bg_manager.check(args.get("task_id"))
    except Exception as e:
        return f"Error: {e}"
