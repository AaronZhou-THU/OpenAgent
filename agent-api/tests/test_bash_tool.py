"""Tests for agent_service.agent.tools.bash_tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_service.agent.tools.bash_tool import _extract_commands, run_bash


# ---------------------------------------------------------------------------
# _extract_commands tests
# ---------------------------------------------------------------------------


def test_extract_simple_command():
    assert _extract_commands("ls -la") == ["ls"]


def test_extract_piped_commands():
    assert _extract_commands("cat file.txt | grep hello | wc -l") == [
        "cat",
        "grep",
        "wc",
    ]


def test_extract_chained_and():
    assert _extract_commands("mkdir build && cd build && cmake ..") == [
        "mkdir",
        "cd",
        "cmake",
    ]


def test_extract_chained_or():
    assert _extract_commands("test -f x || echo missing") == ["test", "echo"]


def test_extract_chained_semicolon():
    assert _extract_commands("echo a; echo b") == ["echo", "echo"]


def test_extract_env_var_prefix():
    result = _extract_commands("FOO=bar BAZ=1 python script.py")
    assert result == ["python"]


# ---------------------------------------------------------------------------
# run_bash tests
# ---------------------------------------------------------------------------


async def test_run_bash_echo(tmp_path: Path):
    result = await run_bash({"command": "echo hello"}, workspace=tmp_path)
    assert "hello" in result


async def test_run_bash_blocks_sudo(tmp_path: Path):
    result = await run_bash({"command": "sudo rm -rf /"}, workspace=tmp_path)
    assert "Error" in result
    assert "Blocked" in result or "dangerous" in result.lower()


async def test_run_bash_blocks_rm_rf_root(tmp_path: Path):
    result = await run_bash({"command": "rm -rf /"}, workspace=tmp_path)
    assert "Error" in result


async def test_run_bash_blocks_shutdown(tmp_path: Path):
    result = await run_bash({"command": "shutdown -h now"}, workspace=tmp_path)
    assert "Error" in result


async def test_run_bash_blocks_reboot(tmp_path: Path):
    result = await run_bash({"command": "reboot"}, workspace=tmp_path)
    assert "Error" in result


async def test_run_bash_allowed_commands(tmp_path: Path):
    # Only allow echo
    result = await run_bash(
        {"command": "echo ok"},
        workspace=tmp_path,
        allowed_commands=["echo"],
    )
    assert "ok" in result

    # ls is NOT allowed
    result = await run_bash(
        {"command": "ls"},
        workspace=tmp_path,
        allowed_commands=["echo"],
    )
    assert "Error" in result
    assert "not in allowed" in result


async def test_run_bash_allowed_commands_piped(tmp_path: Path):
    # echo is allowed but grep is not
    result = await run_bash(
        {"command": "echo hi | grep hi"},
        workspace=tmp_path,
        allowed_commands=["echo"],
    )
    assert "Error" in result
    assert "grep" in result


async def test_run_bash_timeout(tmp_path: Path):
    result = await run_bash(
        {"command": "sleep 10"},
        workspace=tmp_path,
        timeout=1,
    )
    assert "Error" in result
    assert "timed out" in result.lower()


# ---------------------------------------------------------------------------
# Security bypass tests (Phase 1.1 & Phase 4.1)
# ---------------------------------------------------------------------------


async def test_run_bash_blocks_command_substitution(tmp_path: Path):
    """Command substitution via $(...) should be blocked."""
    result = await run_bash(
        {"command": 'grep "$(cat /etc/passwd)" file'},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "Blocked" in result


async def test_run_bash_blocks_nested_command_substitution(tmp_path: Path):
    """Nested command substitution: $(rm -rf /) inside arguments."""
    result = await run_bash(
        {"command": 'echo "$(rm -rf /)"'},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "Blocked" in result


async def test_run_bash_blocks_backtick_substitution(tmp_path: Path):
    """Backtick command substitution should be blocked."""
    result = await run_bash(
        {"command": "echo `whoami`"},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "Blocked" in result


async def test_run_bash_blocks_arithmetic_expansion(tmp_path: Path):
    """Arithmetic expansion $((...)) should be blocked."""
    result = await run_bash(
        {"command": "echo $((1+1))"},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "Blocked" in result


async def test_run_bash_blocks_env_var_path_injection(tmp_path: Path):
    """Environment variable injection for PATH should be blocked by allowlist."""
    result = await run_bash(
        {"command": "PATH=/tmp cmd"},
        workspace=tmp_path,
        allowed_commands=["echo"],
    )
    assert "Error" in result
    assert "not in allowed" in result


async def test_run_bash_blocks_mkfs(tmp_path: Path):
    result = await run_bash({"command": "mkfs.ext4 /dev/sda1"}, workspace=tmp_path)
    assert "Error" in result
    assert "Blocked" in result


async def test_run_bash_blocks_dd_to_dev(tmp_path: Path):
    result = await run_bash(
        {"command": "dd if=/dev/zero of=/dev/sda"},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "Blocked" in result


async def test_run_bash_blocks_redirect_to_dev(tmp_path: Path):
    result = await run_bash(
        {"command": "echo x > /dev/sda"},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "Blocked" in result
