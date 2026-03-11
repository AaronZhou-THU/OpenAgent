"""Agent-initiated plan mode tools — lets the agent enter/exit plan mode on demand."""

from __future__ import annotations

ENTER_PLAN_SENTINEL = "__ENTER_PLAN_MODE__"
EXIT_PLAN_SENTINEL = "__PLAN_READY__"

ENTER_DEFINITION = {
    "name": "enter_plan_mode",
    "description": (
        "Enter plan mode to explore the codebase and design a step-by-step "
        "implementation plan before making changes. Use this proactively when "
        "facing complex tasks that involve multiple files, architectural decisions, "
        "or unclear requirements. In plan mode you can only use read-only tools "
        "to explore — no writes or execution. Call exit_plan_mode when your plan "
        "is ready for user approval."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

EXIT_DEFINITION = {
    "name": "exit_plan_mode",
    "description": (
        "Signal that your plan is complete and ready for user review. "
        "You MUST include the full plan text in the 'plan' parameter. "
        "The plan will be presented to the user for approval before "
        "execution begins."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": (
                    "The complete plan in markdown format. Include all steps, "
                    "file names, and implementation details."
                ),
            },
        },
        "required": ["plan"],
    },
}


async def run_enter_plan_mode(args: dict) -> str:
    """Returns a sentinel — the agent loop detects this and switches to plan mode."""
    return ENTER_PLAN_SENTINEL


async def run_exit_plan_mode(args: dict) -> str:
    """Returns a sentinel — the agent loop detects this and presents the plan."""
    return EXIT_PLAN_SENTINEL
