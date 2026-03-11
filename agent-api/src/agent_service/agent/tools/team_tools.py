"""Team tools — spawn teammates, send messages, read inbox, broadcast."""

from __future__ import annotations

import json
from dataclasses import asdict

from agent_service.agent.message_bus import MessageBus
from agent_service.agent.protocol_tracker import ProtocolTracker
from agent_service.agent.teammate_manager import TeammateManager

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

SPAWN_TEAMMATE_DEFINITION = {
    "name": "spawn_teammate",
    "description": (
        "Spawn a named teammate agent with a role and initial task. "
        "The teammate runs its own agent loop and communicates via messages."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique name for the teammate (e.g. 'alice', 'bob')",
            },
            "role": {
                "type": "string",
                "description": "Role description (e.g. 'coder', 'tester', 'reviewer')",
            },
            "prompt": {
                "type": "string",
                "description": "Initial task/instructions for the teammate",
            },
        },
        "required": ["name", "role", "prompt"],
    },
}

LIST_TEAMMATES_DEFINITION = {
    "name": "list_teammates",
    "description": "List all teammates with their roles and current status.",
    "input_schema": {"type": "object", "properties": {}},
}

SEND_MESSAGE_DEFINITION = {
    "name": "send_message",
    "description": "Send a message to a specific teammate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient teammate name"},
            "content": {"type": "string", "description": "Message content"},
            "msg_type": {
                "type": "string",
                "description": "Message type",
                "enum": ["message", "shutdown_request", "plan_approval_response"],
                "default": "message",
            },
        },
        "required": ["to", "content"],
    },
}

READ_INBOX_DEFINITION = {
    "name": "read_inbox",
    "description": "Read and drain all messages from your (lead) inbox.",
    "input_schema": {"type": "object", "properties": {}},
}

BROADCAST_DEFINITION = {
    "name": "broadcast",
    "description": "Send a message to all active teammates.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Message to broadcast"},
        },
        "required": ["content"],
    },
}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def run_spawn_teammate(
    args: dict, *, team_manager: TeammateManager
) -> str:
    try:
        return await team_manager.spawn(
            name=args["name"],
            role=args["role"],
            prompt=args["prompt"],
        )
    except Exception as e:
        return f"Error: {e}"


async def run_list_teammates(
    args: dict, *, team_manager: TeammateManager
) -> str:
    return team_manager.list_all()


async def run_send_message(
    args: dict, *, bus: MessageBus, sender: str = "lead"
) -> str:
    try:
        return await bus.send(
            sender=sender,
            to=args["to"],
            content=args["content"],
            msg_type=args.get("msg_type", "message"),
        )
    except Exception as e:
        return f"Error: {e}"


async def run_read_inbox(
    args: dict, *, bus: MessageBus, name: str = "lead"
) -> str:
    try:
        msgs = await bus.read_inbox(name)
        if not msgs:
            return "(inbox empty)"
        return json.dumps([asdict(m) for m in msgs], indent=2)
    except Exception as e:
        return f"Error: {e}"


async def run_broadcast(
    args: dict, *, bus: MessageBus, team_manager: TeammateManager
) -> str:
    try:
        recipients = team_manager.member_names()
        return await bus.broadcast("lead", args["content"], recipients)
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Protocol tools (shutdown + plan approval)
# ---------------------------------------------------------------------------

SHUTDOWN_REQUEST_DEFINITION = {
    "name": "shutdown_request",
    "description": (
        "Send a graceful shutdown request to a teammate. "
        "The teammate can approve or reject. Returns a request_id for tracking."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "teammate": {
                "type": "string",
                "description": "Name of the teammate to shut down",
            },
        },
        "required": ["teammate"],
    },
}

CHECK_PROTOCOL_DEFINITION = {
    "name": "check_protocol",
    "description": "Check status of a protocol request by request_id.",
    "input_schema": {
        "type": "object",
        "properties": {
            "request_id": {
                "type": "string",
                "description": "The request_id to check",
            },
        },
        "required": ["request_id"],
    },
}

PLAN_REVIEW_DEFINITION = {
    "name": "plan_review",
    "description": (
        "Approve or reject a plan submitted by a teammate. "
        "The teammate will receive the decision and optional feedback."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "request_id": {
                "type": "string",
                "description": "The plan request_id",
            },
            "approve": {
                "type": "boolean",
                "description": "Whether to approve the plan",
            },
            "feedback": {
                "type": "string",
                "description": "Optional feedback for the teammate",
            },
        },
        "required": ["request_id", "approve"],
    },
}


async def run_shutdown_request(
    args: dict, *, bus: MessageBus, tracker: ProtocolTracker
) -> str:
    try:
        teammate = args["teammate"]
        req = await tracker.create_request("shutdown", teammate)
        await bus.send(
            "lead", teammate,
            "Please shut down gracefully.",
            "shutdown_request",
            extra={"request_id": req.id},
        )
        return f"Shutdown request {req.id} sent to '{teammate}' (status: pending)"
    except Exception as e:
        return f"Error: {e}"


async def run_check_protocol(
    args: dict, *, tracker: ProtocolTracker
) -> str:
    try:
        req = await tracker.get(args["request_id"])
        if not req:
            return f"Error: Unknown request_id '{args['request_id']}'"
        return (
            f"Request {req.id}: type={req.type}, target={req.target}, "
            f"status={req.status}"
        )
    except Exception as e:
        return f"Error: {e}"


async def run_plan_review(
    args: dict, *, bus: MessageBus, tracker: ProtocolTracker
) -> str:
    try:
        req_id = args["request_id"]
        approve = args["approve"]
        feedback = args.get("feedback", "")

        req = await tracker.resolve(req_id, approve)
        if not req:
            return f"Error: Unknown request_id '{req_id}'"

        await bus.send(
            "lead", req.target,
            feedback or ("Approved" if approve else "Rejected"),
            "plan_approval_response",
            extra={"request_id": req_id, "approve": approve, "feedback": feedback},
        )
        status = "approved" if approve else "rejected"
        return f"Plan {status} for '{req.target}'"
    except Exception as e:
        return f"Error: {e}"
