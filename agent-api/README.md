# OpenAgent

Production agentic system — backend API, web UI, and terminal CLI. Built by **Walden AI Lab**.

## Install

```bash
git clone <your-fork-or-local-copy>
cd openagent/agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

The Python package split in this repository is:

- [`openagent-core`](https://pypi.org/project/openagent-core/) — backend library
- [`openagent-app`](https://pypi.org/project/openagent-app/) — terminal CLI

Install from PyPI when you only need the packaged artifacts:

```bash
pip install openagent-core
pip install openagent-app
```

---

Built with **FastAPI + WebSocket** and production-style agent loop patterns.

## Architecture

```
Client (WebSocket) ──> FastAPI ──> Agent Loop ──> LLM Client Chain ──> LLM Provider
                                      │               │
                          ┌───────────┼───────────┐   │ AnthropicAdapter / OpenAIAdapter
                          │           │           │   │  → RetryingLLMClient
                      ToolRegistry  TaskManager  SkillLoader  → TracingLLMClient (opt-in)
                          │
          ┌───────┬───────┼───────┬────────┬──────────┐
          │       │       │       │        │          │
       bash    file    task    background  team     compact
               tools  (subagent) tools    tools(opt-in)
```

### Core Pattern

The same loop from the reference — the model IS the agent:

```python
while not done:
    micro_compact(messages)              # Layer 1: trim old tool results
    drain background notifications       # inject async results
    drain inbox messages                 # inject team messages
    if near turn limit: add wrap-up hint # nudge model to finish up
    response = model(messages, tools)    # stream text deltas over WS
    if truncated (max_tokens): continue  # auto-continue cut-off responses
    if no tool calls: break              # agent decides when it's done
    execute tools, send results back     # send tool events over WS
    append to messages, continue
else:
    final_summary = model(messages, [])  # force text-only summary
```

The agent uses the **think tool** to self-verify its work before finishing — no separate verification or summary phases. The model decides when to verify, what to check, and whether to fix issues, all within the normal tool loop.

### Key Components

| Component | Description |
|-----------|-------------|
| **Agent Loop** (`agent/loop.py`) | Streaming while-loop with three-layer compaction, background draining, inbox draining, truncation auto-continuation, wrap-up nudging, forced final summary on turn exhaustion, and think-tool self-verification. |
| **RetryingLLMClient** (`agent/llm.py`) | Transparent retry wrapper with jittered exponential backoff for transient API errors. |
| **TracingLLMClient** (`agent/llm.py`) | Per-session LLM wrapper that emits `llm_request`/`llm_response` WebSocket events with full API payloads. |
| **ToolRegistry** (`agent/tools/registry.py`) | Pluggable registry — register name + JSON schema + async handler. |
| **TaskManager** (`agent/task_manager.py`) | Persistent file-backed task system with dependency graph and cascade. |
| **BackgroundManager** (`agent/background_manager.py`) | Async background command execution with notification queue. |
| **TeammateManager** (`agent/teammate_manager.py`) | Spawns named agent teammates with WORK/IDLE state machine. |
| **MessageBus** (`agent/message_bus.py`) | Per-agent async mailbox (asyncio.Queue + optional JSONL persistence). |
| **ProtocolTracker** (`agent/protocol_tracker.py`) | Request-response correlation for shutdown and plan approval protocols. |
| **TodoManager** (`agent/todo_manager.py`) | Legacy per-conversation task list (kept for backward compat). |
| **SkillLoader** (`agent/skill_loader.py`) | Reads SKILL.md files, progressive disclosure (metadata → full body). |
| **Subagents** (`agent/tools/task_tool.py` + loop) | Spawns child agent with isolated context. No recursion (max depth 2). |

## Quick Start

### Public Deployment

- User UI: [https://openagent.walden.chat](https://openagent.walden.chat)
- Developer UI: [https://openagent-dev.walden.chat](https://openagent-dev.walden.chat)

### 1. Install

```bash
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set LLM_PROVIDER and the matching API key
```

### 3. Run

```bash
# Backend (port 8000)
uvicorn agent_service.main:app --reload --reload-exclude 'workspace/*'

# Developer Frontend (port 3500) — full tool visibility, dev panel, file browser
cd ../agent-ui && python3 -m http.server 3500
# Open http://localhost:3500

# User Frontend (port 3501) — simplified consumer-grade UI
cd ../agent-user-ui && python3 -m http.server 3501
# Open http://localhost:3501
```

#### Two Frontend Options

| | Developer UI (`agent-ui`, port 3500) | User UI (`agent-user-ui`, port 3501) |
|---|---|---|
| **Audience** | Developers, debugging | End users, non-technical |
| **Theme** | Dark (GitHub-dark) | Light (Forest Canopy) |
| **Tool calls** | Collapsible blocks with JSON | Hidden, activity indicator pill |
| **Subagents** | Cards with stats | "Researching..." indicator |
| **New chat** | Preset selector + toggle switches | Auto-create, no modal |
| **Dev panel** | WebSocket traffic inspector | None |
| **File browser** | Right-side panel (browse + upload) | Right-side panel (browse + upload) |
| **Token usage** | Header display | Hidden |
| **Feature toggles** | Teams, Approval, Plan Mode buttons | None |

When the UIs are served from a non-localhost origin, they default to same-origin API and WebSocket endpoints. For local development on `localhost` or `127.0.0.1`, they default to `http://localhost:8000` and `ws://localhost:8000`.

### 4. Test

```bash
# Health check
curl http://localhost:8000/health

# Create a conversation
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{}'

# Connect via WebSocket (use wscat, websocat, or any WS client)
wscat -c ws://localhost:8000/api/chat/{conversation_id}/ws

# Send a message
> {"type": "message", "content": "List the files in the workspace"}
```

### Docker

```bash
cp .env.example .env   # set LLM_PROVIDER and the matching API key
docker compose up --build
```

## Storage Model

- Workspace files live under `WORKSPACE_DIR` (`workspace/` by default).
- Uploaded files and agent-created files share that same workspace root.
- Workspace cleanup is deferred by `WORKSPACE_CLEANUP_DELAY` seconds after session disconnect, so generated files are temporary unless you mount `workspace/` to persistent storage.
- Conversation history is stored in the SQL database configured by `DATABASE_URL` (`agent.db` by default) and is not removed by workspace cleanup.
- Without app-level authentication, conversations are global to the deployment rather than user-scoped.

## Execution Isolation

OpenAgent currently uses a **workspace-based execution model**, not a full sandbox.

### What the current model does

- File tools are constrained to paths inside `WORKSPACE_DIR`.
- Shell commands run with `WORKSPACE_DIR` as their working directory.
- Workspace cleanup removes generated files after a delay, while preserving memory and task metadata directories.
- The workspace provides a clear place to inspect agent-created artifacts during and after a run.

### What the current model does not do

- It does not run tool commands inside Docker or a VM by default.
- It does not isolate the process from the host operating system.
- It does not provide container-level CPU, memory, filesystem, or network isolation.
- It does not create per-user security boundaries on its own.

So `WORKSPACE_DIR` should be understood as a **working directory root** for tool execution, not as a hardened sandbox boundary.

### Current safety mechanisms

- File-path validation prevents `read_file`, `write_file`, and `edit_file` from escaping the workspace.
- Bash commands have a timeout via `BASH_TIMEOUT`.
- Known dangerous shell patterns are blocked.
- `ALLOWED_COMMANDS` can be used to enforce an explicit command allowlist.
- Optional human approval can gate tool execution before side-effecting operations run.

These controls are useful for local development, demos, and trusted environments, but they are still weaker than real container isolation.

### Recommended production model

For stronger isolation in hosted environments, run tools inside a per-session Docker or VM sandbox and mount a dedicated workspace into that sandbox.

A typical production shape is:

- create one sandbox per session, conversation, or run
- mount a dedicated workspace volume into the sandbox
- execute shell commands, background jobs, and code edits inside that sandbox
- enforce CPU, memory, time, and optionally network limits
- persist selected artifacts outside the sandbox before teardown

In that model, `WORKSPACE_DIR` remains useful, but it becomes the mounted root **inside** the sandbox rather than the host execution boundary.

## API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/chat` | Create new conversation → `{conversation_id}`. Body: `{preset?, enable_teams?, enable_tracing?, enable_approval?}` |
| `GET` | `/api/conversations` | List all conversations |
| `GET` | `/api/conversations/{id}` | Get conversation history + token usage |
| `DELETE` | `/api/conversations/{id}` | Delete a conversation |
| `GET` | `/api/tools` | List available tools |
| `GET` | `/api/skills` | List available skills |
| `POST` | `/api/skills` | Upload a new skill |
| `GET` | `/api/presets` | List available prompt presets |
| `GET` | `/api/workspace/files` | List all workspace files (excludes `.agent/`, `.transcripts/`, `.tasks/`, `.team/`) |
| `GET` | `/api/workspace/file/{path}` | Read file content for preview → `{path, name, size, content, binary, language}`. Text files return content with language detection; binary files return `content: null, binary: true`. Truncated at 100 KB. |
| `POST` | `/api/workspace/upload` | Upload files to workspace. Accepts `multipart/form-data` with `files` field (multiple). Optional `?subdir=` query param for target subdirectory. 10 MB per-file limit. Returns `{uploaded: [paths]}`. |

### WebSocket Protocol

Connect to `ws://host/api/chat/{conversation_id}/ws`

**Send** (client → server):
```json
{"type": "message", "content": "Your prompt here"}
{"type": "interrupt", "content": "Redirect the agent mid-stream"}
{"type": "cancel"}
{"type": "tool_approval_response", "decision": "approve|deny|auto_approve"}
```

**Receive** (server → client) — JSON events:

| Event | Fields | Description |
|-------|--------|-------------|
| `text_delta` | `content` | Streamed text from the model |
| `tool_call` | `tool`, `input` | Model is calling a tool |
| `tool_result` | `tool`, `result` | Tool execution result |
| `tool_approval_request` | `tools: [{name, input, id}]` | Waiting for user approval (when approval enabled) |
| `tool_approval_result` | `decision`, `tools` | Tools were denied by user |
| `subagent_start` | `subagent_id`, `task`, `agent_type` | Subagent spawned |
| `subagent_end` | `subagent_id`, `summary`, `agent_type`, `usage` | Subagent completed |
| `todo_update` | `todos` | Todo list changed (legacy) |
| `task_update` | `tasks` | Task list changed |
| `background_result` | `notifications` | Background command completed |
| `teammate_status` | `name`, `role`, `status` | Teammate state changed |
| `compact` | `message` | Context was compacted |
| `llm_request` | `seq`, `model`, `messages`, `tools`, `max_tokens` | LLM API request (when tracing enabled) |
| `llm_response` | `seq`, `content`, `tool_calls`, `done`, `usage` | LLM API response (when tracing enabled) |
| `interrupted` | `usage`, `files` | Agent turn interrupted by user feedback (new turn starting) |
| `done` | `usage`, `files` | Agent loop finished |
| `error` | `message` | Error occurred |

## Built-in Tools

### Core Tools

| Tool | Description |
|------|-------------|
| `bash` | Run shell commands (with timeout + safety checks) |
| `read_file` | Read file contents (within workspace) |
| `write_file` | Create/overwrite files |
| `edit_file` | Surgical text replacement |
| `task` | Spawn a subagent (general/explore/code/plan/research) |
| `list_skills` | List available skills |
| `read_skill` | Load skill knowledge |
| `think` | Dedicated reasoning space — self-verification, planning, analysis (no-op, no side effects) |
| `compact` | Trigger manual context compaction (with optional focus) |

### Task Management Tools

| Tool | Description |
|------|-------------|
| `task_create` | Create a persistent task with subject, description, activeForm |
| `task_get` | Get full task details by ID |
| `task_update` | Update status, add dependencies (blockedBy/blocks), set owner |
| `task_list` | List all tasks with status and dependency info |

### Background Execution Tools

| Tool | Description |
|------|-------------|
| `background_run` | Run a command asynchronously, returns task_id immediately |
| `check_background` | Check status/result of a background task |

### Team Tools

| Tool | Description |
|------|-------------|
| `spawn_teammate` | Spawn a named teammate with role and initial task |
| `list_teammates` | List all teammates with roles and status |
| `send_message` | Send a message to a specific teammate |
| `read_inbox` | Read and drain all messages from the lead's inbox |
| `broadcast` | Send a message to all active teammates |
| `shutdown_request` | Send graceful shutdown request to a teammate |
| `check_protocol` | Check status of a protocol request by request_id |
| `plan_review` | Approve or reject a plan submitted by a teammate |

### Legacy Todo Tools

| Tool | Description |
|------|-------------|
| `todo_write` | Replace entire task list |
| `todo_add` | Add a single task |
| `todo_complete` | Mark a task done |
| `todo_list` | Show current tasks |

## Key Features

### LLM Retry with Exponential Backoff

`RetryingLLMClient` wraps any `LLMClient` transparently. Retries on transient errors (HTTP 429/500/502/503/529, `ConnectionError`, `TimeoutError`) with jittered exponential backoff: `min(base * 2^attempt + random(0,1), max_delay)`. Only retries `create()` and initial `stream()` connection — never mid-stream failures.

### LLM Tracing

`TracingLLMClient` wraps any `LLMClient` per-session and emits full API request/response payloads as WebSocket events. Enabled per-conversation via `enable_tracing: true` at creation time. Uses a monotonic `seq` counter to pair requests with responses. Captures all LLM calls — main loop, subagents, and teammates — through a single wrapper point in `websocket.py`. The frontend dev panel provides a dedicated "LLM Traces" filter with purple-coded entries and compact previews (model, message count, tool count, token usage).

### Per-Conversation Feature Flags

Teams, tracing, and tool approval are opt-in per conversation via `enable_teams`, `enable_tracing`, and `enable_approval` booleans (default false). Set at creation time in `POST /api/chat`. The frontend new-conversation modal provides toggle switches for all three. When teams is disabled, no team infrastructure (MessageBus, ProtocolTracker, TeammateManager) is created and team tools are not registered.

### Tool Approval

When `enable_approval` is true, the agent loop pauses before executing "dangerous" tools and waits for user approval via WebSocket. Read-only tools (think, read_file, list_skills, etc.) auto-execute without prompting. Unsafe tools trigger a `tool_approval_request` event; the user can **Approve** (execute normally), **Deny** (LLM receives "User denied this tool call" and adjusts), or **Auto-approve rest** (disables approval for the remainder of the session). 5-minute timeout prevents hanging on disconnect. Subagents run autonomously once the `task` tool itself is approved.

### Three-Layer Context Compaction

1. **Micro-compact** (every turn, zero LLM cost) — replaces old tool_result content (>100 chars, except last 3 results) with `[Previous: used {tool_name}]`
2. **Auto-compact with transcript preservation** — when input exceeds `compact_threshold x context_window`, saves full history to `workspace/.transcripts/transcript_{timestamp}.jsonl` before LLM summarization
3. **Manual compact tool** — agent calls `compact` to trigger compaction on demand with optional focus parameter

### Persistent Task System

File-backed tasks at `workspace/.tasks/task_{id}.json` with dependency graph:
- **Dependency cascade**: completing a task removes it from all other tasks' `blockedBy` lists
- **Bidirectional linking**: `addBlocks` on task A auto-adds A to the target's `blockedBy`
- Survives context compaction and server restarts
- Concurrent-safe via `asyncio.Lock` + `asyncio.to_thread()` for file I/O

### Background Task Execution

Long-running commands (builds, tests, installs) run asynchronously via `asyncio.create_subprocess_shell()`. Results are collected in a notification queue and injected as synthetic message pairs at the top of each agent loop turn — the agent discovers results naturally without polling.

### Agent Teams (opt-in)

Enabled per-conversation via `enable_teams: true`. Named agent teammates run their own agent loops as `asyncio.Task` instances. Communication via `MessageBus` (per-agent `asyncio.Queue`). Teammates get bash, file tools, and messaging — but cannot spawn other teammates.

**WORK/IDLE state machine:**
- WORK phase: standard agent loop with inbox draining before each LLM call
- IDLE phase: polls inbox + task board every 5 seconds for 60 seconds
- Auto-claims unclaimed tasks from the task board
- Auto-shutdown after idle timeout
- Identity re-injection after context compaction

**Protocols:**
- Shutdown: lead sends request → teammate responds → teammate exits on approval
- Plan approval: teammate submits plan → lead reviews → teammate receives decision

### Mid-Stream Interrupt / Feedback

Users can redirect the agent while it's running — no need to wait for the current turn to finish.

**Web UI:** Type a message while the agent is streaming and press Enter. The current turn is cancelled, the feedback is injected as a new user message, and the agent restarts with full context. A cancel/stop button is also available to cancel without feedback. The input remains enabled during streaming with a "Type to interrupt the agent..." placeholder.

**CLI:** Press Ctrl+C during execution. The agent stops and a `feedback>` prompt appears. Type redirection text to re-run the agent with context, or press Enter to skip and return to the normal prompt.

The backend uses an `interrupt_queue` per WebSocket session. When an interrupt message arrives, the `cancelled` event is set (cooperative cancellation), and the content is queued. After the agent loop breaks, the handler checks the queue — if content is found, it sends an `interrupted` event and continues with a new turn using the interrupt content. Orphaned `tool_use` blocks (from mid-tool-call interrupts) are automatically sanitized to prevent API errors.

### Self-Verification via Think Tool

Instead of rigid verify/summary phases injected by the loop, the agent uses the `think` tool to verify its own work before finishing. The system prompt instructs the agent to review tool results for errors, confirm all parts of the request are addressed, and re-read modified files if needed. If issues are found, the agent fixes them with tools and re-verifies — all within the normal loop. The loop simply exits when the agent responds with no tool calls.

This gives the agent full autonomy over verification: it decides *when* to verify, *what* to check, and *whether* to fix issues, rather than being forced through a fixed state machine.

### Loop Completion Guarantees

The agent loop ensures the model always produces a final response, even in edge cases:

1. **Truncation auto-continuation** — when the model hits `max_output_tokens` mid-response (`stop_reason=max_tokens`), the loop automatically injects a "[continue from where you left off]" prompt and resumes. Up to 3 continuations per session. This prevents the model from writing code but stopping before executing it.
2. **Wrap-up nudge** — 3 turns before the `max_turns` limit, the system prompt is augmented with a hint telling the model to finish up and not start new tasks.
3. **Forced final summary** — if the loop exhausts all turns without the model finishing on its own, one final no-tools LLM call is made to produce a text summary of what was accomplished.

### Workspace Directories

| Directory | Purpose |
|-----------|---------|
| `.agent/` | Session memory (`memory.md`) |
| `.transcripts/` | Compaction audit trail (JSONL files) |
| `.tasks/` | Persistent task files (JSON) |
| `.team/` | Team config + inbox persistence |

All excluded from workspace file listing and deferred cleanup.

## Adding Custom Tools

Register a new tool in `agent/loop.py`:

```python
MY_TOOL_DEF = {
    "name": "my_tool",
    "description": "What it does",
    "input_schema": {
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "..."}
        },
        "required": ["param"]
    }
}

async def run_my_tool(args: dict, **kwargs) -> str:
    return f"Result: {args['param']}"

# In build_registry():
registry.register("my_tool", MY_TOOL_DEF, run_my_tool)
```

## Adding Skills

Create a folder under `skills/` with a `SKILL.md` file:

```
skills/
└── my-skill/
    ├── SKILL.md        # Required
    ├── scripts/        # Optional helper scripts
    └── references/     # Optional docs
```

`SKILL.md` format:

```markdown
---
name: my-skill
description: One-line description of when to use this skill.
---

# My Skill

Detailed instructions the model will follow when this skill is loaded.
```

The model calls `read_skill` to load the skill content on-demand.

## Configuration

All settings via environment variables or `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | LLM backend to use (`anthropic` or `openai`) |
| `ANTHROPIC_API_KEY` | — | Required for `anthropic` |
| `ANTHROPIC_BASE_URL` | — | Optional Anthropic-compatible base URL |
| `OPENAI_API_KEY` | — | Required for `openai` |
| `OPENAI_BASE_URL` | — | Optional OpenAI-compatible base URL |
| `MODEL` | `claude-sonnet-4-5-20250929` | Model to use |
| `MAX_TURNS` | `50` | Max agent loop iterations |
| `MAX_TOKEN_BUDGET` | `200000` | Total token budget per request |
| `MAX_OUTPUT_TOKENS` | `16384` | Max tokens per model response |
| `CONTEXT_WINDOW` | `200000` | Model's context window size (tokens) |
| `COMPACT_THRESHOLD` | `0.7` | Auto-compact when input exceeds this fraction of context window |
| `LLM_MAX_RETRIES` | `3` | Max retry attempts for transient LLM errors |
| `LLM_RETRY_BASE_DELAY` | `1.0` | Base delay in seconds for retry backoff |
| `LLM_RETRY_MAX_DELAY` | `30.0` | Maximum delay in seconds between retries |
| `SKILLS_DIR` | `skills` | Path to skills directory |
| `PROMPTS_DIR` | `prompts` | Path to prompt presets directory |
| `WORKSPACE_DIR` | `workspace` | Workspace root for file tools and command execution |
| `WORKSPACE_CLEANUP_DELAY` | `300` | Seconds before workspace cleanup after session ends |
| `BASH_TIMEOUT` | `60` | Seconds before bash commands timeout |
| `BACKGROUND_TIMEOUT` | `300` | Max seconds for background commands |
| `ALLOWED_COMMANDS` | `[]` | Whitelist for bash (empty = allow all) |
| `MAX_TEAMMATES` | `5` | Max concurrent teammate agents |
| `ENABLE_MEMORY` | `true` | Enable cross-session memory persistence |
| `DATABASE_URL` | `sqlite+aiosqlite:///./agent.db` | SQLAlchemy async URL |
