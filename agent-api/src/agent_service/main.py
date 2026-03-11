"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_service.agent.llm import RetryingLLMClient, build_raw_llm_client
from agent_service.agent.mcp_manager import MCPManager
from agent_service.agent.prompt_loader import PromptLoader
from agent_service.agent.skill_loader import SkillLoader
from agent_service.agent.tools.bash_tool import DEFINITION as BASH_DEF
from agent_service.agent.tools.code_nav_tools import (
    FIND_REFERENCES_DEFINITION,
    LIST_SYMBOLS_DEFINITION,
    READ_FILE_RANGE_DEFINITION,
    SEARCH_CODE_DEFINITION,
)
from agent_service.agent.tools.file_tools import (
    EDIT_DEFINITION,
    READ_DEFINITION,
    WRITE_DEFINITION,
)
from agent_service.agent.tools.skill_tools import (
    LIST_SKILLS_DEFINITION,
    READ_SKILL_DEFINITION,
)
from agent_service.agent.tools.background_tools import (
    BACKGROUND_RUN_DEFINITION,
    CHECK_BACKGROUND_DEFINITION,
)
from agent_service.agent.tools.team_tools import (
    BROADCAST_DEFINITION,
    CHECK_PROTOCOL_DEFINITION,
    LIST_TEAMMATES_DEFINITION,
    PLAN_REVIEW_DEFINITION,
    READ_INBOX_DEFINITION,
    SEND_MESSAGE_DEFINITION,
    SHUTDOWN_REQUEST_DEFINITION,
    SPAWN_TEAMMATE_DEFINITION,
)
from agent_service.agent.tools.compact_tool import DEFINITION as COMPACT_DEF
from agent_service.agent.tools.thinking_tool import DEFINITION as THINK_DEF
from agent_service.agent.tools.task_mgmt_tools import (
    TASK_CREATE_DEFINITION,
    TASK_GET_DEFINITION,
    TASK_LIST_DEFINITION,
    TASK_UPDATE_DEFINITION,
)
from agent_service.agent.tools.task_tool import TASK_DEFINITION
from agent_service.agent.tools.todo_tools import (
    TODO_ADD_DEFINITION,
    TODO_COMPLETE_DEFINITION,
    TODO_LIST_DEFINITION,
    TODOWRITE_DEFINITION,
)
from agent_service.api import routes, websocket
from agent_service.config import AppState, Settings
from agent_service.database import close_db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    # Database
    await init_db(settings.database_url)
    logger.info("Database initialized: %s", settings.database_url)

    # LLM client (provider-agnostic via adapter, with retry wrapper)
    raw_llm = build_raw_llm_client(
        provider=settings.llm_provider,
        anthropic_api_key=settings.anthropic_api_key,
        anthropic_base_url=settings.anthropic_base_url,
        openai_api_key=settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
    )
    llm = RetryingLLMClient(
        raw_llm,
        max_retries=settings.llm_max_retries,
        base_delay=settings.llm_retry_base_delay,
        max_delay=settings.llm_retry_max_delay,
    )

    # Skill loader — use configured path if it exists, otherwise bundled data
    from agent_service.paths import get_skills_dir, get_prompts_dir

    skills_path = Path(settings.skills_dir)
    if not skills_path.is_absolute() and not skills_path.exists():
        skills_path = get_skills_dir()
    skill_loader = SkillLoader(str(skills_path))
    logger.info("Skills loaded: %s", skill_loader.list_skills() or "none")

    # Prompt loader — same fallback logic
    prompts_path = Path(settings.prompts_dir)
    if not prompts_path.is_absolute() and not prompts_path.exists():
        prompts_path = get_prompts_dir()
    prompt_loader = PromptLoader(str(prompts_path))
    logger.info("Presets loaded: %s", [p["name"] for p in prompt_loader.list_presets()] or "none")

    # MCP servers (optional — no file = no MCP)
    mcp_manager = MCPManager.from_config_file(settings.mcp_servers_file)
    if mcp_manager:
        await mcp_manager.connect_all()
        logger.info("MCP tools: %s", mcp_manager.get_tool_names() or "none")

    # Build tool info list for GET /api/tools
    all_defs = [
        BASH_DEF,
        READ_DEFINITION,
        READ_FILE_RANGE_DEFINITION,
        SEARCH_CODE_DEFINITION,
        LIST_SYMBOLS_DEFINITION,
        FIND_REFERENCES_DEFINITION,
        WRITE_DEFINITION,
        EDIT_DEFINITION,
        TODOWRITE_DEFINITION,
        TODO_ADD_DEFINITION,
        TODO_COMPLETE_DEFINITION,
        TODO_LIST_DEFINITION,
        LIST_SKILLS_DEFINITION,
        READ_SKILL_DEFINITION,
        COMPACT_DEF,
        THINK_DEF,
        TASK_CREATE_DEFINITION,
        TASK_GET_DEFINITION,
        TASK_UPDATE_DEFINITION,
        TASK_LIST_DEFINITION,
        BACKGROUND_RUN_DEFINITION,
        CHECK_BACKGROUND_DEFINITION,
        SPAWN_TEAMMATE_DEFINITION,
        LIST_TEAMMATES_DEFINITION,
        SEND_MESSAGE_DEFINITION,
        READ_INBOX_DEFINITION,
        BROADCAST_DEFINITION,
        SHUTDOWN_REQUEST_DEFINITION,
        CHECK_PROTOCOL_DEFINITION,
        PLAN_REVIEW_DEFINITION,
        TASK_DEFINITION,
    ]
    tool_info = [{"name": d["name"], "description": d["description"]} for d in all_defs]
    if mcp_manager:
        tool_info.extend(mcp_manager.get_tool_info())

    # Centralized app state — single source of truth
    app_state = AppState(
        settings=settings,
        client=llm,
        skill_loader=skill_loader,
        prompt_loader=prompt_loader,
        mcp_manager=mcp_manager,
        tool_info=tool_info,
    )
    app.state.app_state = app_state

    # Wire up routes + websocket with shared state (legacy injection kept for compatibility)
    routes.set_settings(settings)
    routes.set_skill_loader(skill_loader)
    routes.set_prompt_loader(prompt_loader)
    routes.set_tool_info(tool_info)

    websocket.configure(settings, llm, skill_loader, prompt_loader, mcp_manager)

    logger.info("Agent service ready — model=%s", settings.model)
    yield

    if mcp_manager:
        await mcp_manager.disconnect_all()
    await close_db()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = Settings()

    app = FastAPI(
        title="Agent Service",
        description="Production agentic loop backend — FastAPI + WebSocket",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST routes
    app.include_router(routes.router)

    # WebSocket route
    app.include_router(websocket.ws_router)

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "model": settings.model}

    return app


app = create_app()
