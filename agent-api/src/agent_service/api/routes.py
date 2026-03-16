"""REST API routes."""

from __future__ import annotations

import mimetypes
import uuid

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_service.agent.prompt_loader import PromptLoader
from agent_service.agent.skill_loader import SkillLoader
from agent_service.agent.tools.registry import ToolRegistry
from agent_service.api.auth import get_current_user
from agent_service.config import Settings
from agent_service.database import get_session
from agent_service.models import Conversation, Message, TokenUsage
from agent_service.schemas import (
    ConversationDetail,
    ConversationInfo,
    CreateChatRequest,
    CreateChatResponse,
    MessageInfo,
    PresetInfo,
    SkillInfo,
    ToolInfo,
    UploadSkillRequest,
)

router = APIRouter(prefix="/api")

# These are injected by main.py at startup
_settings: Settings | None = None
_skill_loader: SkillLoader | None = None
_prompt_loader: PromptLoader | None = None
_tool_names: list[dict] | None = None


def set_settings(s: Settings) -> None:
    global _settings
    _settings = s


def set_skill_loader(sl: SkillLoader) -> None:
    global _skill_loader
    _skill_loader = sl


def set_prompt_loader(pl: PromptLoader) -> None:
    global _prompt_loader
    _prompt_loader = pl


def set_tool_info(info: list[dict]) -> None:
    global _tool_names
    _tool_names = info


# ---------------------------------------------------------------------------
# POST /api/chat — create a new conversation
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=CreateChatResponse)
async def create_chat(
    req: CreateChatRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict | None = Depends(get_current_user),
):
    conv_id = uuid.uuid4().hex[:12]
    conv = Conversation(
        id=conv_id,
        system_prompt=req.system_prompt,
        preset=req.preset,
        enable_teams=req.enable_teams,
        enable_tracing=req.enable_tracing,
        enable_approval=req.enable_approval,
        enable_plan_mode=req.enable_plan_mode,
    )
    session.add(conv)
    await session.commit()
    return CreateChatResponse(conversation_id=conv_id)


# ---------------------------------------------------------------------------
# GET /api/conversations
# ---------------------------------------------------------------------------

@router.get("/conversations", response_model=list[ConversationInfo])
async def list_conversations(
    session: AsyncSession = Depends(get_session),
    _user: dict | None = Depends(get_current_user),
):
    result = await session.execute(
        select(
            Conversation.id,
            Conversation.title,
            Conversation.created_at,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .group_by(Conversation.id)
        .order_by(Conversation.created_at.desc())
    )
    return [
        ConversationInfo(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            message_count=row.message_count,
        )
        for row in result.all()
    ]


# ---------------------------------------------------------------------------
# GET /api/conversations/{id}
# ---------------------------------------------------------------------------

@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict | None = Depends(get_current_user),
):
    conv = await session.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")

    msg_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
    )
    msgs = msg_result.scalars().all()

    usage_result = await session.execute(
        select(
            func.coalesce(func.sum(TokenUsage.input_tokens), 0),
            func.coalesce(func.sum(TokenUsage.output_tokens), 0),
        ).where(TokenUsage.conversation_id == conv_id)
    )
    usage_row = usage_result.one()

    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        system_prompt=conv.system_prompt,
        preset=conv.preset,
        enable_teams=conv.enable_teams,
        enable_tracing=conv.enable_tracing,
        enable_approval=conv.enable_approval,
        enable_plan_mode=conv.enable_plan_mode,
        created_at=conv.created_at,
        messages=[
            MessageInfo(role=m.role, content=m.content, created_at=m.created_at)
            for m in msgs
        ],
        total_input_tokens=usage_row[0],
        total_output_tokens=usage_row[1],
    )


# ---------------------------------------------------------------------------
# DELETE /api/conversations/{id}
# ---------------------------------------------------------------------------

@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict | None = Depends(get_current_user),
):
    conv = await session.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")

    # Delete related rows first (messages, token_usage)
    await session.execute(
        Message.__table__.delete().where(Message.conversation_id == conv_id)
    )
    await session.execute(
        TokenUsage.__table__.delete().where(TokenUsage.conversation_id == conv_id)
    )
    await session.delete(conv)
    await session.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# GET /api/tools
# ---------------------------------------------------------------------------

@router.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    if _tool_names is None:
        return []
    return [ToolInfo(**t) for t in _tool_names]


# ---------------------------------------------------------------------------
# GET /api/skills
# ---------------------------------------------------------------------------

@router.get("/skills", response_model=list[SkillInfo])
async def list_skills():
    if _skill_loader is None:
        return []
    return [
        SkillInfo(name=name, description=s["description"])
        for name, s in _skill_loader.skills.items()
    ]


# ---------------------------------------------------------------------------
# GET /api/presets
# ---------------------------------------------------------------------------

@router.get("/presets", response_model=list[PresetInfo])
async def list_presets():
    if _prompt_loader is None:
        return []
    return [PresetInfo(**p) for p in _prompt_loader.list_presets()]


# ---------------------------------------------------------------------------
# POST /api/skills — upload a new skill
# ---------------------------------------------------------------------------

@router.post("/skills", response_model=SkillInfo)
async def upload_skill(req: UploadSkillRequest):
    if _skill_loader is None:
        raise HTTPException(500, "Skill loader not initialized")
    _skill_loader.add_skill(req.name, req.description, req.body)
    return SkillInfo(name=req.name, description=req.description)


# ---------------------------------------------------------------------------
# GET /api/files/{conv_id}/{file_path} — download a workspace file
# ---------------------------------------------------------------------------

@router.get("/files/{conv_id}/{file_path:path}")
async def download_file(conv_id: str, file_path: str):
    if _settings is None:
        raise HTTPException(500, "Settings not initialized")

    workspace = Path(_settings.workspace_dir).resolve()
    target = (workspace / file_path).resolve()

    # Security: must be inside workspace and not inside .agent/
    if not str(target).startswith(str(workspace)):
        raise HTTPException(403, "Access denied")
    try:
        relative = target.relative_to(workspace)
    except ValueError:
        raise HTTPException(403, "Access denied")
    if relative.parts and relative.parts[0] == ".agent":
        raise HTTPException(403, "Access denied")

    if not target.is_file():
        raise HTTPException(404, "File not found")

    return FileResponse(
        path=target,
        filename=target.name,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Workspace file browsing (for file panel)
# ---------------------------------------------------------------------------

_SKIP_DIRS = {".agent", ".transcripts", ".tasks", ".team"}

# Extension → language name for syntax highlighting
_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx",
    ".jsx": "jsx", ".json": "json", ".html": "html", ".css": "css",
    ".md": "markdown", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml",
    ".xml": "xml", ".sql": "sql", ".sh": "bash", ".bash": "bash",
    ".zsh": "bash", ".rs": "rust", ".go": "go", ".java": "java",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".rb": "ruby",
    ".php": "php", ".swift": "swift", ".kt": "kotlin", ".r": "r",
    ".csv": "plaintext", ".txt": "plaintext", ".log": "plaintext",
    ".env": "plaintext", ".ini": "ini", ".cfg": "ini",
    ".dockerfile": "dockerfile", ".makefile": "makefile",
}

_MAX_CONTENT_BYTES = 100 * 1024  # 100 KB
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB per file


@router.post("/workspace/upload")
async def upload_workspace_files(
    files: list[UploadFile],
    subdir: str = Query("", description="Target subdirectory inside workspace"),
):
    """Upload one or more files to the workspace."""
    if _settings is None:
        raise HTTPException(500, "Settings not initialized")

    workspace = Path(_settings.workspace_dir).resolve()

    # Resolve the target directory
    target_dir = (workspace / subdir).resolve() if subdir else workspace
    if not str(target_dir).startswith(str(workspace)):
        raise HTTPException(403, "Access denied")
    try:
        relative_dir = target_dir.relative_to(workspace)
    except ValueError:
        raise HTTPException(403, "Access denied")
    if relative_dir.parts and relative_dir.parts[0] in _SKIP_DIRS:
        raise HTTPException(403, "Cannot upload into restricted directory")

    target_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for f in files:
        # Read content and enforce size limit
        content = await f.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"File '{f.filename}' exceeds 10 MB limit "
                f"({len(content) / (1024 * 1024):.1f} MB)",
            )

        # Sanitize filename and verify path stays inside workspace
        safe_name = Path(f.filename).name  # strip directory components
        dest = (target_dir / safe_name).resolve()
        if not str(dest).startswith(str(workspace)):
            raise HTTPException(403, "Access denied")

        dest.write_bytes(content)
        uploaded.append(str(dest.relative_to(workspace)))

    return {"uploaded": uploaded}


@router.get("/workspace/files")
async def list_workspace_files():
    """List all workspace files (mirrors _list_workspace_files in websocket.py)."""
    if _settings is None:
        raise HTTPException(500, "Settings not initialized")

    workspace = Path(_settings.workspace_dir).resolve()
    if not workspace.exists():
        return []

    files = []
    for item in workspace.rglob("*"):
        if not item.is_file():
            continue
        try:
            rel = item.relative_to(workspace)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in _SKIP_DIRS:
            continue
        files.append({
            "name": item.name,
            "path": str(rel),
            "size": item.stat().st_size,
        })
    return files


@router.get("/workspace/file/{file_path:path}")
async def read_workspace_file(file_path: str):
    """Read workspace file content for preview."""
    if _settings is None:
        raise HTTPException(500, "Settings not initialized")

    workspace = Path(_settings.workspace_dir).resolve()
    target = (workspace / file_path).resolve()

    # Security: must be inside workspace and not inside hidden dirs
    if not str(target).startswith(str(workspace)):
        raise HTTPException(403, "Access denied")
    try:
        relative = target.relative_to(workspace)
    except ValueError:
        raise HTTPException(403, "Access denied")
    if relative.parts and relative.parts[0] in _SKIP_DIRS:
        raise HTTPException(403, "Access denied")

    if not target.is_file():
        raise HTTPException(404, "File not found")

    ext = target.suffix.lower()
    language = _EXT_LANG.get(ext, None)
    size = target.stat().st_size

    # Detect binary vs text
    mime, _ = mimetypes.guess_type(target.name)
    is_binary = False
    content = None

    if mime and (
        mime.startswith("image/")
        or mime.startswith("audio/")
        or mime.startswith("video/")
        or mime == "application/octet-stream"
    ):
        is_binary = True
    elif ext in (
        ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar", ".gz",
        ".bz2", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
        ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ):
        is_binary = True

    if not is_binary:
        try:
            raw = target.read_bytes()
            # Quick binary check: look for null bytes in first 8KB
            if b"\x00" in raw[:8192]:
                is_binary = True
            else:
                text = raw.decode("utf-8", errors="replace")
                if len(raw) > _MAX_CONTENT_BYTES:
                    text = text[: _MAX_CONTENT_BYTES] + "\n\n... (truncated at 100 KB)"
                content = text
        except Exception:
            is_binary = True

    return {
        "path": str(relative),
        "name": target.name,
        "size": size,
        "content": content,
        "binary": is_binary,
        "language": language,
    }
