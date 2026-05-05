"""Tests for agent_service.api.routes — REST API endpoints.

Uses an in-memory SQLite database and httpx.AsyncClient with FastAPI's
ASGI transport for isolated, fast testing.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_service.database import Base
from agent_service.models import Conversation, Message, TokenUsage  # noqa: F401 — import to register models

from fastapi import FastAPI
from agent_service.api.routes import router
from agent_service.api import routes as routes_module
from agent_service.database import get_session


# ---------------------------------------------------------------------------
# In-memory database setup
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite database, yield a session factory, and tear down."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def app(db_session: async_sessionmaker):
    """Build a minimal FastAPI app with routes and overridden DB session."""
    test_app = FastAPI()
    test_app.include_router(router)

    async def override_get_session() -> AsyncSession:
        async with db_session() as session:
            yield session

    test_app.dependency_overrides[get_session] = override_get_session

    # Inject minimal module-level state that routes.py reads
    routes_module.set_settings(None)
    routes_module.set_skill_loader(None)
    routes_module.set_prompt_loader(None)
    routes_module.set_tool_info([
        {"name": "bash", "description": "Run shell"},
        {"name": "read_file", "description": "Read a file"},
    ])

    yield test_app

    test_app.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI):
    """httpx async client pointed at the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_create_chat(client: AsyncClient):
    resp = await client.post("/api/chat", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "conversation_id" in data
    assert len(data["conversation_id"]) == 12


async def test_create_chat_with_options(client: AsyncClient):
    resp = await client.post(
        "/api/chat",
        json={
            "preset": "coding",
            "enable_teams": True,
            "enable_tracing": True,
            "enable_approval": True,
            "enable_thinking": True,
            "thinking_effort": "max",
        },
    )
    assert resp.status_code == 200
    conv_id = resp.json()["conversation_id"]

    # Verify via GET detail
    detail_resp = await client.get(f"/api/conversations/{conv_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["preset"] == "coding"
    assert detail["enable_teams"] is True
    assert detail["enable_tracing"] is True
    assert detail["enable_approval"] is True
    assert detail["enable_thinking"] is True
    assert detail["thinking_effort"] == "max"


async def test_list_conversations(client: AsyncClient):
    # Create two conversations
    await client.post("/api/chat", json={})
    await client.post("/api/chat", json={})

    resp = await client.get("/api/conversations")
    assert resp.status_code == 200
    convs = resp.json()
    assert len(convs) == 2
    for c in convs:
        assert "id" in c
        assert "created_at" in c
        assert "message_count" in c


async def test_get_conversation_detail(client: AsyncClient):
    create_resp = await client.post("/api/chat", json={"preset": "work"})
    conv_id = create_resp.json()["conversation_id"]

    resp = await client.get(f"/api/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == conv_id
    assert data["preset"] == "work"
    assert data["messages"] == []
    assert data["total_input_tokens"] == 0
    assert data["total_output_tokens"] == 0


async def test_get_conversation_not_found(client: AsyncClient):
    resp = await client.get("/api/conversations/nonexistent")
    assert resp.status_code == 404


async def test_delete_conversation(client: AsyncClient):
    create_resp = await client.post("/api/chat", json={})
    conv_id = create_resp.json()["conversation_id"]

    del_resp = await client.delete(f"/api/conversations/{conv_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Should be gone
    get_resp = await client.get(f"/api/conversations/{conv_id}")
    assert get_resp.status_code == 404


async def test_delete_conversation_not_found(client: AsyncClient):
    resp = await client.delete("/api/conversations/nonexistent")
    assert resp.status_code == 404


async def test_list_tools(client: AsyncClient):
    resp = await client.get("/api/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) == 2
    names = {t["name"] for t in tools}
    assert "bash" in names
    assert "read_file" in names


async def test_list_skills(client: AsyncClient):
    resp = await client.get("/api/skills")
    assert resp.status_code == 200
    # No skill loader set => empty list
    assert resp.json() == []


async def test_list_presets(client: AsyncClient):
    resp = await client.get("/api/presets")
    assert resp.status_code == 200
    # No prompt loader set => empty list
    assert resp.json() == []
