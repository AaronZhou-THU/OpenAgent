"""
Protocol tracker — request/response correlation for team protocols.

Adapted from learn-claude-code s10. Tracks shutdown and plan approval
requests using request_id correlation.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field


@dataclass
class ProtocolRequest:
    id: str
    type: str  # "shutdown" | "plan_approval"
    target: str  # agent name
    status: str = "pending"  # pending | approved | rejected
    payload: dict = field(default_factory=dict)


class ProtocolTracker:
    """Tracks request/response correlations for team protocols.

    Thread-safe via asyncio.Lock.
    """

    def __init__(self) -> None:
        self._requests: dict[str, ProtocolRequest] = {}
        self._lock = asyncio.Lock()

    async def create_request(
        self, req_type: str, target: str, payload: dict | None = None
    ) -> ProtocolRequest:
        req_id = uuid.uuid4().hex[:8]
        req = ProtocolRequest(
            id=req_id,
            type=req_type,
            target=target,
            payload=payload or {},
        )
        async with self._lock:
            self._requests[req_id] = req
        return req

    async def resolve(self, req_id: str, approved: bool) -> ProtocolRequest | None:
        async with self._lock:
            req = self._requests.get(req_id)
            if req:
                req.status = "approved" if approved else "rejected"
        return req

    async def get(self, req_id: str) -> ProtocolRequest | None:
        return self._requests.get(req_id)

    async def list_pending(self, req_type: str | None = None) -> list[ProtocolRequest]:
        async with self._lock:
            reqs = list(self._requests.values())
        if req_type:
            reqs = [r for r in reqs if r.type == req_type]
        return [r for r in reqs if r.status == "pending"]
