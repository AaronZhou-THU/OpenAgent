"""Manual context compaction tool — lets the agent trigger compression on demand."""

from __future__ import annotations

COMPACT_SENTINEL = "__COMPACT_REQUESTED__"

DEFINITION = {
    "name": "compact",
    "description": (
        "Trigger manual conversation compression. Use when context is getting "
        "large, you want to reset focus, or before switching to a different task. "
        "Optionally specify what to preserve in the summary."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "description": "What to preserve in the summary (optional)",
            }
        },
    },
}


async def run_compact(args: dict) -> str:
    """Returns a sentinel — the agent loop detects this and triggers compaction."""
    return COMPACT_SENTINEL
