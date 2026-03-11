"""Tests for agent_service.agent.message_bus.MessageBus."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_service.agent.message_bus import MessageBus, TeamMessage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_send_and_read_inbox():
    bus = MessageBus()
    await bus.send("alice", "bob", "Hello Bob", "message")
    msgs = await bus.read_inbox("bob")
    assert len(msgs) == 1
    assert msgs[0].sender == "alice"
    assert msgs[0].content == "Hello Bob"
    assert msgs[0].type == "message"


async def test_send_invalid_type():
    bus = MessageBus()
    result = await bus.send("alice", "bob", "hi", "invalid_type")
    assert "Error" in result


async def test_broadcast_delivers_to_all_except_sender():
    bus = MessageBus()
    await bus.broadcast("lead", "Hello team", ["lead", "worker1", "worker2"])
    # lead should NOT get the message
    lead_msgs = await bus.read_inbox("lead")
    assert len(lead_msgs) == 0
    # workers should get it
    w1 = await bus.read_inbox("worker1")
    assert len(w1) == 1
    assert w1[0].sender == "lead"
    w2 = await bus.read_inbox("worker2")
    assert len(w2) == 1


async def test_read_inbox_empty():
    bus = MessageBus()
    msgs = await bus.read_inbox("nobody")
    assert msgs == []


async def test_multiple_messages_ordered():
    bus = MessageBus()
    await bus.send("alice", "bob", "First", "message")
    await bus.send("alice", "bob", "Second", "message")
    await bus.send("charlie", "bob", "Third", "message")
    msgs = await bus.read_inbox("bob")
    assert len(msgs) == 3
    assert msgs[0].content == "First"
    assert msgs[1].content == "Second"
    assert msgs[2].content == "Third"


async def test_persistence_to_jsonl(tmp_path: Path):
    persist_dir = tmp_path / "inbox"
    bus = MessageBus(persist_dir=persist_dir)
    await bus.send("alice", "bob", "persisted message", "message")
    # Check the JSONL file was created
    jsonl_file = persist_dir / "bob.jsonl"
    assert jsonl_file.exists()
    content = jsonl_file.read_text()
    assert "persisted message" in content
    assert "alice" in content


async def test_read_inbox_clears_persistence(tmp_path: Path):
    persist_dir = tmp_path / "inbox"
    bus = MessageBus(persist_dir=persist_dir)
    await bus.send("alice", "bob", "msg1", "message")
    jsonl_file = persist_dir / "bob.jsonl"
    assert jsonl_file.exists()
    assert jsonl_file.read_text().strip() != ""

    # Drain inbox — should clear the persistence file
    msgs = await bus.read_inbox("bob")
    assert len(msgs) == 1
    assert jsonl_file.read_text() == ""
