<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    A beginner-friendly, source-available AI coding agent for learning how agents work by building and running one yourself.
  </p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> &bull;
    <a href="#features">Features</a> &bull;
    <a href="#architecture">Architecture</a> &bull;
    <a href="#testing">Testing</a> &bull;
    <a href="#documentation">Docs</a> &bull;
    <a href="#contributing">Contributing</a>
  </p>
  <p align="center">
    <strong>Translations:</strong>&nbsp;
    <a href="docs/README_zh.md">中文</a> &bull;
    <a href="docs/README_ja.md">日本語</a> &bull;
    <a href="docs/README_ko.md">한국어</a> &bull;
    <a href="docs/README_es.md">Español</a> &bull;
    <a href="docs/README_fr.md">Français</a>
  </p>
</p>

---

## What Is This?

OpenAgent is a beginner-first AI coding agent project for people who are curious how modern agents work. You can **run it locally**, **read every line of it**, and **learn by changing real code instead of studying abstract diagrams**.

You type a message like *"Create a REST API with authentication"*, and the agent:

1. Reads your codebase to understand the context
2. Plans an approach (optionally in read-only plan mode)
3. Writes code, runs commands, creates files using tools
4. Verifies its own work before finishing
5. Reports back with results — all streamed in real time

```
You: "Add user authentication with JWT tokens"

Agent: [thinking] Let me explore the codebase first...
       [read_file] src/app.py — found the Flask app
       [read_file] requirements.txt — no auth libraries yet
       [bash] pip install PyJWT bcrypt
       [write_file] src/auth.py — JWT token generation
       [edit_file] src/app.py — added login/register routes
       [bash] python -m pytest tests/ — all 12 tests pass

       Done! I've added JWT authentication with login and
       register endpoints. Here's what I created: ...
```

## Repository Scope

This monorepo contains the OpenAgent runtime stack and the repo-governance files needed
to publish and maintain it as a source-available project.

- Runtime projects: `agent-api/`, `agent-cli/`, `agent-ui/`, `agent-user-ui/`
- Repo operations: `.github/`, `docs/`, `README.md`, `CONTRIBUTING.md`, `LICENSE`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`

## Why This Project?

Most AI agent projects are either too abstract for beginners or too closed to learn from properly. OpenAgent is:

- **Readable** — the core loop is ~30 lines. No frameworks, no magic.
- **Educational** — built for beginners who want to learn agent architecture by running it, tracing it, and changing it.
- **Complete** — web UI, terminal CLI, streaming, tools, memory, teams, plan mode.
- **Documented** — includes contributor guidance, security policy, translations, and component-level technical references.
- **LLM-independent** — the core loop targets a shared `LLMClient` interface instead of a single model vendor.
- **Extensible** — add a new tool in 20 lines. Add or swap provider adapters without rewriting the loop.

## Quick Start

### Prerequisites

- Python 3.11+ (3.14 recommended)
- Credentials for your chosen LLM provider or compatible endpoint

### Option 1a: Developer Web UI

```bash
# Clone your fork or local copy
git clone <your-fork-or-local-copy>
cd openagent

# Backend
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
cat > .env <<'EOF'
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
EOF
uvicorn agent_service.main:app --reload

# Developer Frontend (new terminal)
cd /path/to/openagent/agent-ui
python3 -m http.server 3500

# Open http://localhost:3500
```

### Option 1b: User Web UI

```bash
# Same backend as above, then in a new terminal:
cd /path/to/openagent/agent-user-ui
python3 -m http.server 3501

# Open http://localhost:3501
```

The User UI is a lighter, user-facing interface with a Forest Canopy light theme, activity indicators instead of raw tool blocks, and simplified approval dialogs. Both UIs connect to the same backend.

### Option 2: Terminal CLI

```bash
cd openagent
python -m venv .venv && source .venv/bin/activate
pip install -e agent-api -e agent-cli
openagent
```

### Option 3: Pipe mode (non-interactive)

```bash
echo "Explain how binary search works" | openagent --no-approval
```

## Features

### Core

| Feature | Description |
|---------|-------------|
| **Agentic loop** | While-loop that streams LLM responses, executes tools, and repeats until done |
| **15+ built-in tools** | Bash, file read/write/edit, think, compact, skills, tasks, background commands |
| **Streaming** | Real-time token-by-token output via WebSocket |
| **Tool approval** | Optional human-in-the-loop confirmation before dangerous operations |
| **Plan mode** | Read-only exploration phase — agent designs a plan before making changes |
| **Agent-initiated planning** | Agent autonomously enters plan mode for complex tasks |
| **Sub-agents** | Spawn focused child agents (explore, code, plan, research) for subtasks |
| **Agent teams** | Multiple named agents working in parallel with async message passing |

### Intelligence

| Feature | Description |
|---------|-------------|
| **3-layer compaction** | Micro-compact, auto-compact with transcripts, manual compact tool |
| **Persistent memory** | Agent remembers your preferences across sessions |
| **Self-verification** | Uses think tool to check its own work before finishing |
| **Wrap-up nudging** | Hints to finish when approaching turn limits |
| **Truncation recovery** | Auto-continues when response hits token limit |

### Developer Experience

| Feature | Description |
|---------|-------------|
| **Developer UI** | Dark-themed chat interface with markdown, syntax highlighting, file browser, dev panel |
| **User UI** | Light-themed (Forest Canopy) user-facing interface with activity indicators, simplified dialogs |
| **Terminal CLI** | Rich REPL with history, autocomplete, vi mode, session persistence |
| **Dev panel** | Raw WebSocket frame inspector in the browser |
| **LLM tracing** | See exact prompts and responses sent to the model |
| **Presets** | Swappable system prompt personas (coding, office productivity, etc.) |
| **Skills** | On-demand expert knowledge (API design, Docker, PDF generation, etc.) |

## Architecture

```
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   agent-ui   │  │  agent-user-ui   │  │  agent-cli   │
│  (Developer) │  │     (User)       │  │  (Terminal)  │
│  port 3500   │  │   port 3501      │  │              │
└──────┬───────┘  └────────┬─────────┘  └──────┬───────┘
       │ WebSocket         │ WebSocket         │ Direct call
       └──────────┬────────┘                   │
                  └─────────────┬───────────────┘
                                ▼
                  ┌─────────────────┐
                  │    agent-api     │
                  │    (FastAPI)     │
                  ├─────────────────┤
                  │   Agent Loop     │  ◄── while not done: stream → tools → repeat
                  ├─────────────────┤
                  │  Tool Registry   │  ◄── bash, files, think, plan_mode, compact, ...
                  ├─────────────────┤
                  │   LLM Client     │  ◄── provider-independent adapter boundary
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │ LLM Provider │  (any supported or compatible backend)
                    └────────────┘
```

More backend architecture detail lives in [agent-api/README.md](agent-api/README.md) and [agent-api/CLAUDE.md](agent-api/CLAUDE.md).

## Project Structure

```
openagent/
├── agent-api/          # FastAPI backend + agent logic
│   ├── src/agent_service/
│   │   ├── main.py           # App entrypoint
│   │   ├── agent/loop.py     # Core agentic loop (~1200 lines)
│   │   ├── agent/llm.py      # Provider-agnostic LLM abstraction
│   │   ├── agent/tools/      # All tool implementations
│   │   └── api/websocket.py  # WebSocket streaming handler
│   ├── skills/               # SKILL.md expert knowledge files
│   ├── prompts/              # PROMPT.md system prompt presets
│   └── tests/                # Backend test suite
├── agent-cli/          # Terminal CLI interface
│   ├── src/agent_cli/
│   │   ├── app.py            # REPL orchestrator
│   │   ├── renderer.py       # Rich terminal output
│   │   └── commands.py       # Slash commands (/plan, /model, etc.)
│   └── tests/                # CLI test suite
├── agent-ui/           # Developer web frontend (no build step)
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # ES modules (app, renderer, websocket, etc.)
├── agent-user-ui/      # User-facing web frontend (no build step)
│   ├── index.html
│   ├── css/styles.css        # Forest Canopy light theme
│   └── js/                   # ES modules (app, renderer, websocket, etc.)
├── docs/                # Translated root READMEs
├── .github/             # CI, issue templates, PR template
├── HOW_IT_WORKS.md      # Architecture guide for the runtime stack
├── CONTRIBUTING.md     # Contribution guidelines
├── CODE_OF_CONDUCT.md  # Community expectations
├── SECURITY.md         # Vulnerability disclosure policy
├── LICENSE             # Business Source License 1.1
├── .env.example        # Environment variable reference
└── REMOTE-CONTROL.md   # Notes for remote-control usage
```

See [docs/REPOSITORY.md](docs/REPOSITORY.md) for a path-by-path map of the monorepo and maintainer notes about the preserved pre-monorepo histories.

## Testing

```bash
# Backend
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# Developer UI
cd agent-ui && npm test

# User UI
cd agent-user-ui && npm test

# Lint + type check
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## Configuration

Set environment variables in `agent-api/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | LLM backend to use (`anthropic` or `openai`) |
| `ANTHROPIC_API_KEY` | (required) | Your Anthropic API key |
| `ANTHROPIC_BASE_URL` | unset | Optional API endpoint override |
| `OPENAI_API_KEY` | (required for OpenAI) | Your OpenAI API key |
| `OPENAI_BASE_URL` | unset | Optional OpenAI-compatible endpoint |
| `MODEL` | `claude-sonnet-4-5-20250929` | Default model |
| `WORKSPACE_DIR` | `workspace` | Where agent files are created |
| `ENABLE_MEMORY` | `true` | Cross-session memory |
| `MAX_TURNS` | `50` | Max agent loop iterations |
| `MAX_TOKEN_BUDGET` | `200000` | Token spending limit per session |
| `OPENAGENT_TIMEOUT` | `1800` | CLI agent loop hard timeout (seconds) |

### Using different LLM backends

```bash
# OpenAI
LLM_PROVIDER=openai OPENAI_API_KEY=your-key MODEL=gpt-4.1

# Anthropic-compatible endpoint
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat

# Any other compatible backend
# Implement or extend the adapter layer in agent-api/src/agent_service/agent/llm.py
```

## Documentation

| Document | Audience | Description |
|----------|----------|-------------|
| [README.md](README.md) | Everyone | Product overview, setup, testing, and configuration |
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | Contributors | Architecture walkthrough of the runtime stack |
| [docs/REPOSITORY.md](docs/REPOSITORY.md) | Contributors | Monorepo layout and maintainer notes |
| [CLAUDE.md](agent-api/CLAUDE.md) | AI agents / developers | Comprehensive technical reference |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributors | Branch naming, commit format, PR checklist |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community | Expected behavior and enforcement process |
| [SECURITY.md](SECURITY.md) | Security researchers | Private vulnerability disclosure guidance |
| [REMOTE-CONTROL.md](REMOTE-CONTROL.md) | Operators | Remote-control setup and operational notes |
| [.env.example](.env.example) | Operators | All environment variables with descriptions |
| [docs/README_zh.md](docs/README_zh.md) | Chinese readers | Chinese translation of the root README |
| [docs/README_ja.md](docs/README_ja.md) | Japanese readers | Japanese translation of the root README |
| [docs/README_ko.md](docs/README_ko.md) | Korean readers | Korean translation of the root README |
| [docs/README_es.md](docs/README_es.md) | Spanish readers | Spanish translation of the root README |
| [docs/README_fr.md](docs/README_fr.md) | French readers | French translation of the root README |

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines. Some good starting points:

- **Add a new tool** — copy `agent-api/src/agent_service/agent/tools/compact_tool.py`, modify, register in `loop.py`
- **Add a new skill** — create `agent-api/skills/your-skill/SKILL.md`
- **Add a new preset** — create `agent-api/prompts/your-preset/PROMPT.md`
- **Add a new LLM backend** — implement the `LLMClient` protocol in `agent/llm.py`
- **Improve the Developer UI** — edit files in `agent-ui/` directly (no build step)
- **Improve the User UI** — edit files in `agent-user-ui/` directly (no build step)

Please run the test suites before submitting (CI runs these automatically on PRs):

```bash
cd agent-api && .venv/bin/python -m pytest tests/ -v
cd agent-cli && .venv/bin/python -m pytest tests/ -v
cd agent-ui && npm test
cd agent-user-ui && npm test
```

You can also run all checks at once with pre-commit:

```bash
pre-commit run --all-files
```

## License

Business Source License 1.1 (BSL 1.1)

See [LICENSE](LICENSE) for the Additional Use Grant, Change Date, and Change License.

OpenAgent is source-available under BSL 1.1, not OSI open source.

For commercial licensing inquiries, contact Walden AI Lab through the repository
owner contact channel on the repository hosting platform.

For security issues, use [SECURITY.md](SECURITY.md). For community expectations, use [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Acknowledgments

Built as a learn-by-doing reference implementation for beginners, using production-style agent patterns with a provider-independent LLM adapter layer.
