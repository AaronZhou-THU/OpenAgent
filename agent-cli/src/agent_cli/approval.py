"""Claude Code-style tool approval prompt."""

from __future__ import annotations

import asyncio
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

console = Console()


def _extract_detail(inp: dict[str, Any]) -> str:
    """Extract the most relevant input parameter for the detail line."""
    if not isinstance(inp, dict):
        return ""
    for key in ("file_path", "path", "notebook_path"):
        if key in inp:
            return str(inp[key])
    if "command" in inp:
        cmd = str(inp["command"])
        return cmd[:120] + ("\u2026" if len(cmd) > 120 else "")
    if "pattern" in inp:
        return f'pattern: "{inp["pattern"]}"'
    for key in ("query", "url", "skill"):
        if key in inp:
            v = str(inp[key])
            return v[:120] + ("\u2026" if len(v) > 120 else "")
    return ""


class ApprovalHandler:
    """Shows tool approval prompts and feeds decisions into the approval queue."""

    def __init__(self, approval_queue: asyncio.Queue) -> None:
        self._queue = approval_queue

    async def handle(self, event: dict[str, Any]) -> None:
        tools = event.get("tools", [])
        first = tools[0] if tools else {}
        name = first.get("name", "?") if isinstance(first, dict) else str(first)
        inp = first.get("input", {}) if isinstance(first, dict) else {}
        detail = _extract_detail(inp)

        console.print(
            f"\n  [bright_yellow]\u250c[/bright_yellow]"
            f" Allow tool: [bold]{escape(name)}[/bold]"
        )
        if detail:
            console.print(
                f"  [bright_yellow]\u2502[/bright_yellow]"
                f"  [dim]{escape(detail)}[/dim]"
            )

        # Run blocking prompt in a thread so we don't block the event loop
        answer = await asyncio.to_thread(
            Prompt.ask,
            "  [bright_yellow]\u2514[/bright_yellow]"
            " [bold]\\[Y][/bold]es  [bold]\\[n][/bold]o  [bold]\\[a][/bold]lways",
            choices=["y", "n", "a"],
            default="y",
        )

        if answer == "y":
            decision = "approve"
        elif answer == "a":
            decision = "auto_approve"
        else:
            decision = "deny"

        await self._queue.put(decision)
