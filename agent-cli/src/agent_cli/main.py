"""CLI entry point — parse arguments and launch the REPL."""

from __future__ import annotations

import argparse
import asyncio
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openagent",
        description="OpenAgent — terminal interface for the agent service.",
    )
    p.add_argument(
        "-p", "--preset",
        default="coding",
        help="Prompt preset to use (default: coding)",
    )
    p.add_argument(
        "-w", "--workspace",
        default=None,
        help="Workspace directory (default: current directory)",
    )
    p.add_argument(
        "-m", "--model",
        default=None,
        help="Override the LLM model name",
    )
    p.add_argument(
        "--no-memory",
        action="store_true",
        help="Disable session memory save on exit",
    )
    p.add_argument(
        "--no-approval",
        action="store_true",
        help="Skip tool approval prompts (auto-approve everything)",
    )
    p.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Override max agent turns per message",
    )
    p.add_argument(
        "--teams",
        action="store_true",
        help="Enable agent teammates (team mode)",
    )
    p.add_argument(
        "--plan",
        action="store_true",
        help="Start in plan mode (read-only exploration, then execute after approval)",
    )
    p.add_argument(
        "--resume",
        nargs="?",
        const="latest",
        default=None,
        metavar="SESSION_ID",
        help="Resume a previous session (default: latest)",
    )
    p.add_argument(
        "--version",
        action="version",
        version=_get_version(),
    )
    return p


def _get_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        for dist_name in ("openagent-app", "openagent"):
            try:
                return f"openagent {version(dist_name)}"
            except PackageNotFoundError:
                continue
    except Exception:
        pass

    return "openagent 0.1.0"


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    from agent_cli.app import run_repl

    try:
        asyncio.run(run_repl(args))
    except KeyboardInterrupt:
        print("\nBye!")
        sys.exit(0)
