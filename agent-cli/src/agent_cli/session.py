"""Session persistence — save/resume conversations in ~/.agent/conversations/."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SessionMeta:
    """Metadata for a saved session."""

    id: str
    title: str = ""
    preset: str = "coding"
    model: str = ""
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0


class SessionStore:
    """Manages conversation persistence in ~/.agent/conversations/."""

    def __init__(self, conversations_dir: Path) -> None:
        self._dir = conversations_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # -- Creation & metadata ------------------------------------------------

    def create(self, preset: str, model: str) -> SessionMeta:
        """Create a new session directory and return its metadata."""
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        meta = SessionMeta(
            id=session_id,
            preset=preset,
            model=model,
            created_at=now,
            updated_at=now,
        )
        session_dir = self._dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        self._write_meta(meta)
        self._update_index(meta)
        return meta

    def update_title(self, session_id: str, title: str) -> None:
        """Set the session title (typically from first user message)."""
        meta = self._read_meta(session_id)
        if meta:
            meta.title = title[:60]
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            self._write_meta(meta)
            self._update_index(meta)

    # -- Messages -----------------------------------------------------------

    def save_message(self, session_id: str, msg: dict[str, Any]) -> None:
        """Append a single message to the session's JSONL file."""
        path = self._dir / session_id / "messages.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        # Update message count in both meta.json and index
        meta = self._read_meta(session_id)
        if meta:
            meta.message_count += 1
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            self._write_meta(meta)
            self._update_index(meta)

    def load_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Load all messages from a session's JSONL file."""
        path = self._dir / session_id / "messages.jsonl"
        if not path.exists():
            return []
        messages = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        return messages

    # -- Usage --------------------------------------------------------------

    def save_usage(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ) -> None:
        """Save cumulative token usage for the session."""
        path = self._dir / session_id / "usage.json"
        data = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": round(cost, 4),
        }
        with open(path, "w") as f:
            json.dump(data, f)

    # -- Listing & retrieval ------------------------------------------------

    def list_sessions(self, limit: int = 20) -> list[SessionMeta]:
        """List recent sessions, newest first."""
        index = self._load_index()
        # Sort by updated_at descending
        index.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        result = []
        for entry in index[:limit]:
            result.append(SessionMeta(**{
                k: entry.get(k, "")
                for k in SessionMeta.__dataclass_fields__
            }))
        return result

    def get_latest(self) -> SessionMeta | None:
        """Return the most recently updated session, or None."""
        sessions = self.list_sessions(limit=1)
        return sessions[0] if sessions else None

    def get_session(self, session_id: str) -> SessionMeta | None:
        """Return metadata for a specific session."""
        return self._read_meta(session_id)

    # -- Internal helpers ---------------------------------------------------

    def _session_dir(self, session_id: str) -> Path:
        return self._dir / session_id

    def _write_meta(self, meta: SessionMeta) -> None:
        path = self._session_dir(meta.id) / "meta.json"
        with open(path, "w") as f:
            json.dump(asdict(meta), f, indent=2)

    def _read_meta(self, session_id: str) -> SessionMeta | None:
        path = self._session_dir(session_id) / "meta.json"
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
        return SessionMeta(**{
            k: data.get(k, "")
            for k in SessionMeta.__dataclass_fields__
        })

    def _load_index(self) -> list[dict[str, Any]]:
        path = self._dir / "index.json"
        if not path.exists():
            return []
        with open(path) as f:
            return json.load(f)

    def _update_index(self, meta: SessionMeta) -> None:
        """Add or update a session entry in the index."""
        index = self._load_index()
        entry = asdict(meta)
        # Replace existing or append
        for i, item in enumerate(index):
            if item.get("id") == meta.id:
                index[i] = entry
                break
        else:
            index.append(entry)

        path = self._dir / "index.json"
        with open(path, "w") as f:
            json.dump(index, f, indent=2)
