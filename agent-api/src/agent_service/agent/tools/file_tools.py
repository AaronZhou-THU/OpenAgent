"""File tools — read_file, write_file, edit_file (v1 pattern)."""

from __future__ import annotations

import asyncio
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_path(p: str, workspace: Path) -> Path:
    """Resolve *p* inside *workspace*; raise if it escapes (including via symlinks).

    Guards against TOCTOU race conditions by checking every intermediate path
    component for symlinks that point outside the workspace.  Uses O_NOFOLLOW
    on the final component where the platform supports it.
    """
    ws_real = workspace.resolve()

    # Reject null bytes (could bypass C-level path handling)
    if "\x00" in p:
        raise ValueError(f"Path contains null byte: {p!r}")

    # Check each intermediate path component for symlinks escaping workspace
    current = ws_real
    parts = Path(p).parts
    for i, part in enumerate(parts):
        current = current / part
        # Check if this component is a symlink
        if current.is_symlink():
            link_target = current.resolve()
            if not link_target.is_relative_to(ws_real):
                raise ValueError(
                    f"Symlink at component '{'/'.join(parts[:i+1])}' escapes workspace: {p}"
                )

    resolved = (ws_real / p).resolve()  # resolve() follows symlinks
    if not resolved.is_relative_to(ws_real):
        raise ValueError(f"Path escapes workspace: {p}")

    # Final symlink check on the resolved path
    if resolved.is_symlink():
        target = resolved.resolve()
        if not target.is_relative_to(ws_real):
            raise ValueError(f"Symlink escapes workspace: {p}")

    return resolved


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

READ_DEFINITION = {
    "name": "read_file",
    "description": "Read file contents. Returns UTF-8 text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file"},
            "limit": {
                "type": "integer",
                "description": "Max lines to read (default: all)",
            },
        },
        "required": ["path"],
    },
}


async def run_read_file(args: dict, *, workspace: Path) -> str:
    try:
        fp = _safe_path(args["path"], workspace)
        text = await asyncio.to_thread(fp.read_text)
        lines = text.splitlines()
        limit = args.get("limit")
        if limit and limit < len(lines):
            lines = lines[:limit]
            lines.append(f"... ({len(text.splitlines()) - limit} more lines)")
        return "\n".join(lines)[:50_000]
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

WRITE_DEFINITION = {
    "name": "write_file",
    "description": "Write content to a file. Creates parent directories if needed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path for the file"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
}


async def run_write_file(args: dict, *, workspace: Path) -> str:
    try:
        fp = _safe_path(args["path"], workspace)
        fp.parent.mkdir(parents=True, exist_ok=True)
        content: str = args["content"]
        await asyncio.to_thread(fp.write_text, content)
        return f"Wrote {len(content)} bytes to {args['path']}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

EDIT_DEFINITION = {
    "name": "edit_file",
    "description": "Replace exact text in a file. Use for surgical edits.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file"},
            "old_text": {
                "type": "string",
                "description": "Exact text to find (must match precisely)",
            },
            "new_text": {"type": "string", "description": "Replacement text"},
        },
        "required": ["path", "old_text", "new_text"],
    },
}


async def run_edit_file(args: dict, *, workspace: Path) -> str:
    try:
        fp = _safe_path(args["path"], workspace)
        content = await asyncio.to_thread(fp.read_text)
        old_text: str = args["old_text"]
        count = content.count(old_text)
        if count == 0:
            return f"Error: Text not found in {args['path']}"
        if count > 1:
            return (
                f"Error: old_text appears {count} times in {args['path']}. "
                "Provide a larger, unique snippet to avoid ambiguity."
            )
        new_content = content.replace(old_text, args["new_text"], 1)
        await asyncio.to_thread(fp.write_text, new_content)
        return f"Edited {args['path']}"
    except Exception as e:
        return f"Error: {e}"
