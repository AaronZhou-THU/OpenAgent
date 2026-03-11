"""Bash tool — run shell commands with timeout and safety checks."""

from __future__ import annotations

import asyncio
import re
import shlex
from pathlib import Path

DEFINITION = {
    "name": "bash",
    "description": "Run a shell command. Use for: ls, find, grep, git, npm, python, etc.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            }
        },
        "required": ["command"],
    },
}

# Patterns checked after normalising whitespace, so "rm  -rf  /" still matches.
DANGEROUS_PATTERNS = [
    r"\brm\s+(?:-\S+\s+)*\s*/\s*$|\brm\s+(?:-\S+\s+)*/\s",  # rm -rf / (root only)
    r"\bsudo\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r">\s*/dev/",
    r"\bmkfs\b",
    r"\bdd\s+.*of=/dev/",
    r"\$\(",               # command substitution: $(...)
    r"`",                  # backtick command substitution
    r"\$\(\(",             # arithmetic expansion: $((...))
]

_DANGEROUS_RE = [re.compile(p) for p in DANGEROUS_PATTERNS]

# Shell operators that chain separate commands
_CHAIN_SPLIT_RE = re.compile(r"\s*(?:\|+|&&|\|\||;)\s*")


def _extract_commands(command: str) -> list[str]:
    """Extract the leading program name from each segment in a piped/chained command."""
    segments = _CHAIN_SPLIT_RE.split(command.strip())
    programs: list[str] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        # Strip env-var assignments at the front (e.g. "FOO=bar cmd")
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()
        for tok in tokens:
            if "=" in tok and not tok.startswith("-"):
                continue  # VAR=value prefix
            programs.append(tok)
            break
    return programs


async def run_bash(
    args: dict,
    *,
    workspace: Path,
    timeout: int = 60,
    allowed_commands: list[str] | None = None,
) -> str:
    command: str = args["command"]

    # Safety: block dangerous patterns (regex-based, whitespace-insensitive)
    for pat in _DANGEROUS_RE:
        if pat.search(command):
            return f"Error: Blocked dangerous pattern in command"

    # Safety: if allowlist is set, check ALL programs in pipes/chains
    if allowed_commands:
        allowed_set = set(allowed_commands)
        programs = _extract_commands(command)
        if not programs:
            return "Error: Empty command"
        for prog in programs:
            if prog not in allowed_set:
                return f"Error: Command '{prog}' not in allowed list"

    proc = None
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout.decode() + stderr.decode()).strip()
        return (output[:50_000]) if output else "(no output)"
    except asyncio.TimeoutError:
        if proc is not None:
            proc.kill()
        return f"Error: Command timed out ({timeout}s)"
    except Exception as e:
        return f"Error: {e}"
