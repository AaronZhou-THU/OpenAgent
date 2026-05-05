"""Core REPL loop — initializes the agent and runs an interactive session."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _find_env_file() -> str | None:
    """Look for .env in CWD."""
    candidate = Path.cwd() / ".env"
    if candidate.exists():
        return str(candidate)
    return None


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------


def _sanitize_interrupted_messages(messages: list[dict]) -> None:
    """Strip orphaned tool_use blocks from the last assistant message.

    When the agent is interrupted mid-tool-call, the assistant message may
    contain tool_use blocks without matching tool_result in the next message.
    The LLM API rejects this.  We strip those blocks in-place.
    """
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg["role"] != "assistant" or not isinstance(msg.get("content"), list):
            continue
        tool_use_ids = {
            b["id"]
            for b in msg["content"]
            if isinstance(b, dict) and b.get("type") == "tool_use"
        }
        if not tool_use_ids:
            break
        # Check if next message has matching tool_results
        next_msg = messages[i + 1] if i + 1 < len(messages) else None
        has_results = False
        if (
            next_msg
            and next_msg["role"] == "user"
            and isinstance(next_msg.get("content"), list)
        ):
            result_ids = {
                b.get("tool_use_id")
                for b in next_msg["content"]
                if isinstance(b, dict) and b.get("type") == "tool_result"
            }
            has_results = bool(tool_use_ids & result_ids)
        if not has_results:
            cleaned = [
                b for b in msg["content"]
                if not (isinstance(b, dict) and b.get("type") == "tool_use")
            ]
            if not cleaned:
                cleaned = [{"type": "text", "text": "(interrupted)"}]
            msg["content"] = cleaned
        break  # only fix the last assistant message


async def run_repl(args) -> None:
    """Main interactive loop."""
    # Load .env early so Settings picks it up
    env_file = _find_env_file()
    if env_file:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)

    # Late imports — after env is loaded
    from agent_service.agent.llm import RetryingLLMClient, build_raw_llm_client
    from agent_service.agent.loop import agent_loop
    from agent_service.agent.memory import MemoryManager, analyze_session
    from agent_service.agent.prompt_loader import PromptLoader
    from agent_service.agent.skill_loader import SkillLoader
    from agent_service.agent.task_manager import TaskManager
    from agent_service.agent.background_manager import BackgroundManager
    from agent_service.agent.todo_manager import TodoManager
    from agent_service.agent.message_bus import MessageBus
    from agent_service.agent.protocol_tracker import ProtocolTracker
    from agent_service.agent.teammate_manager import TeammateManager
    from agent_service.config import Settings

    from agent_cli.approval import ApprovalHandler
    from agent_cli.commands import CommandContext, dispatch
    from agent_cli.config import CLIConfig, ensure_dirs, load_config
    from agent_cli.cost import CostTracker
    from agent_cli.renderer import make_send_event
    from agent_cli.session import SessionStore

    # ---- CLI config ----
    cli_config = load_config()
    ensure_dirs(cli_config)

    # ---- Settings ----
    settings = Settings()
    # CLI flag > config file > env
    if args.model:
        settings.model = args.model
    elif cli_config.model:
        settings.model = cli_config.model
    if args.max_turns:
        settings.max_turns = args.max_turns
    if getattr(args, "thinking", None) is not None:
        settings.thinking_enabled = bool(args.thinking)
    elif cli_config.thinking_enabled is not None:
        settings.thinking_enabled = cli_config.thinking_enabled
    if getattr(args, "thinking_effort", None):
        settings.thinking_effort = args.thinking_effort
    elif cli_config.thinking_effort:
        settings.thinking_effort = cli_config.thinking_effort

    preset = args.preset or cli_config.preset

    # ---- Paths ----
    from agent_service.paths import get_skills_dir, get_prompts_dir

    skills_dir = get_skills_dir()
    prompts_dir = get_prompts_dir()

    if args.workspace:
        workspace = Path(args.workspace).resolve()
    else:
        workspace = Path.cwd()
    workspace.mkdir(parents=True, exist_ok=True)

    # ---- LLM client ----
    raw_llm = build_raw_llm_client(
        provider=settings.llm_provider,
        anthropic_api_key=settings.anthropic_api_key,
        anthropic_base_url=settings.anthropic_base_url,
        openai_api_key=settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
    )
    llm = RetryingLLMClient(
        raw_llm,
        max_retries=settings.llm_max_retries,
        base_delay=settings.llm_retry_base_delay,
        max_delay=settings.llm_retry_max_delay,
    )

    # ---- Loaders ----
    skill_loader = SkillLoader(skills_dir)
    prompt_loader = PromptLoader(prompts_dir)

    # ---- Per-session state ----
    todo = TodoManager()
    task_manager = TaskManager(workspace)
    bg_manager = BackgroundManager(workspace, timeout=settings.background_timeout)
    cancelled = asyncio.Event()

    approval_queue: asyncio.Queue | None = None
    approval_handler: ApprovalHandler | None = None
    no_approval = args.no_approval or not cli_config.approval
    if not no_approval:
        approval_queue = asyncio.Queue()
        approval_handler = ApprovalHandler(approval_queue)

    # ---- Plan mode ----
    plan_mode_active = getattr(args, "plan", False)
    plan_ready_received = False  # set True when plan_ready event fires

    # ---- Cost tracker ----
    cost_tracker = CostTracker(settings.model)

    # ---- Renderer ----
    _raw_send_event = make_send_event(approval_handler, cost_tracker)

    async def send_event(event: dict) -> None:
        nonlocal plan_ready_received
        if event.get("type") == "plan_ready":
            plan_ready_received = True
        await _raw_send_event(event)

    # ---- Teams (optional) ----
    message_bus: MessageBus | None = None
    protocol_tracker: ProtocolTracker | None = None
    team_manager: TeammateManager | None = None
    if args.teams:
        message_bus = MessageBus(persist_dir=workspace / ".team" / "inbox")
        protocol_tracker = ProtocolTracker()
        team_manager = TeammateManager(
            workspace=workspace,
            bus=message_bus,
            llm=llm,
            config=settings,
            send_event=send_event,
            task_manager=task_manager,
        )

    # ---- Memory ----
    memory_mgr = MemoryManager(workspace)
    memory_content = memory_mgr.read() if settings.enable_memory else ""

    # ---- Session persistence ----
    session_store = SessionStore(cli_config.conversations_dir)

    # ---- Handle resume ----
    messages: list[dict] = []
    if getattr(args, "resume", None):
        resume_id = args.resume
        if resume_id == "latest":
            latest = session_store.get_latest()
            if latest:
                resume_id = latest.id
            else:
                console.print("  [yellow]No sessions to resume.[/yellow]")
                resume_id = None

        if resume_id:
            meta = session_store.get_session(resume_id)
            if meta:
                messages = session_store.load_messages(resume_id)
                session_meta = meta
                console.print(
                    f"  [dim]Resumed session[/dim] [bold]{meta.id}[/bold]"
                    f"  [dim]{meta.title or '(untitled)'}[/dim]"
                    f"  [dim]({len(messages)} messages)[/dim]"
                )
            else:
                console.print(f"  [yellow]Session {resume_id} not found.[/yellow]")

    # Create new session if not resuming
    if not messages or not getattr(args, "resume", None):
        session_meta = session_store.create(preset=preset, model=settings.model)
    elif not locals().get("session_meta"):
        session_meta = session_store.create(preset=preset, model=settings.model)

    # ---- Input session ----
    is_interactive = sys.stdin.isatty()
    prompt_session = None
    if is_interactive:
        from agent_cli.input import create_session
        prompt_session = create_session(cli_config)

    # ---- Non-interactive pipe mode ----
    if not is_interactive:
        user_input = sys.stdin.read().strip()
        if not user_input:
            return

        # Extract first line as session title in pipe mode
        first_line = user_input.split("\n", 1)[0].strip()[:60]
        if first_line:
            session_store.update_title(session_meta.id, first_line)

        messages.append({"role": "user", "content": user_input})
        session_store.save_message(session_meta.id, messages[-1])
        msg_count_before = len(messages)

        try:
            usage = await agent_loop(
                messages=messages,
                config=settings,
                llm=llm,
                skill_loader=skill_loader,
                todo=todo,
                send_event=send_event,
                preset=preset,
                prompt_loader=prompt_loader,
                cancelled=cancelled,
                task_manager=task_manager,
                background_manager=bg_manager,
                approval_queue=approval_queue,
                plan_mode=plan_mode_active,
            )
            # Flush renderer (important for code blocks in pipe mode)
            await send_event({"type": "done", "usage": usage})

            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cost_tracker.add(inp, out)
            # Save all new messages (assistant + tool results)
            for msg in messages[msg_count_before:]:
                session_store.save_message(session_meta.id, msg)
            session_store.save_usage(
                session_meta.id, cost_tracker.total_input,
                cost_tracker.total_output, cost_tracker.total_cost,
            )
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            logger.exception("Agent loop error")
        return

    # ---- Command context ----
    cmd_ctx = CommandContext(
        config=cli_config,
        cost_tracker=cost_tracker,
        session_store=session_store,
        session_id=session_meta.id,
        model=settings.model,
        preset=preset,
        thinking_enabled=settings.thinking_enabled,
        thinking_effort=settings.thinking_effort,
    )

    # ---- Banner ----
    teams_label = "[bold green]on[/bold green]" if args.teams else "[dim]off[/dim]"
    plan_label = "[bold bright_cyan]on[/bold bright_cyan]" if plan_mode_active else "[dim]off[/dim]"
    thinking_label = (
        f"[bold bright_black]on[/bold bright_black] [dim]({settings.thinking_effort})[/dim]"
        if settings.thinking_enabled
        else "[dim]off[/dim]"
    )
    info = (
        f"[bright_black]Model[/bright_black]      [bold]{settings.model}[/bold]\n"
        f"[bright_black]Preset[/bright_black]     [bold]{preset}[/bold]\n"
        f"[bright_black]Teams[/bright_black]      {teams_label}\n"
        f"[bright_black]Plan Mode[/bright_black]  {plan_label}\n"
        f"[bright_black]Thinking[/bright_black]   {thinking_label}\n"
        f"[bright_black]Session[/bright_black]    [dim]{session_meta.id}[/dim]\n"
        f"[bright_black]Workspace[/bright_black]  {workspace}\n\n"
        f"[bright_black]Ctrl+D to quit \u00b7 Ctrl+C to interrupt \u00b7 /help for commands[/bright_black]"
    )
    console.print()
    console.print(Panel(
        info,
        title="[bold]\u276f OpenAgent[/bold]",
        title_align="left",
        border_style="bright_black",
        padding=(1, 2),
        expand=False,
    ))
    console.print()

    # ---- Signal handling helpers ----
    loop = asyncio.get_running_loop()
    original_sigint = signal.getsignal(signal.SIGINT)

    def _cancel_handler(sig, frame):
        """Set the cancelled event so the agent loop stops gracefully."""
        cancelled.set()
        # Use sys.stderr to avoid reentrant Rich console writes
        sys.stderr.write("\n  Cancelling\u2026\n")
        sys.stderr.flush()

    # ---- REPL ----
    _skip_prompt = False  # set True after interrupt feedback to re-enter agent loop

    while True:
        if _skip_prompt:
            _skip_prompt = False
        else:
            # Restore default Ctrl+C for input phase
            signal.signal(signal.SIGINT, original_sigint)

            try:
                if prompt_session:
                    user_input = await prompt_session.prompt_async()
                    user_input = user_input.strip() if user_input else ""
                else:
                    console.print("[bright_black]\u2500\u2500\u2500[/bright_black]")
                    console.print("[bold cyan]\u276f[/bold cyan] ", end="")
                    user_input = await asyncio.to_thread(
                        lambda: input().strip()
                    )
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            # ---- Slash command dispatch ----
            cmd_result = await dispatch(user_input, cmd_ctx)
            if cmd_result is not None:
                if cmd_result.quit:
                    break
                if cmd_result.clear:
                    messages = []
                    if cmd_result.new_session_id:
                        session_meta = session_store.get_session(cmd_result.new_session_id) or session_meta
                        cmd_ctx.session_id = session_meta.id
                    continue
                if cmd_result.new_session_id and not cmd_result.clear:
                    # Resume command
                    new_meta = session_store.get_session(cmd_result.new_session_id)
                    if new_meta:
                        messages = session_store.load_messages(new_meta.id)
                        session_meta = new_meta
                        cmd_ctx.session_id = new_meta.id
                    continue
                if cmd_result.plan_mode is not None:
                    plan_mode_active = cmd_result.plan_mode
                    continue
                if cmd_result.teams is not None:
                    if cmd_result.teams and team_manager is None:
                        message_bus = MessageBus(persist_dir=workspace / ".team" / "inbox")
                        protocol_tracker = ProtocolTracker()
                        team_manager = TeammateManager(
                            workspace=workspace,
                            bus=message_bus,
                            llm=llm,
                            config=settings,
                            send_event=send_event,
                            task_manager=task_manager,
                        )
                    elif not cmd_result.teams and team_manager is not None:
                        await team_manager.shutdown_all()
                        team_manager = None
                        protocol_tracker = None
                        message_bus = None
                    continue
                if cmd_result.approval is not None:
                    if cmd_result.approval:
                        approval_queue = asyncio.Queue()
                        approval_handler = ApprovalHandler(approval_queue)
                        _raw_send_event = make_send_event(approval_handler, cost_tracker)
                    else:
                        approval_queue = None
                        approval_handler = None
                        _raw_send_event = make_send_event(None, cost_tracker)
                    continue
                if cmd_result.thinking is not None or cmd_result.thinking_effort is not None:
                    if cmd_result.thinking is not None:
                        settings.thinking_enabled = cmd_result.thinking
                        cmd_ctx.thinking_enabled = cmd_result.thinking
                    if cmd_result.thinking_effort is not None:
                        settings.thinking_effort = cmd_result.thinking_effort
                        cmd_ctx.thinking_effort = cmd_result.thinking_effort
                    continue
                if cmd_result.compact:
                    # Send compact as a user message to trigger manual compaction
                    messages.append({"role": "user", "content": "/compact"})
                    # Fall through to agent loop
                elif hasattr(cmd_result, "_new_model"):
                    new_model = cmd_result._new_model  # type: ignore[attr-defined]
                    settings.model = new_model
                    cost_tracker.model = new_model
                    cmd_ctx.model = new_model
                    continue
                else:
                    continue

            if not cmd_result or not cmd_result.compact:
                messages.append({"role": "user", "content": user_input})
                session_store.save_message(session_meta.id, messages[-1])

                # Auto-set title from first user message
                if len([m for m in messages if m.get("role") == "user"]) == 1:
                    session_store.update_title(session_meta.id, user_input[:60])

        # Track how many messages exist before agent runs
        msg_count_before = len(messages)
        plan_ready_received = False  # reset each turn

        # During agent turn: Ctrl+C → cancel event (not exit)
        cancelled.clear()
        signal.signal(signal.SIGINT, _cancel_handler)

        try:
            # Send thinking event for spinner
            await send_event({"type": "thinking"})

            AGENT_TIMEOUT = int(os.environ.get("OPENAGENT_TIMEOUT", 1800))  # default 30 min
            try:
                usage = await asyncio.wait_for(
                    agent_loop(
                        messages=messages,
                        config=settings,
                        llm=llm,
                        skill_loader=skill_loader,
                        todo=todo,
                        send_event=send_event,
                        preset=preset,
                        prompt_loader=prompt_loader,
                        cancelled=cancelled,
                        task_manager=task_manager,
                        background_manager=bg_manager,
                        team_manager=team_manager,
                        message_bus=message_bus,
                        protocol_tracker=protocol_tracker,
                        approval_queue=approval_queue,
                        plan_mode=plan_mode_active,
                    ),
                    timeout=AGENT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                console.print(f"\n  [bold yellow]Agent loop timed out after {AGENT_TIMEOUT}s[/bold yellow]")
                usage = {"input_tokens": 0, "output_tokens": 0}

            # Sync plan mode if agent entered it mid-loop
            if usage.get("plan_mode") and not plan_mode_active:
                plan_mode_active = True

            # Track costs
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cost_tracker.add(inp, out)

            # Check if this was a Ctrl+C interrupt — offer feedback prompt
            if cancelled.is_set() and not plan_mode_active:
                # Show interrupted usage
                await send_event({"type": "interrupted", "usage": usage})

                # Persist partial work
                for msg in messages[msg_count_before:]:
                    session_store.save_message(session_meta.id, msg)
                session_store.save_usage(
                    session_meta.id, cost_tracker.total_input,
                    cost_tracker.total_output, cost_tracker.total_cost,
                )

                # Restore normal Ctrl+C for feedback input
                signal.signal(signal.SIGINT, original_sigint)
                console.print(
                    "\n  [bright_yellow]\u250c[/bright_yellow]"
                    " [yellow]Interrupted[/yellow] \u2014 type feedback to redirect"
                )
                console.print(
                    "  [bright_yellow]\u2514[/bright_yellow]"
                    " [dim]Press Enter to skip[/dim]"
                )

                try:
                    if prompt_session:
                        from prompt_toolkit.formatted_text import HTML
                        feedback = await prompt_session.prompt_async(
                            message=HTML(
                                '<style fg="ansiyellow">feedback\u276f</style> '
                            )
                        )
                    else:
                        feedback = await asyncio.to_thread(
                            lambda: input("  feedback\u276f ").strip()
                        )
                    feedback = feedback.strip() if feedback else ""
                except (EOFError, KeyboardInterrupt):
                    feedback = ""

                if feedback:
                    # Sanitize orphaned tool_use blocks before re-running.
                    # When interrupted mid-tool-call, the last assistant
                    # message may have tool_use without matching tool_result.
                    _sanitize_interrupted_messages(messages)
                    # Inject feedback and re-run the agent loop
                    messages.append({"role": "user", "content": feedback})
                    session_store.save_message(session_meta.id, messages[-1])
                    _skip_prompt = True
                    console.print()
                    continue

                # No feedback — continue to normal REPL prompt
                console.print()
                continue

            # Plan mode approval prompt — only when the agent signalled plan_ready
            if plan_mode_active and plan_ready_received:
                signal.signal(signal.SIGINT, original_sigint)
                console.print()
                console.print(
                    "  [bright_cyan]\u250c[/bright_cyan]"
                    " [bold bright_cyan]Plan ready for review[/bold bright_cyan]"
                )
                console.print(
                    "  [bright_cyan]\u2514[/bright_cyan]"
                    " [bold]\\[A][/bold]pprove  [bold]\\[r][/bold]eject"
                    "  [bold]\\[f][/bold]eedback"
                )
                try:
                    if prompt_session:
                        from prompt_toolkit.formatted_text import HTML
                        choice = await prompt_session.prompt_async(
                            message=HTML(
                                '<b><style fg="ansicyan">plan\u276f</style></b> '
                            )
                        )
                        choice = choice.strip().lower() if choice else "r"
                    else:
                        choice = await asyncio.to_thread(
                            lambda: input("  plan\u276f ").strip().lower()
                        )
                except (EOFError, KeyboardInterrupt):
                    choice = "r"

                # Save agent messages from the plan phase
                for msg in messages[msg_count_before:]:
                    session_store.save_message(session_meta.id, msg)
                await send_event({"type": "done", "usage": usage})

                if choice.startswith("a"):
                    plan_mode_active = False
                    await send_event({"type": "plan_approved"})
                    await send_event({"type": "plan_mode_changed", "enabled": False})
                    # Inject execution message and re-run the agent loop
                    messages.append({
                        "role": "user",
                        "content": "Plan approved. Now execute the plan above step by step.",
                    })
                    session_store.save_message(session_meta.id, messages[-1])
                    _skip_prompt = True
                elif choice.startswith("f"):
                    try:
                        if prompt_session:
                            fb = await prompt_session.prompt_async(
                                message=HTML(
                                    '<style fg="ansiyellow">feedback\u276f</style> '
                                )
                            )
                            fb = fb.strip() if fb else ""
                        else:
                            fb = await asyncio.to_thread(
                                lambda: input("  feedback\u276f ").strip()
                            )
                    except (EOFError, KeyboardInterrupt):
                        fb = ""
                    if fb:
                        await send_event({"type": "plan_rejected", "feedback": fb})
                        messages.append({"role": "user", "content": f"Plan rejected. Feedback:\n{fb}\n\nRevise the plan."})
                        session_store.save_message(session_meta.id, messages[-1])
                        _skip_prompt = True
                else:
                    await send_event({"type": "plan_rejected"})
                    console.print("  [dim]Type a new message or /execute to exit plan mode.[/dim]")

                session_store.save_usage(
                    session_meta.id, cost_tracker.total_input,
                    cost_tracker.total_output, cost_tracker.total_cost,
                )
                console.print()
                continue

            # Show usage
            await send_event({"type": "done", "usage": usage})

            # Persist all new messages added by the agent loop
            for msg in messages[msg_count_before:]:
                session_store.save_message(session_meta.id, msg)

            # Save usage
            session_store.save_usage(
                session_meta.id, cost_tracker.total_input,
                cost_tracker.total_output, cost_tracker.total_cost,
            )

        except Exception as exc:
            console.print(f"\n  [bold red]\u2717 Error[/bold red]  {exc}")
            logger.exception("Agent loop error")

        # Blank line between turns
        console.print()

    # ---- Cleanup ----
    console.print()
    console.print("  [bright_black]\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500[/bright_black]")
    await bg_manager.cancel_all()
    if team_manager:
        await team_manager.shutdown_all()

    enable_memory = settings.enable_memory and not args.no_memory
    if enable_memory and len(messages) >= 2:
        console.print("  [dim]Saving session memory\u2026[/dim]")
        try:
            existing = memory_mgr.read()
            updated = await analyze_session(messages, existing, llm, settings.model)
            memory_mgr.write(updated)
            console.print("  [dim]Memory saved.[/dim]")
        except Exception:
            console.print("  [yellow]Failed to save memory.[/yellow]")
            logger.exception("Memory save failed")

    # Final cost summary
    if cost_tracker.total_input or cost_tracker.total_output:
        line = cost_tracker.format_usage_line(
            cost_tracker.total_input, cost_tracker.total_output,
        )
        console.print(f"  [dim]Total: {line}[/dim]")

    console.print("\n  [dim]Session ended.[/dim]\n")
