# AGENTS.md

This file gives coding agents the minimum backend-specific context needed to
work safely in `openagent/agent-api`.

For the full technical walkthrough, see `CLAUDE.md`. Use this file first, then
open `CLAUDE.md` only when you need deeper subsystem detail.

## Scope

- Package: `openagent-core`
- Import root: `agent_service`
- Runtime: FastAPI backend for OpenAgent
- Main entrypoint: `src/agent_service/main.py`

## Goal Of This Package

This backend is a beginner-friendly, learn-by-doing reference implementation of
an AI coding agent. Prefer changes that keep the system understandable:

- Keep the control flow explicit.
- Avoid introducing framework-heavy abstractions.
- Preserve the provider-agnostic `LLMClient` boundary.
- Prefer small, readable changes over clever indirection.

## Primary Files

- `src/agent_service/main.py`: app startup, lifespan wiring, shared state
- `src/agent_service/api/routes.py`: REST endpoints
- `src/agent_service/api/websocket.py`: streaming session orchestration
- `src/agent_service/agent/loop.py`: core agent loop
- `src/agent_service/agent/llm.py`: provider adapters and LLM wrappers
- `src/agent_service/agent/tools/`: tool implementations
- `src/agent_service/config.py`: settings and app state
- `src/agent_service/schemas.py`: request and response models
- `tests/`: backend tests

## Design Rules

- Keep `agent/loop.py` as the central execution loop: stream -> tools -> repeat.
- Do not couple the loop or websocket layer directly to a specific SDK.
- New model providers belong behind `LLMClient` in `agent/llm.py`.
- New tools should register through the tool registry, not by special-casing the loop.
- Prefer async-safe changes. Most runtime paths are async and WebSocket-driven.
- Preserve the beginner-first architecture. If a change makes the system harder
  to explain, it needs a strong reason.

## Common Tasks

### Add a tool

1. Add the implementation under `src/agent_service/agent/tools/`.
2. Register it through the registry/loop wiring.
3. Keep the JSON schema explicit and minimal.
4. Add or update tests.

### Add an LLM backend

1. Implement the `LLMClient` protocol in `src/agent_service/agent/llm.py`.
2. Keep retries/tracing as wrappers instead of embedding them in the adapter.
3. Wire provider selection through config, not hardcoded branches in unrelated files.

### Change WebSocket behavior

1. Start in `src/agent_service/api/websocket.py`.
2. Check event names already emitted to the UIs/CLI before renaming anything.
3. If the event contract changes, update consumers in `../agent-ui/`,
   `../agent-user-ui/`, and `../agent-cli/`.

## Local Commands

```bash
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .[test]
uvicorn agent_service.main:app --reload
```

## Verification

Run the narrowest useful checks first.

```bash
cd agent-api
.venv/bin/python -m pytest tests/test_schemas.py -q
.venv/bin/python -m pytest tests/ -v
.venv/bin/ruff check src/ tests/
```

If your change touches streaming behavior or shared contracts, also check the
dependent packages:

```bash
cd ../agent-cli && .venv/bin/python -m pytest tests/ -v
cd ../agent-ui && npm test
```

## Environment Notes

- Configuration lives in `.env` and `src/agent_service/config.py`.
- The backend is LLM-independent. Existing adapters target Anthropic and OpenAI
  style backends, but new work should preserve the abstraction.
- SQLite is used locally by default.
- Workspace-facing features must stay scoped to the configured workspace path.

## Documentation

- `README.md`: package overview and setup
- `CLAUDE.md`: detailed architecture reference
- `../HOW_IT_WORKS.md`: beginner-friendly system walkthrough

## License

This repository uses Business Source License 1.1. Check `../LICENSE` before
adding license-sensitive text or metadata.
