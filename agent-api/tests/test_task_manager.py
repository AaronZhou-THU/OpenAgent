"""Tests for agent_service.agent.task_manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_service.agent.task_manager import (
    Task,
    TaskManager,
    _dict_to_task,
    _task_to_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tm(tmp_path: Path) -> TaskManager:
    """Return a fresh TaskManager backed by a tmp directory."""
    return TaskManager(tmp_path)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


async def test_create_task(tm: TaskManager):
    task = await tm.create("Build API", description="REST endpoints")
    assert task.id == 1
    assert task.subject == "Build API"
    assert task.description == "REST endpoints"
    assert task.status == "pending"


async def test_get_task(tm: TaskManager):
    created = await tm.create("Task A")
    fetched = await tm.get(created.id)
    assert fetched.subject == "Task A"
    assert fetched.id == created.id


async def test_list_tasks(tm: TaskManager):
    await tm.create("A")
    await tm.create("B")
    tasks = await tm.list_all()
    assert len(tasks) == 2
    subjects = {t.subject for t in tasks}
    assert subjects == {"A", "B"}


async def test_update_status(tm: TaskManager):
    task = await tm.create("X")
    updated = await tm.update(task.id, status="in_progress")
    assert updated.status == "in_progress"
    updated = await tm.update(task.id, status="completed")
    assert updated.status == "completed"


async def test_update_subject_description_active_form_owner(tm: TaskManager):
    task = await tm.create("Old subject")
    updated = await tm.update(
        task.id,
        subject="New subject",
        description="New desc",
        active_form="Reviewing",
        owner="alice",
    )
    assert updated.subject == "New subject"
    assert updated.description == "New desc"
    assert updated.active_form == "Reviewing"
    assert updated.owner == "alice"


async def test_delete_task(tm: TaskManager):
    task = await tm.create("Doomed")
    await tm.update(task.id, status="deleted")
    tasks = await tm.list_all()
    # list_all skips deleted tasks
    assert all(t.id != task.id for t in tasks)


async def test_dependency_cascade_on_completion(tm: TaskManager):
    t1 = await tm.create("First")
    t2 = await tm.create("Second")
    # t2 is blocked by t1
    await tm.update(t2.id, add_blocked_by=[t1.id])
    fetched = await tm.get(t2.id)
    assert t1.id in fetched.blocked_by

    # Complete t1 => t2's blockedBy should be cleared
    await tm.update(t1.id, status="completed")
    fetched = await tm.get(t2.id)
    assert t1.id not in fetched.blocked_by


async def test_bidirectional_dependency(tm: TaskManager):
    t1 = await tm.create("Blocker")
    t2 = await tm.create("Blocked")
    # addBlocks on t1 pointing to t2 should add t1 to t2's blockedBy
    await tm.update(t1.id, add_blocks=[t2.id])
    t2_fetched = await tm.get(t2.id)
    assert t1.id in t2_fetched.blocked_by
    t1_fetched = await tm.get(t1.id)
    assert t2.id in t1_fetched.blocks


async def test_scan_unclaimed(tm: TaskManager):
    t1 = await tm.create("Free task")
    t2 = await tm.create("Owned task")
    await tm.update(t2.id, owner="bob")
    t3 = await tm.create("Blocked task")
    await tm.update(t3.id, add_blocked_by=[t1.id])

    unclaimed = await tm.scan_unclaimed()
    ids = [t.id for t in unclaimed]
    assert t1.id in ids
    assert t2.id not in ids  # owned
    assert t3.id not in ids  # blocked


async def test_claim_task(tm: TaskManager):
    task = await tm.create("Claimable")
    claimed = await tm.claim(task.id, "alice")
    assert claimed.owner == "alice"
    assert claimed.status == "in_progress"


async def test_claim_already_claimed_raises(tm: TaskManager):
    task = await tm.create("Taken")
    await tm.claim(task.id, "alice")
    with pytest.raises(ValueError, match="already claimed"):
        await tm.claim(task.id, "bob")


# ---------------------------------------------------------------------------
# Serialization roundtrip
# ---------------------------------------------------------------------------


def test_task_to_dict_and_back():
    task = Task(
        id=42,
        subject="Deploy",
        description="Deploy to prod",
        status="in_progress",
        blocked_by=[1, 2],
        blocks=[3],
        owner="dev",
        active_form="Deploying...",
        metadata={"region": "us-east"},
    )
    d = _task_to_dict(task)
    assert d["id"] == 42
    assert d["blockedBy"] == [1, 2]
    assert d["blocks"] == [3]
    assert d["activeForm"] == "Deploying..."

    roundtripped = _dict_to_task(d)
    assert roundtripped.id == task.id
    assert roundtripped.subject == task.subject
    assert roundtripped.blocked_by == task.blocked_by
    assert roundtripped.blocks == task.blocks
    assert roundtripped.active_form == task.active_form
    assert roundtripped.metadata == task.metadata


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def test_render_empty():
    assert TaskManager.render([]) == "No tasks."


def test_render_tasks():
    tasks = [
        Task(id=1, subject="A", status="pending"),
        Task(id=2, subject="B", status="in_progress", active_form="Working", owner="x"),
        Task(id=3, subject="C", status="completed"),
    ]
    text = TaskManager.render(tasks)
    assert "[ ] #1: A" in text
    assert "[>] #2: B" in text
    assert "@x" in text
    assert "<- Working" in text
    assert "[x] #3: C" in text
    assert "(1/3 completed)" in text


def test_render_blocked():
    tasks = [
        Task(id=1, subject="A", status="pending", blocked_by=[2]),
    ]
    text = TaskManager.render(tasks)
    assert "(blocked by:" in text


# ---------------------------------------------------------------------------
# Invalid status
# ---------------------------------------------------------------------------


async def test_invalid_status_raises(tm: TaskManager):
    task = await tm.create("X")
    with pytest.raises(ValueError, match="Invalid status"):
        await tm.update(task.id, status="banana")
