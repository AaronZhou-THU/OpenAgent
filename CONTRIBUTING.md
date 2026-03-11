# Contributing to OpenAgent

By participating in this project, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Getting Started

1. Clone the repository
2. Install the Python packages in editable mode:
   ```bash
   cd agent-api && python -m venv .venv && source .venv/bin/activate && pip install -e ".[test]"
   cd ../agent-cli && python -m venv .venv && source .venv/bin/activate && pip install -e ".[test]"
   ```
3. Install the Developer UI test dependencies:
   ```bash
   cd ../agent-ui && npm ci
   ```
4. Copy `.env.example` to `agent-api/.env` and configure your API key

## Repository Focus

Most code contributions should target one of these runtime projects:

- `agent-api/` — FastAPI backend and agent loop
- `agent-cli/` — terminal interface
- `agent-ui/` — developer-facing web UI
- `agent-user-ui/` — simplified end-user web UI

If you are unsure where a change belongs, check [docs/REPOSITORY.md](docs/REPOSITORY.md) before opening a PR.

## Branch Naming

- `feature/<description>` — new features
- `fix/<description>` — bug fixes
- `refactor/<description>` — code improvements
- `docs/<description>` — documentation changes
- `test/<description>` — test additions/fixes

## Commit Format

Use conventional commits:
```
type(scope): description

body (optional)
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`

Scopes: `api`, `cli`, `ui`, `user-ui`, `tools`, `loop`, `teams`

## Pull Request Checklist

- [ ] The PR is scoped to the intended runtime component or documentation area
- [ ] Tests pass: `cd agent-api && pytest tests/ -v`
- [ ] Tests pass: `cd agent-cli && pytest tests/ -v`
- [ ] Tests pass: `cd agent-ui && npm test`
- [ ] No new linting errors: `ruff check src/ tests/`
- [ ] Formatting is correct: `ruff format --check src/ tests/`
- [ ] New features have corresponding tests
- [ ] Security-sensitive changes have bypass tests

## Testing Requirements

- All new tools must have unit tests in `agent-api/tests/`
- Integration tests should use `ScriptedLLMClient` (never call a real API)
- Security-sensitive features (bash tool, file tools, path validation) need bypass tests
- Frontend behavior changes in `agent-ui/` should include or update Vitest coverage where practical
- Target: maintain existing test count or above

## Architecture Notes

- The LLM layer is provider-agnostic — never import `anthropic` outside `llm.py` and `main.py`
- Tools are registered via `ToolRegistry` — add new tools in `agent/tools/` and wire them in `loop.py:build_registry()`
- The agent loop is the core — changes there require comprehensive integration tests
- There are two web frontends: `agent-ui` (developer-facing, dark theme, tool blocks, dev panel) and `agent-user-ui` (user-facing, Forest Canopy light theme, activity indicators, simplified dialogs). Both connect to the same `agent-api` backend via WebSocket.
