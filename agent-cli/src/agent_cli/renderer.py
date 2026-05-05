"""Claude Code-style terminal renderer for agent events."""

from __future__ import annotations

import json
import sys
import time
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.status import Status
from rich.text import Text

if TYPE_CHECKING:
    from agent_cli.approval import ApprovalHandler
    from agent_cli.cost import CostTracker

console = Console()
_streaming = False


# ---------------------------------------------------------------------------
# Streaming markdown renderer
# ---------------------------------------------------------------------------


class StreamingRenderer:
    """Accumulates streaming tokens and renders formatted markdown."""

    def __init__(self) -> None:
        self._buffer: list[str] = []

    def feed(self, text: str) -> None:
        """Accumulate text tokens."""
        self._buffer.append(text)

    def finish(self) -> None:
        """Render accumulated text as formatted markdown."""
        if self._buffer:
            text = "".join(self._buffer).rstrip()
            self._buffer = []
            if text:
                console.print(Markdown(text))

    def reset(self) -> None:
        """Reset state for a new response."""
        self._buffer = []


# ---------------------------------------------------------------------------
# Elapsed-time renderable (Claude Code-style)
# ---------------------------------------------------------------------------


class ElapsedText:
    """A Rich renderable that shows a message with live-updating elapsed time.

    Because ``Status`` (via ``Live``) calls ``__rich_console__`` on every
    refresh frame (~12.5 fps), the elapsed counter updates automatically
    without any extra asyncio task or explicit ``update()`` call.

    Example output: ``Thinking (12s)``
    """

    def __init__(self, message: str, start: float | None = None) -> None:
        self._message = message
        self._start = start or time.monotonic()

    @property
    def message(self) -> str:
        return self._message

    @message.setter
    def message(self, value: str) -> None:
        self._message = value

    def __rich_console__(self, console, options):  # type: ignore[override]
        elapsed = int(time.monotonic() - self._start)
        if elapsed > 0:
            yield Text(f"{self._message} ({elapsed}s)", style="dim")
        else:
            yield Text(self._message, style="dim")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _end_stream() -> None:
    global _streaming
    if _streaming:
        sys.stdout.write("\n")
        sys.stdout.flush()
        _streaming = False


def _summarize_input(name: str, data: Any) -> str:
    """Extract the most relevant parameter for compact display."""
    if isinstance(data, str):
        return data[:120] + ("\u2026" if len(data) > 120 else "")
    if not isinstance(data, dict):
        return str(data)[:120]

    # File path (most tools)
    for key in ("file_path", "path", "notebook_path"):
        if key in data:
            return str(data[key])

    # Command
    if "command" in data:
        cmd = str(data["command"])
        return cmd[:120] + ("\u2026" if len(cmd) > 120 else "")

    # Search patterns
    if "pattern" in data:
        p = str(data["pattern"])
        target = data.get("path") or data.get("glob", "")
        return f'"{p}"  {target}' if target else f'"{p}"'

    # Queries / URLs / skills
    for key in ("query", "url", "skill"):
        if key in data:
            v = str(data[key])
            return v[:120] + ("\u2026" if len(v) > 120 else "")

    # Content preview
    if "content" in data:
        c = str(data["content"])
        return c[:80] + ("\u2026" if len(c) > 80 else "")

    # Fallback: first param
    for key, val in data.items():
        v = str(val)
        if len(v) > 100:
            v = v[:97] + "\u2026"
        return f"{key}={v}"

    return ""


# ---------------------------------------------------------------------------
# Tool activity labels (Claude Code-style contextual status)
# ---------------------------------------------------------------------------

_TOOL_ACTIVITY: dict[str, str] = {
    "bash": "Running command",
    "execute_command": "Running command",
    "read_file": "Reading {path}",
    "read": "Reading {path}",
    "write_file": "Writing {path}",
    "edit_file": "Editing {path}",
    "write": "Writing {path}",
    "edit": "Editing {path}",
    "grep": "Searching files",
    "glob": "Searching files",
    "search": "Searching",
    "web_search": "Searching the web",
    "web_fetch": "Fetching page",
    "task": "Researching",
    "think": "Thinking deeper",
}


def _tool_activity_label(name: str, data: Any) -> str:
    """Return a human-readable activity label for a tool call."""
    template = _TOOL_ACTIVITY.get(name.lower(), "Working")
    if "{path}" in template:
        path = ""
        if isinstance(data, dict):
            for key in ("file_path", "path", "notebook_path"):
                if key in data:
                    path = str(data[key])
                    # Show just the filename, not the full path
                    if "/" in path:
                        path = path.rsplit("/", 1)[-1]
                    break
        if path:
            return template.replace("{path}", path)
        return template.replace(" {path}", "").replace("{path}", "")
    return template


def _result_lines(result: Any, max_lines: int = 6, max_len: int = 2000) -> list[str]:
    """Convert a tool result into truncated display lines."""
    if isinstance(result, str):
        text = result
    else:
        try:
            text = json.dumps(result, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(result)

    if len(text) > max_len:
        text = text[:max_len]

    lines = text.rstrip().split("\n")
    if len(lines) > max_lines:
        remaining = len(lines) - max_lines + 1
        return lines[: max_lines - 1] + [f"\u2026 {remaining} more lines"]
    return lines


# ---------------------------------------------------------------------------
# Event handler factory
# ---------------------------------------------------------------------------


def make_send_event(
    approval_handler: ApprovalHandler | None = None,
    cost_tracker: CostTracker | None = None,
):
    """Return an async send_event callback with Claude Code-style output.

    Optionally accepts a *cost_tracker* for enhanced usage display on ``done``.
    """
    renderer = StreamingRenderer()
    spinner: Status | None = None
    elapsed_text: ElapsedText | None = None
    _turn_start: float | None = None
    _subagent_count: int = 0
    _provider_thinking: list[str] = []
    _provider_thinking_effort = ""
    _provider_thinking_rendered = False

    def _stop_spinner():
        nonlocal spinner, elapsed_text
        if spinner is not None:
            spinner.stop()
            spinner = None
            elapsed_text = None

    def _start_spinner(message: str):
        """Start a new spinner with elapsed time, reusing the turn start time."""
        nonlocal spinner, elapsed_text, _turn_start
        _stop_spinner()
        if _turn_start is None:
            _turn_start = time.monotonic()
        elapsed_text = ElapsedText(message, start=_turn_start)
        spinner = Status(elapsed_text, spinner="dots", console=console)
        spinner.start()

    def _update_spinner_message(message: str):
        """Update the spinner message without restarting (preserves elapsed time)."""
        if elapsed_text is not None:
            elapsed_text.message = message

    def _flush_provider_thinking():
        nonlocal _provider_thinking_rendered
        if _provider_thinking_rendered:
            return
        text = "".join(_provider_thinking).rstrip()
        if not text:
            return
        _stop_spinner()
        label = "Thinking"
        if _provider_thinking_effort:
            label = f"{label} · {_provider_thinking_effort}"
        console.print(f"\n  [bright_black]{escape(label)}[/bright_black]")
        console.print(Text(text, style="dim"))
        _provider_thinking_rendered = True

    async def send_event(event: dict[str, Any]) -> None:
        global _streaming
        nonlocal spinner, _turn_start, _subagent_count
        nonlocal _provider_thinking_effort, _provider_thinking_rendered
        etype = event.get("type", "")

        # ── Thinking spinner ──
        if etype == "thinking":
            content = event.get("content", "")
            if content:
                _provider_thinking.append(str(content))
                _provider_thinking_effort = event.get("effort", "") or _provider_thinking_effort
                _flush_provider_thinking()
                return

            _turn_start = None  # reset for new turn
            _start_spinner("Thinking")
            return

        # ── Provider thinking stream ──
        if etype == "thinking_delta":
            content = event.get("content", "")
            if content:
                _provider_thinking.append(str(content))
                _provider_thinking_effort = event.get("effort", "") or _provider_thinking_effort
                if spinner is not None:
                    _update_spinner_message("Thinking")
                else:
                    _start_spinner("Thinking")
            return

        # ── Streaming text ──
        if etype == "text_delta":
            _flush_provider_thinking()
            if spinner is not None:
                _update_spinner_message("Generating")
            else:
                _start_spinner("Generating")
            text = event.get("content", "")
            renderer.feed(text)
            return

        # Finish any streaming + stop spinner before block events
        _flush_provider_thinking()
        _stop_spinner()
        renderer.finish()
        _end_stream()

        # ── Tool call ──
        if etype == "tool_call":
            name = event.get("tool", "?")
            data = event.get("input", {})
            summary = _summarize_input(name, data)
            console.print(
                f"\n  [bold dodger_blue2]\u25c6 {escape(name)}[/bold dodger_blue2]"
                f"  [dim]{escape(summary)}[/dim]"
            )
            # Restart spinner with contextual activity label
            label = _tool_activity_label(name, data)
            _start_spinner(label)

        # ── Tool result ──
        elif etype == "tool_result":
            lines = _result_lines(event.get("result", ""))
            if lines:
                console.print(f"  [dim]\u23bf[/dim]  [dim]{escape(lines[0])}[/dim]")
                for ln in lines[1:]:
                    console.print(f"     [dim]{escape(ln)}[/dim]")
            else:
                console.print(f"  [dim]\u23bf[/dim]  [dim](no output)[/dim]")
            # Restart spinner — next event will be another tool_call, text_delta, or done
            _start_spinner("Thinking")

        # ── Tool approval ──
        elif etype == "tool_approval_request":
            if approval_handler:
                await approval_handler.handle(event)

        # ── Subagent start ──
        elif etype == "subagent_start":
            _subagent_count += 1
            task = event.get("task", "")
            agent_type = event.get("agent_type", "")
            type_label = f" [bright_black]({agent_type})[/bright_black]" if agent_type else ""
            console.print(
                f"\n  [bold medium_purple3]\u25b8 Subagent{type_label}[/bold medium_purple3]"
                f"  [dim]{escape(task[:150])}[/dim]"
            )
            # Show a working spinner while subagent(s) run
            spinner_msg = f"Researching ({_subagent_count} subagents)" if _subagent_count > 1 else "Researching"
            _start_spinner(spinner_msg)

        # ── Subagent end ──
        elif etype == "subagent_end":
            _subagent_count = max(0, _subagent_count - 1)
            summary = event.get("summary", "")
            tc = event.get("tool_count", 0)
            elapsed = event.get("elapsed", 0)
            trunc = summary[:140] + "\u2026" if len(summary) > 140 else summary
            console.print(
                f"  [dim]\u23bf[/dim]  [dim]{escape(trunc)}[/dim]"
            )
            console.print(
                f"     [bright_black]{tc} tools \u00b7 {elapsed:.1f}s[/bright_black]"
            )
            # Continue spinner if more subagents running, else resume Thinking
            if _subagent_count > 0:
                spinner_msg = f"Researching ({_subagent_count} subagents)" if _subagent_count > 1 else "Researching"
                _start_spinner(spinner_msg)
            else:
                _start_spinner("Thinking")

        # ── Todo updates ──
        elif etype == "todo_update":
            items = event.get("todos", [])
            if items:
                console.print(f"\n  [bold sky_blue3]Todos[/bold sky_blue3]")
                for item in items:
                    s = item.get("status", "pending")
                    c = escape(item.get("content", ""))
                    a = item.get("activeForm", "")
                    if s == "completed":
                        console.print(f"  [green]\u2713[/green] [dim]{c}[/dim]")
                    elif s == "in_progress":
                        console.print(f"  [yellow]\u25cf[/yellow] {escape(a) if a else c}")
                    else:
                        console.print(f"  [bright_black]\u25cb[/bright_black] [dim]{c}[/dim]")

        # ── Task updates ──
        elif etype == "task_update":
            items = event.get("tasks", [])
            if items:
                console.print(f"\n  [bold sky_blue3]Tasks[/bold sky_blue3]")
                for t in items:
                    s = t.get("status", "pending")
                    tid = t.get("id", "?")
                    subj = escape(t.get("subject", ""))
                    a = t.get("active_form", "")
                    tag = f"[bright_black]#{tid}[/bright_black]"
                    if s == "completed":
                        console.print(f"  [green]\u2713[/green] {tag} [dim]{subj}[/dim]")
                    elif s == "in_progress":
                        console.print(f"  [yellow]\u25cf[/yellow] {tag} {escape(a) if a else subj}")
                    elif s == "deleted":
                        console.print(f"  [red]\u2717[/red] {tag} [dim strikethrough]{subj}[/dim strikethrough]")
                    else:
                        console.print(f"  [bright_black]\u25cb[/bright_black] {tag} [dim]{subj}[/dim]")

        # ── Context compaction ──
        elif etype == "compact":
            msg = event.get("message", "Context compacted")
            console.print(f"\n  [dim italic]\u2500\u2500 {escape(msg)} \u2500\u2500[/dim italic]")

        # ── Background result ──
        elif etype == "background_result":
            for n in event.get("notifications", []):
                lines = _result_lines(n, max_lines=4)
                if lines:
                    console.print(
                        f"\n  [bold steel_blue1]\u25c7 Background[/bold steel_blue1]"
                        f"  [dim]{escape(lines[0])}[/dim]"
                    )
                    for ln in lines[1:]:
                        console.print(f"     [dim]{escape(ln)}[/dim]")

        # ── Error ──
        elif etype == "error":
            msg = event.get("message", "Unknown error")
            console.print(f"\n  [bold red]\u2717 Error[/bold red]  {escape(msg)}")

        # ── Interrupted ──
        elif etype == "interrupted":
            usage = event.get("usage", {})
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            if inp or out:
                if cost_tracker:
                    last_inp = usage.get("last_input_tokens")
                    line = cost_tracker.format_usage_line(inp, out, last_inp)
                    console.print(
                        f"\n  [yellow]── Interrupted ──[/yellow]"
                        f"  [bright_black]{line}[/bright_black]"
                    )
                else:
                    console.print(
                        f"\n  [yellow]── Interrupted ──[/yellow]"
                        f"  [bright_black]{inp:,} input · {out:,} output[/bright_black]"
                    )
            else:
                console.print("\n  [yellow]── Interrupted ──[/yellow]")
            renderer.reset()

        # ── Done ──
        elif etype == "done":
            usage = event.get("usage", {})
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            if inp or out:
                if cost_tracker:
                    last_inp = usage.get("last_input_tokens")
                    line = cost_tracker.format_usage_line(inp, out, last_inp)
                    console.print(
                        f"\n  [bright_black]\u2500\u2500\u2500\u2500\u2500\u2500 "
                        f"{line} "
                        f"\u2500\u2500\u2500\u2500\u2500\u2500[/bright_black]"
                    )
                else:
                    console.print(
                        f"\n  [bright_black]\u2500\u2500\u2500\u2500\u2500\u2500 "
                        f"{inp:,} input \u00b7 {out:,} output "
                        f"\u2500\u2500\u2500\u2500\u2500\u2500[/bright_black]"
                    )

        # ── Teammate status ──
        elif etype == "teammate_status":
            name = event.get("name", "?")
            role = event.get("role", "")
            status = event.get("status", "")
            console.print(
                f"  [bold medium_purple3]{escape(name)}[/bold medium_purple3]"
                f"  [dim]({escape(role)})[/dim] {escape(status)}"
            )

        # ── Plan mode events ──
        elif etype == "plan_mode_changed":
            enabled = event.get("enabled", False)
            if enabled:
                console.print(
                    "\n  [bold bright_cyan]\u25c6 Plan mode enabled[/bold bright_cyan]"
                    "  [dim]read-only exploration[/dim]"
                )
            else:
                console.print(
                    "\n  [bold bright_cyan]\u25c6 Plan mode disabled[/bold bright_cyan]"
                    "  [dim]full tool access[/dim]"
                )

        # ── Teams toggle ──
        elif etype == "teams_changed":
            enabled = event.get("enabled", False)
            if enabled:
                console.print(
                    "\n  [bold medium_purple3]\u25c6 Teams enabled[/bold medium_purple3]"
                    "  [dim]teammate agents available[/dim]"
                )
            else:
                console.print(
                    "\n  [bold medium_purple3]\u25c6 Teams disabled[/bold medium_purple3]"
                )

        # ── Approval toggle ──
        elif etype == "approval_changed":
            enabled = event.get("enabled", False)
            if enabled:
                console.print(
                    "\n  [bold orange3]\u25c6 Tool approval enabled[/bold orange3]"
                    "  [dim]dangerous tools require approval[/dim]"
                )
            else:
                console.print(
                    "\n  [bold orange3]\u25c6 Tool approval disabled[/bold orange3]"
                )

        elif etype == "plan_ready":
            console.print(
                "\n  [bright_cyan]\u2501\u2501\u2501[/bright_cyan]"
                " [bold bright_cyan]Plan ready for review[/bold bright_cyan]"
                " [bright_cyan]\u2501\u2501\u2501[/bright_cyan]"
            )

        elif etype == "plan_approved":
            console.print(
                "  [bold green]\u2713 Plan approved \u2014 switching to execution[/bold green]"
            )

        elif etype == "plan_rejected":
            fb = event.get("feedback", "")
            if fb:
                console.print(
                    f"  [yellow]\u2717 Plan rejected[/yellow]  [dim]{escape(fb[:120])}[/dim]"
                )
            else:
                console.print("  [yellow]\u2717 Plan rejected[/yellow]")

        # ── Tool approval result ──
        elif etype == "tool_approval_result":
            decision = event.get("decision", "?")
            if decision in ("approve", "auto_approve"):
                label = "Auto-approved" if decision == "auto_approve" else "Approved"
                console.print(f"  [green]\u2713 {label}[/green]")
            else:
                console.print(f"  [red]\u2717 Denied[/red]")

        # Reset renderer for next turn on 'done'
        if etype == "done":
            _turn_start = None
            _subagent_count = 0
            _provider_thinking.clear()
            _provider_thinking_effort = ""
            _provider_thinking_rendered = False
            renderer.reset()

    return send_event
