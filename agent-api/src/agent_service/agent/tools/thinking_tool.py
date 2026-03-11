"""Thinking tool — lets the agent pause and reason mid-conversation.

A no-op tool that appends the thought to the conversation log without
obtaining new information or causing any side effects.  The value is in
giving the model a dedicated space for complex reasoning between tool
calls (see https://www.anthropic.com/engineering/claude-think-tool).
"""

from __future__ import annotations

DEFINITION = {
    "name": "think",
    "description": (
        "Use the tool to think about something. It will not obtain new "
        "information or change the database, but just append the thought "
        "to the log. Use it when complex reasoning or some cache memory "
        "is needed. Also use it to verify your work before finishing: "
        "review tool results for errors, check that the original request "
        "is fully addressed, and decide whether to fix issues or respond."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": "A thought to think about.",
            }
        },
        "required": ["thought"],
    },
}


async def run_think(args: dict) -> str:
    """No-op — the reasoning value is in the tool_use input itself."""
    return ""
