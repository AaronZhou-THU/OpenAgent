"""Slash command dispatch and handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from rich.console import Console
from rich.markup import escape
from rich.table import Table

if TYPE_CHECKING:
    from agent_cli.config import CLIConfig
    from agent_cli.cost import CostTracker
    from agent_cli.session import SessionStore

console = Console()

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CommandResult:
    """Result of a slash command execution."""

    handled: bool = True
    quit: bool = False
    clear: bool = False
    new_session_id: str | None = None
    compact: bool = False
    plan_mode: bool | None = None  # None=no change, True=enter, False=exit
    teams: bool | None = None      # None=no change, True=enable, False=disable
    approval: bool | None = None   # None=no change, True=enable, False=disable
    thinking: bool | None = None   # None=no change, True=enable, False=disable
    thinking_effort: str | None = None


# ---------------------------------------------------------------------------
# Command context — passed to every handler
# ---------------------------------------------------------------------------


@dataclass
class CommandContext:
    """Dependencies injected into slash command handlers."""

    config: CLIConfig
    cost_tracker: CostTracker
    session_store: SessionStore
    session_id: str
    model: str
    preset: str
    thinking_enabled: bool = False
    thinking_effort: str = "high"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_commands: dict[str, tuple[str, Callable]] = {}


def register(name: str, description: str):
    """Decorator to register a slash command handler."""
    def decorator(fn: Callable[[CommandContext, list[str]], Awaitable[CommandResult]]):
        _commands[name] = (description, fn)
        return fn
    return decorator


def get_commands() -> dict[str, str]:
    """Return {name: description} for all registered commands."""
    return {name: desc for name, (desc, _) in _commands.items()}


async def dispatch(
    raw_input: str,
    ctx: CommandContext,
) -> CommandResult | None:
    """If *raw_input* starts with ``/``, dispatch to the matching handler.

    Returns ``None`` if the input is not a slash command.
    Returns a ``CommandResult`` if a command was executed (even if unknown).
    """
    if not raw_input.startswith("/"):
        return None

    parts = raw_input.split()
    name = parts[0][1:]  # strip leading /
    args = parts[1:]

    if name not in _commands:
        console.print(f"  [yellow]Unknown command: /{escape(name)}[/yellow]")
        console.print("  [dim]Type /help for available commands[/dim]")
        return CommandResult(handled=True)

    _, handler = _commands[name]
    return await handler(ctx, args)


# ---------------------------------------------------------------------------
# Built-in commands
# ---------------------------------------------------------------------------


@register("help", "List available commands")
async def _cmd_help(ctx: CommandContext, args: list[str]) -> CommandResult:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column(style="dim")
    for name, desc in get_commands().items():
        table.add_row(f"/{name}", desc)
    console.print()
    console.print(table)
    console.print()
    return CommandResult()


@register("clear", "Clear messages and start a new session")
async def _cmd_clear(ctx: CommandContext, args: list[str]) -> CommandResult:
    new_meta = ctx.session_store.create(preset=ctx.preset, model=ctx.model)
    console.print("  [dim]Session cleared.[/dim]")
    return CommandResult(clear=True, new_session_id=new_meta.id)


@register("compact", "Trigger manual context compaction")
async def _cmd_compact(ctx: CommandContext, args: list[str]) -> CommandResult:
    return CommandResult(compact=True)


@register("model", "Show or switch the current model")
async def _cmd_model(ctx: CommandContext, args: list[str]) -> CommandResult:
    if not args:
        console.print(f"  [dim]Current model:[/dim] [bold]{escape(ctx.model)}[/bold]")
    else:
        # The actual switch is handled by app.py reading the result
        new_model = args[0]
        console.print(f"  [dim]Model switched to[/dim] [bold]{escape(new_model)}[/bold]")
        # Return new model name via a custom attribute
        result = CommandResult()
        result._new_model = new_model  # type: ignore[attr-defined]
        return result
    return CommandResult()


@register("history", "List recent sessions")
async def _cmd_history(ctx: CommandContext, args: list[str]) -> CommandResult:
    sessions = ctx.session_store.list_sessions(limit=20)
    if not sessions:
        console.print("  [dim]No saved sessions.[/dim]")
        return CommandResult()

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Model", style="dim")
    table.add_column("Messages", style="dim", justify="right")
    table.add_column("Updated", style="dim")

    for s in sessions:
        updated = s.updated_at[:10] if s.updated_at else ""
        table.add_row(
            s.id,
            s.title or "(untitled)",
            s.model,
            str(s.message_count),
            updated,
        )

    console.print()
    console.print(table)
    console.print()
    return CommandResult()


@register("resume", "Resume a past session (optionally by ID)")
async def _cmd_resume(ctx: CommandContext, args: list[str]) -> CommandResult:
    if args:
        session_id = args[0]
    else:
        latest = ctx.session_store.get_latest()
        if not latest:
            console.print("  [yellow]No sessions to resume.[/yellow]")
            return CommandResult()
        session_id = latest.id

    meta = ctx.session_store.get_session(session_id)
    if not meta:
        console.print(f"  [yellow]Session {escape(session_id)} not found.[/yellow]")
        return CommandResult()

    console.print(
        f"  [dim]Resuming session[/dim] [bold]{escape(meta.id)}[/bold]"
        f"  [dim]{escape(meta.title or '(untitled)')}[/dim]"
    )
    return CommandResult(new_session_id=session_id)


@register("cost", "Show cumulative session cost")
async def _cmd_cost(ctx: CommandContext, args: list[str]) -> CommandResult:
    ct = ctx.cost_tracker
    line = ct.format_usage_line(ct.total_input, ct.total_output)
    console.print(f"\n  [bright_black]{line}[/bright_black]\n")
    return CommandResult()


@register("quit", "Exit the CLI")
async def _cmd_quit(ctx: CommandContext, args: list[str]) -> CommandResult:
    return CommandResult(quit=True)


@register("exit", "Exit the CLI")
async def _cmd_exit(ctx: CommandContext, args: list[str]) -> CommandResult:
    return CommandResult(quit=True)


@register("plan", "Enter plan mode (read-only exploration)")
async def _cmd_plan(ctx: CommandContext, args: list[str]) -> CommandResult:
    console.print("  [bold bright_cyan]Entering plan mode[/bold bright_cyan]")
    console.print("  [dim]Agent will explore and plan without modifying files.[/dim]")
    return CommandResult(plan_mode=True)


@register("execute", "Exit plan mode and execute the plan")
async def _cmd_execute(ctx: CommandContext, args: list[str]) -> CommandResult:
    console.print("  [bold bright_cyan]Exiting plan mode[/bold bright_cyan]")
    console.print("  [dim]Agent now has full tool access.[/dim]")
    return CommandResult(plan_mode=False)


@register("teams", "Toggle team mode (on/off)")
async def _cmd_teams(ctx: CommandContext, args: list[str]) -> CommandResult:
    if not args or args[0].lower() not in ("on", "off"):
        console.print("  [dim]Usage: /teams on | /teams off[/dim]")
        return CommandResult()
    enable = args[0].lower() == "on"
    label = "[bold green]on[/bold green]" if enable else "[dim]off[/dim]"
    console.print(f"  [bold medium_purple3]Teams {label}[/bold medium_purple3]")
    return CommandResult(teams=enable)


@register("approval", "Toggle tool approval (on/off)")
async def _cmd_approval(ctx: CommandContext, args: list[str]) -> CommandResult:
    if not args or args[0].lower() not in ("on", "off"):
        console.print("  [dim]Usage: /approval on | /approval off[/dim]")
        return CommandResult()
    enable = args[0].lower() == "on"
    label = "[bold green]on[/bold green]" if enable else "[dim]off[/dim]"
    console.print(f"  [bold orange3]Approval {label}[/bold orange3]")
    return CommandResult(approval=enable)


@register("thinking", "Show or set provider thinking (on/off/high/max)")
async def _cmd_thinking(ctx: CommandContext, args: list[str]) -> CommandResult:
    if not args:
        enabled = "[bold green]on[/bold green]" if ctx.thinking_enabled else "[dim]off[/dim]"
        console.print(
            f"  [bright_black]Thinking[/bright_black] {enabled}"
            f"  [dim]level: {escape(ctx.thinking_effort)}[/dim]"
        )
        return CommandResult()

    arg = args[0].lower()
    if arg in ("on", "enable", "enabled", "true"):
        console.print(
            f"  [bright_black]Thinking[/bright_black] [bold green]on[/bold green]"
            f"  [dim]level: {escape(ctx.thinking_effort)}[/dim]"
        )
        return CommandResult(thinking=True)
    if arg in ("off", "disable", "disabled", "false"):
        console.print("  [bright_black]Thinking[/bright_black] [dim]off[/dim]")
        return CommandResult(thinking=False)
    if arg in ("high", "max"):
        console.print(
            f"  [bright_black]Thinking[/bright_black] [bold green]on[/bold green]"
            f"  [dim]level: {escape(arg)}[/dim]"
        )
        return CommandResult(thinking=True, thinking_effort=arg)

    console.print("  [dim]Usage: /thinking on | /thinking off | /thinking high | /thinking max[/dim]")
    return CommandResult()
