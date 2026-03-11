"""Tests for agent_service.agent.background_manager.BackgroundManager."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_service.agent.background_manager import BackgroundManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def bm(tmp_path: Path):
    """Return a BackgroundManager and cancel all tasks on teardown."""
    mgr = BackgroundManager(tmp_path, timeout=10)
    yield mgr
    await mgr.cancel_all()
    # Give cancellation a moment to propagate
    await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_run_returns_immediately(bm: BackgroundManager):
    result = await bm.run("echo hello")
    assert "Background task" in result
    assert "started" in result


async def test_check_no_tasks(bm: BackgroundManager):
    result = await bm.check()
    assert result == "No background tasks."


async def test_check_specific_running_task(bm: BackgroundManager):
    msg = await bm.run("sleep 10")
    task_id = msg.split()[2]  # "Background task XXXX started: ..."
    result = await bm.check(task_id)
    assert "running" in result.lower() or "sleep" in result


async def test_drain_notifications_empty(bm: BackgroundManager):
    notifs = await bm.drain_notifications()
    assert notifs == []


async def test_cancel_all(bm: BackgroundManager):
    await bm.run("sleep 100")
    await bm.run("sleep 100")
    assert len(bm._running) == 2
    await bm.cancel_all()
    # Give cancellation a moment to propagate
    await asyncio.sleep(0.1)
    for t in bm._running.values():
        assert t.done() or t.cancelled()


async def test_run_wait_check_drain(bm: BackgroundManager):
    """Full lifecycle: run, wait for completion, check result, drain notification."""
    msg = await bm.run("echo test_output")
    task_id = msg.split()[2]

    # Wait for the background asyncio.Task to finish
    await bm._running[task_id]

    # Check should show completed
    result = await bm.check(task_id)
    assert "completed" in result.lower()
    assert "test_output" in result

    # Drain should yield the notification
    notifs = await bm.drain_notifications()
    assert len(notifs) == 1
    assert notifs[0]["task_id"] == task_id
    assert notifs[0]["status"] == "completed"
    assert "test_output" in notifs[0]["result"]

    # Second drain should be empty
    notifs2 = await bm.drain_notifications()
    assert notifs2 == []
