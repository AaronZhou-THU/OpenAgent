# OpenAgent

Production agentic system — backend API, web UI, and terminal CLI.

## PyPI Packages

- **`openagent-core`** — backend library (PyPI name; import as `agent_service`)
- **`openagent-app`** — CLI (PyPI name; binary is `openagent`)

```bash
# Install from PyPI
pip install openagent-app
export ANTHROPIC_API_KEY=sk-ant-...
openagent
```

## Quick Start (development)

```bash
# Backend API (port 8000)
cd agent-api
source .venv/bin/activate
uvicorn agent_service.main:app --reload --reload-exclude 'workspace/*'

# Developer Frontend (port 3500) — shows tool calls, subagents, dev panel
cd ../agent-ui && python3 -m http.server 3500
# Open http://localhost:3500

# User Frontend (port 3501) — simplified, consumer-grade UI
cd ../agent-user-ui && python3 -m http.server 3501
# Open http://localhost:3501

# CLI (terminal interface)
cd ../agent-cli
.venv/bin/openagent
```

## Project Structure

- `src/agent_service/` — main package
  - `main.py` — FastAPI app, lifespan, CORS
  - `config.py` — pydantic-settings (env vars) + `AppState` dataclass for centralized application state
  - `database.py` — async SQLAlchemy + aiosqlite
  - `models.py` — Conversation (with `enable_teams`, `enable_tracing`, `enable_approval`, `enable_plan_mode` flags), Message, TokenUsage tables
  - `schemas.py` — Pydantic request/response models (CreateChatRequest includes `enable_teams`, `enable_tracing`, `enable_approval`, `enable_plan_mode`)
  - `api/routes.py` — REST endpoints (conversations CRUD, tools, skills, presets, file downloads, workspace file browsing, workspace file upload)
  - `api/websocket.py` — WebSocket handler for streaming agentic loop (per-session LLM wrapping for tracing, conditional team setup, tool approval queue routing, plan mode state tracking + approval/rejection flow, mid-conversation toggle for teams/approval/plan mode via WebSocket control messages, workspace file scanning + deferred cleanup, interrupt queue for mid-stream user feedback with `pending_content` loop restructure)
  - `agent/llm.py` — provider-agnostic LLM abstraction (LLMClient protocol + LLMResponse with `stop_reason` field + AnthropicAdapter with remote MCP support + RetryingLLMClient + TracingLLMClient with secret redaction via `_redact_sensitive()`)
  - `agent/loop.py` — core while-loop (stream model → execute tools → repeat) with three-layer compaction, background notification draining, inbox draining, tool approval gate, plan mode (read-only tool restriction + prompt injection + `plan_ready` event + agent-initiated enter/exit via sentinels with mid-loop tool/prompt switching), truncation auto-continuation, wrap-up nudging near turn limit, and forced final summary on turn exhaustion. Agent uses the think tool for self-verification (no separate phases). Includes `AgentContext` dataclass + `build_registry_from_context()` convenience wrapper to reduce `build_registry()` parameter count.
  - `agent/memory.py` — persistent session memory (MemoryManager + LLM-based analysis)
  - `agent/todo_manager.py` — per-conversation task list (legacy, kept for backward compat)
  - `agent/task_manager.py` — persistent file-backed task system with dependency graph (`workspace/.tasks/`), in-memory reverse dependency map for O(k) completion cascades
  - `agent/background_manager.py` — async background command execution with notification queue
  - `agent/message_bus.py` — per-agent async mailbox (asyncio.Queue + optional JSONL persistence via `asyncio.to_thread()` + per-agent `asyncio.Event` notification for instant wakeup)
  - `agent/teammate_manager.py` — spawns/manages named agent teammates with WORK/IDLE state machine
  - `agent/protocol_tracker.py` — request_id correlation for structured team protocols (shutdown, plan approval)
  - `agent/skill_loader.py` — reads SKILL.md files
  - `agent/mcp_manager.py` — MCP (Model Context Protocol) server management (MCPManager + MCPServerConfig + MCPConnection, client-mode via mcp SDK, remote-mode via Anthropic beta API)
  - `agent/prompt_loader.py` — reads PROMPT.md preset files (mirrors SkillLoader pattern)
  - `agent/paths.py` — resolves bundled data directories (skills, prompts) via `importlib.resources`, works both from source and pip install
  - `agent/tools/registry.py` — pluggable ToolRegistry
  - `agent/tools/` — bash, file, code-nav, todo, task (subagent), skill, compact, think, task_mgmt, background, team, plan_mode tools
  - `data/` — bundled package data (skills + prompts), symlinked from repo root for dev workflow
- `prompts/` → `src/agent_service/data/prompts/` — PROMPT.md preset files defining system prompt personas (symlink at repo root)
  - `coding/PROMPT.md` — software development preset (default). Includes parallel tool execution rules, speed optimizations (aggressive batching, think-alongside-tools, no redundant reads, bash for bulk exploration), and subagent parallelism preferences
  - `work/PROMPT.md` — office productivity preset (documents, spreadsheets, presentations). Same parallel/speed rules
- `skills/` → `src/agent_service/data/skills/` — SKILL.md files providing on-demand knowledge for the agent (symlink at repo root)
  - `api-design/` — REST API design (resource modeling, pagination, auth, OpenAPI, FastAPI/Express patterns)
  - `code-review/` — structured code reviews (security/correctness/performance checklists, language-specific anti-patterns for Python/JS/Go/Rust)
  - `design/` — frontend interfaces and visual artifacts (HTML/CSS/JS, PDF, PNG with distinctive aesthetics)
  - `dockerfile-builder/` — production Docker images and compose stacks (Python/Node/Go/Rust/nginx templates, multi-stage, security hardening)
  - `docx-writer/` — Word documents via python-docx (styled tables, headers/footers, TOC)
  - `excel-writer/` — Excel spreadsheets via openpyxl (formulas, charts, conditional formatting, data validation)
  - `pdf-writer/` — PDF documents via reportlab (styled tables, headers/footers, page layout) + PyPDF2 for reading/merging
  - `ppt-writer/` — PowerPoint presentations via python-pptx (slide templates, KPI cards, charts, two-column layouts)
- `../agent-ui/` — plain HTML/CSS/JS developer chat frontend (no build step)
- `../agent-user-ui/` — simplified user-facing chat frontend (Forest Canopy theme, no build step)
- `../agent-cli/` — terminal CLI (`openagent` command, prompt-toolkit REPL)

## CLI (`../agent-cli/`)

Rich terminal interface for the agent service. Binary: `openagent`. Python package: `agent_cli`.

- `src/agent_cli/main.py` — argparse entry point (`--version`, `--resume [ID]`, `-m`, `-p`, `-w`, `--teams`, `--plan`, `--no-approval`, `--no-memory`, `--max-turns`)
- `src/agent_cli/app.py` — slim REPL orchestrator (~300 lines): loads config → creates components → interactive loop or pipe mode. Integrates prompt-toolkit input, slash commands, session persistence, cost tracking, thinking spinner, signal handling (Ctrl+C interrupts turn with feedback prompt, Ctrl+D exits), plan mode state tracking with interactive approval prompt ([a]pprove/[r]eject/[f]eedback), mid-conversation teams toggle (creates/destroys MessageBus + ProtocolTracker + TeammateManager), mid-conversation approval toggle (creates/destroys approval queue + handler, rebuilds `send_event`). Hard timeout via `OPENAGENT_TIMEOUT` env var (default 1800s). Pipe mode auto-titles from first input line. Interrupt feedback: after Ctrl+C, shows feedback prompt; user can type redirection text (re-runs agent with context) or press Enter to skip. Uses `_skip_prompt` flag to bypass normal prompt when re-entering with feedback. `_sanitize_interrupted_messages()` strips orphaned `tool_use` blocks from interrupted assistant messages to prevent API 400 errors on re-run.
- `src/agent_cli/config.py` — `CLIConfig` dataclass, loads `~/.openagent/config.toml` via `tomllib`, `ensure_dirs()` creates data directory structure
- `src/agent_cli/cost.py` — `PRICING` table (Opus/Sonnet/Haiku per-million rates), `CostTracker` class with per-turn and cumulative cost, `format_usage_line()` → `"12,340 in · 2,100 out · $0.23 · 14% ctx"`. Logs warning when model not in PRICING table.
- `src/agent_cli/input.py` — prompt-toolkit `PromptSession` with `FileHistory` (~/.openagent/history), `AutoSuggestFromHistory` (fish-style), Esc+Enter for newline, vi_mode toggle
- `src/agent_cli/session.py` — `SessionStore` manages `~/.openagent/conversations/`. JSONL message persistence (append-only), `meta.json` per session, `index.json` for listing, `usage.json` for cost. Auto-title from first user message
- `src/agent_cli/commands.py` — Slash command registry with `@register` decorator. Commands: `/help`, `/clear`, `/compact`, `/model [name]`, `/history`, `/resume [id]`, `/cost`, `/plan`, `/execute`, `/teams on|off`, `/approval on|off`, `/quit`, `/exit`. Returns `CommandResult` with flags (handled, quit, clear, compact, new_session_id, plan_mode, teams, approval)
- `src/agent_cli/renderer.py` — Claude Code-style event renderer. `StreamingRenderer` class buffers streaming tokens and syntax-highlights completed fenced code blocks via `rich.Syntax`. Thinking spinner via `rich.Status`. Enhanced done line with cost. Handles all event types: text_delta, tool_call, tool_result, tool_approval, subagent (parallel: tracks `_subagent_count`, shows agent type label, spinner displays "Researching (N subagents)" when multiple active), todo, task, compact, background, teammate, plan_mode_changed, teams_changed, approval_changed, plan_ready, plan_approved, plan_rejected, interrupted, error, done
- `src/agent_cli/approval.py` — `ApprovalHandler` for interactive tool approval prompts (y/n/a)

### Data directory (`~/.openagent/`)

```
~/.openagent/
├── config.toml              # user defaults (model, preset, vi_mode, approval)
├── history                  # prompt-toolkit persistent history
└── conversations/
    ├── index.json           # [{id, title, preset, model, created_at, message_count}]
    └── {session-id}/
        ├── meta.json        # session metadata
        ├── messages.jsonl   # all messages (user, assistant, tool_result) — append-only
        └── usage.json       # {input_tokens, output_tokens, cost}
```

### CLI key features

- **Rich input**: prompt-toolkit with persistent history, fish-style auto-suggest, multiline (Esc+Enter), vi_mode
- **Interrupt with feedback**: Ctrl+C interrupts the current turn and shows a feedback prompt; type redirection text to re-run the agent with context, or press Enter to skip
- **Slash commands**: `/help`, `/clear`, `/compact`, `/model`, `/history`, `/resume`, `/cost`, `/plan`, `/execute`, `/teams`, `/approval`, `/quit`
- **Code block rendering**: completed fenced blocks → `rich.Syntax` with Monokai theme; plain text streams raw
- **Thinking spinner**: `rich.Status` spinner while waiting for first token
- **Session persistence**: save/resume conversations via `--resume [ID]` or `/resume`
- **Cost tracking**: per-turn and cumulative $ cost with context % indicator
- **Workspace**: defaults to current working directory (`$PWD`), override with `-w /path/to/dir`
- **Non-interactive pipe mode**: `echo "..." | openagent --no-approval`
- **Config file**: `~/.openagent/config.toml` for defaults (model, preset, vi_mode, approval)

### CLI dependencies

`rich>=14.0,<15.0`, `prompt-toolkit>=3.0,<4.0`, `anthropic>=0.42,<1.0`, `pydantic-settings>=2.6,<3.0`, `python-dotenv>=1.0,<2.0`, `agent-service` (sibling package). All dependencies pinned with upper bounds.

## User Frontend (`../agent-user-ui/`)

Consumer-grade chat UI for non-technical users — same backend (port 8000), same WebSocket protocol, all technical details abstracted away behind friendly activity indicators. Themed with **Forest Canopy** (light, warm, natural).

- `index.html` — HTML structure + CDN imports (marked.js, highlight.js github light theme, DOMPurify) + welcome screen with leaf SVG icon, prompt chips, plan overlay modal (hidden by default), no panels/modals
- `css/styles.css` — Forest Canopy light theme (forest green `#2d4a2b`, sage `#7d8471`, olive `#a4ac86`, ivory `#faf9f6`). Headers: Georgia serif. Body: system-ui sans-serif. Code: SF Mono monospace. Plan overlay (fixed full-screen backdrop, centered modal with slideUp animation, scrollable markdown content, feedback textarea). Plan summary card (collapsed/expandable with animated max-height toggle).
- `js/config.js` — API base URL (copied verbatim from agent-ui)
- `js/api.js` — REST client (conversations CRUD, chat, presets, file URLs, workspace file upload — workspace/tools/skills endpoints removed)
- `js/state.js` — simplified state + event bus (adds `activityText`, `planModeActive`, removes `todos`, `teamsActive`, `approvalActive`, token counters)
- `js/markdown.js` — marked.js + highlight.js configuration (copied verbatim from agent-ui)
- `js/websocket.js` — WebSocket connection manager (copied from agent-ui, `dev:` event emissions removed)
- `js/renderer.js` — DOM rendering: activity indicator pill (animated dots + contextual text), user bubbles (right-aligned dark green), assistant content (left-aligned markdown, no role labels), simplified tool approval dialog ("Permission needed" → Allow/Skip), plan overlay modal (`showPlanOverlay`/`hidePlanOverlay` with rendered markdown), plan summary card (`renderPlanSummaryCard` — collapsed "Plan approved" card with expand/collapse toggle showing full plan details), file cards, error cards. No tool blocks, no subagent blocks, no todo panel.
- `js/app.js` — main orchestrator: auto-create chat (silently uses first preset, no modal), prompt chip click fills input, simplified event handling (tool_call → activity indicator with "Looking into it..." during plan mode, tool_result/subagent/todo/task/background/teammate/compact/teams/approval → silent), plan overlay button wiring (Go ahead → approve + render summary card, I'd like some changes → feedback textarea → send rejection), plan_mode_changed/plan_ready/plan_approved/plan_rejected event handlers, interrupt dismisses plan overlay, mobile sidebar with backdrop overlay

### Key design decisions

- **Activity indicators replace tool blocks**: Single animated pill `● ● ● Searching files...` instead of raw tool names + JSON. Mapping: `bash` → "Running a command...", `read_file` → "Reading files...", `write_file`/`edit_file` → "Writing code...", `task` → "Researching...", `think` → "Thinking...", default → "Working...". Parallel subagents: tracks `activeSubagentCount` — shows "Working on N tasks..." when multiple subagents run simultaneously, "Researching..." for a single one
- **History skips tool_use blocks**: Only text content from assistant messages is rendered; `tool_use` blocks and `tool_result` user messages are filtered out
- **Auto-create chat**: "New Chat" silently fetches first preset and creates conversation — no preset selector modal, no toggle switches
- **No dev features**: No devpanel.js, no filepanel.js (but workspace upload is available in Files panel on agent-user-ui), no token usage display, no Teams/Approval/Plan Mode toggle buttons
- **Welcome screen**: Leaf icon (olive SVG), "How can I help you today?" (Georgia, forest green), 4 prompt chips (Write an email, Explain a concept, Analyze data, Write code) — clicking fills input but doesn't auto-send
- **Simplified dialogs**: Tool approval shows "Permission needed" with Allow/Skip (no tool names, no JSON). Plan review shows as a full-screen overlay modal titled "Here's what I'd like to do" with rendered markdown plan content, "Go ahead" / "I'd like some changes" buttons, and a hidden feedback textarea that reveals on click. After approval, a collapsed "Plan approved" summary card appears in the chat stream with an expand toggle to review plan details.
- **Responsive**: Desktop (>=769px): sidebar visible, floating centered pill input. Mobile (<=768px): sidebar as slide-in overlay with backdrop, full-width input at bottom.

### Served at port 3501

```bash
cd ../agent-user-ui && python3 -m http.server 3501
# Open http://localhost:3501
```

## Developer Frontend (`../agent-ui/`)

Plain HTML/CSS/JS chat UI — ES modules, zero build tooling. Served via any static file server.

- `index.html` — HTML structure + CDN imports (marked.js, highlight.js, DOMPurify for XSS sanitization) + cancel/stop button in input bar
- `css/styles.css` — dark theme (GitHub-dark inspired), responsive layout, cancel button + interrupt notice styles
- `js/config.js` — API base URL (override via `localStorage.setItem('API_BASE_URL', '...')`)
- `js/api.js` — REST client (conversations CRUD, chat with `enablePlanMode` param, tools, skills, presets, file download URLs, workspace file browsing, workspace file upload)
- `js/state.js` — app state + event bus (includes `planModeActive`, `pendingPlan`, `teamsActive`, `approvalActive`, `isInterrupting`)
- `js/markdown.js` — marked.js + highlight.js configuration, DOMPurify sanitization on all rendered HTML
- `js/renderer.js` — DOM rendering (messages, tool blocks, subagents with colored type badges, todos, interrupt notices) with ARIA attributes (`role`, `aria-busy`, `aria-label`) for accessibility. Parallel subagents tracked via `Map` (subagent_id → DOM block ID); each block shows agent type badge (explore=blue, code=green, plan=purple, research=orange)
- `js/websocket.js` — WebSocket connection manager with auto-reconnect and `ws:reconnect_failed` event on exhaustion; emits `dev:sent`, `dev:received`, `dev:status` events for raw traffic monitoring
- `js/devpanel.js` — self-contained dev panel module: toggleable bottom panel showing raw WebSocket frames with timestamps, color-coded direction arrows (blue `>>>` sent, green `<<<` received, purple `◊◊◊` LLM traces, yellow `---` status), event type badges, click-to-expand JSON, text_delta coalescing, LLM Traces filter, filter/clear/auto-scroll toolbar, drag-to-resize, localStorage persistence
- `js/filepanel.js` — self-contained file panel module: toggleable right-side panel (420px, flex child of `#app`) for browsing workspace files. File list with emoji icons and sizes; click to preview with syntax highlighting (highlight.js) or rendered markdown (marked.js). Back/refresh/close buttons. **File upload**: upload button (up-arrow) in header + hidden `<input type="file" multiple>` + drag-and-drop on panel body (dragover highlight, drop to upload). Uses `uploadWorkspaceFiles()` from api.js, auto-refreshes file list on success. Auto-refreshes on `done` WebSocket events, resets on `conversation:select`. localStorage persistence (`filepanel:open`). On mobile (<768px): full-width fixed overlay.
- `js/app.js` — main orchestrator, wires UI events to state/API/renderer. Dual-behavior `sendMessage()` (normal send vs interrupt mode based on `state.isStreaming`), `setStreamingUI()` toggles send/cancel buttons + placeholder text, cancel button handler sends `{"type": "cancel"}`, `interrupted` event handler

Features: sidebar with conversation list, new-conversation modal (preset selector + Enable Teams toggle + LLM Tracing toggle + Tool Approval toggle + Plan Mode toggle + Create button), streaming text with markdown, collapsible tool call/result blocks, tool approval blocks (orange-bordered with Approve/Deny/Auto-approve buttons), header toggle buttons for Teams (purple when active), Approval (orange when active), and Plan Mode (blue when active) — all toggleable mid-conversation via WebSocket, plan approval overlay modal (rendered markdown plan + Approve & Execute / Reject buttons + feedback textarea), parallel subagent cards with colored type badges (multiple subagents displayed simultaneously, each with independent spinners and completion stats), todo panel, file download cards, workspace file browser panel (right-side, syntax-highlighted preview, file upload via button + drag-and-drop), token usage display, connection status indicator, dev panel for raw WebSocket traffic inspection (with dedicated LLM Traces filter), mid-stream interrupt (type message while agent is running → sends interrupt, agent restarts with feedback in context), cancel/stop button in input bar during streaming.

## Environment

- Python 3.14 venv at `.venv/`
- Set `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_BASE_URL`, `MODEL`, `WORKSPACE_CLEANUP_DELAY` in `.env` (see `.env.example` for all variables with descriptions)
- Supports Anthropic-compatible APIs (e.g. DeepSeek: `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat`)
- Local proxy on this machine — use `curl --noproxy localhost` for testing
- DB: SQLite at `./agent.db` (auto-created on startup)

## Key Patterns

- **Provider-agnostic LLM layer**: `agent/llm.py` defines `LLMClient` protocol + `LLMResponse`/`ToolCall` dataclasses. The loop and websocket only depend on this protocol — never on a specific SDK. `AnthropicAdapter` is the current implementation; swap it in `main.py` to add new providers (OpenAI, Ollama, etc.)
- **Composable LLM wrapper chain**: `agent/llm.py` provides composable wrappers that stack transparently on any `LLMClient`. Production chain: `AnthropicAdapter → RetryingLLMClient → TracingLLMClient` (tracing optional per-session). Each wrapper adds one concern without coupling to others.
- **LLM retry with exponential backoff**: `RetryingLLMClient` wraps any `LLMClient` transparently. Retries `create()` and initial `stream()` connection on transient errors (429/500/502/503/529, ConnectionError, TimeoutError) with jittered exponential backoff. Does NOT retry mid-stream failures. Configured via `LLM_MAX_RETRIES`, `LLM_RETRY_BASE_DELAY`, `LLM_RETRY_MAX_DELAY`.
- **LLM tracing**: `TracingLLMClient` wraps any `LLMClient` and emits `llm_request`/`llm_response` WebSocket events with full API payloads (system prompt, messages, tools, usage, tool calls). All emitted payloads are passed through `_redact_sensitive()` which masks API keys, Bearer tokens, long base64 strings, and other secret patterns to prevent accidental credential leakage. Uses monotonic `seq` counter for request-response pairing. `_TracingStream` hooks `get_response()` to capture response after stream iteration. Created per-session in `websocket.py` when `enable_tracing` is true — wraps the shared global client so all LLM calls (main loop, subagents, teammates) flow through it.
- Agent loop in `agent/loop.py` — same pattern as reference v0-v4
- **Parallel tool execution**: multiple tool calls in one response run via `asyncio.gather()`. System prompts instruct the agent what to parallelize (multiple read-only reads/searches for different files, independent bash commands, multiple task subagents, think alongside anything) and what NOT to parallelize (write_file/edit_file to the same file, tools that depend on a previous tool's output). Subagent prompts have type-specific guidance matching their available tools.
- **Code navigation tools**: `agent/tools/code_nav_tools.py` adds read-only repo-intelligence primitives:
  - `read_file_range(path, start_line, end_line, include_line_numbers?)`
  - `search_code(query, path_glob?, regex?, case_sensitive?, max_results?)`
  - `list_symbols(path, max_results?)`
  - `find_references(symbol, path_glob?, case_sensitive?, whole_word?, max_results?)`
  These tools skip hidden/system folders (`.agent`, `.transcripts`, `.tasks`, `.team`, `.git`, etc.), cap large files/results, and are intended to reduce shell-heavy exploration.
- **Speed optimizations** (in both presets): (1) Batch aggressively — max independent tool calls per response to minimize LLM round-trips. (2) Call think alongside other tools, not as a separate step. (3) Think-before-acting — plan approach to avoid trial-and-error retries. (4) No redundant reads — don't re-read files just written. (5) Bash for bulk exploration — single grep/find vs many read_file calls. (6) Prefer multiple subagents in parallel for independent subtasks. (7) Spawn multiple explore subagents after understanding the big picture.
- **Three-layer context compaction**:
  - *Layer 1 — Micro-compact* (every turn, zero LLM cost): replaces old tool_result content (>100 chars, except last 3) with `[Previous: used {tool_name}]`
  - *Layer 2 — Auto-compact with transcript preservation*: when input_tokens > `compact_threshold x context_window`, saves full history to `workspace/.transcripts/transcript_{timestamp}.jsonl` before LLM summarization (keeps last 8 messages intact). Falls back to hard truncation on failure.
  - *Layer 3 — Manual compact tool*: agent calls `compact` tool to trigger compaction on demand. Returns sentinel `__COMPACT_REQUESTED__` detected by the loop.
- Tools are async functions registered in `ToolRegistry`
- **Parallel subagents** (task tool): re-enter the loop with isolated context, max depth 2. Subagent types: `general`, `explore`, `code`, `plan`, `research`. Each type has a curated tool set, focused prompt, and type-specific parallel tool guidance (read-only hint for explore/plan, full rules for general/code, write-aware hint for research). Subagents share the parent's remaining token budget (not the full `max_token_budget`) to prevent overspending. The LLM can call multiple `task` tools in a single response to spawn subagents in parallel — they execute concurrently via `asyncio.gather()`. Each subagent emits `subagent_start`/`subagent_end` events with a unique `subagent_id` (UUID hex) and `agent_type` for UI correlation. Developer UI shows parallel blocks with colored type badges (explore=blue, code=green, plan=purple, research=orange). User UI shows "Working on N tasks..." activity indicator. CLI shows "Researching (N subagents)" spinner.
- **Persistent task system**: `agent/task_manager.py` stores tasks as `workspace/.tasks/task_{id}.json`. Each task has: id, subject, description, status, blockedBy/blocks arrays, owner, activeForm, metadata. Dependency cascade on completion (removes completed ID from all blockedBy lists) using an in-memory reverse dependency map (`_reverse_deps: dict[int, set[int]]`) for O(k) lookups instead of O(n) file scans. Bidirectional linking (addBlocks auto-adds to target's blockedBy). Uses `asyncio.Lock` + `asyncio.to_thread()` for concurrent-safe file I/O. Legacy `todo_*` tools kept alongside for backward compat.
- **Background task execution**: `agent/background_manager.py` runs commands via `asyncio.create_task()` + `asyncio.create_subprocess_shell()`. Notification queue (list + asyncio.Lock) collects results. Drained at top of each turn in the agent loop and injected as synthetic message pairs before the LLM call. Tools: `background_run(command)` returns task_id immediately, `check_background(task_id?)` checks status.
- **Per-conversation feature flags**: `enable_teams`, `enable_tracing`, `enable_approval`, and `enable_plan_mode` booleans stored in the `conversations` table (default false). Set at creation time via `POST /api/chat` body. `websocket.py` reads these flags and conditionally creates team infrastructure (MessageBus, ProtocolTracker, TeammateManager), tracing wrapper (TracingLLMClient), tool approval queue (`asyncio.Queue`), and plan mode state. All flags (except tracing) are toggleable mid-conversation via WebSocket control messages (`toggle_teams`, `toggle_approval`, `toggle_plan_mode`) — the handler updates local state + persists to DB + sends a confirmation event. DB migrated via `_migrate_add_column()`.
- **Tool approval system** (opt-in via `enable_approval`): Pauses the agent loop before executing "dangerous" tools and waits for user approval via WebSocket. Read-only tools (`SAFE_TOOLS` frozenset in `loop.py`: think, read_file, read_file_range, search_code, list_symbols, find_references, list_skills, read_skill, todo_list, task_list, task_get, check_background, read_inbox, list_teammates, check_protocol, compact, enter_plan_mode, exit_plan_mode) auto-execute without prompting. Unsafe tools trigger a `tool_approval_request` WebSocket event; the loop blocks on an `asyncio.Queue` until the client sends a `tool_approval_response` with one of three decisions: `approve` (execute normally), `deny` (return "User denied this tool call" as tool_result so the LLM can adjust), or `auto_approve` (set `approval_queue = None` to disable approval for the rest of the session). 5-minute timeout prevents hanging on disconnect. Subagents do not receive the approval queue — once the `task` tool is approved, subagents run autonomously.
- **Plan mode** (opt-in via `enable_plan_mode` or agent-initiated): Claude Code-style read-only exploration phase. When active, the agent is restricted to `PLAN_MODE_TOOLS` (frozenset in `loop.py`: think, read_file, read_file_range, search_code, list_symbols, find_references, list_skills, read_skill, todo_list, task_list, task_get, check_background, read_inbox, list_teammates, check_protocol, compact, task_create, task_update, exit_plan_mode) — all write tools (bash, write_file, edit_file, etc.) are excluded via `registry.get_definitions(exclude=...)`. A `PLAN_MODE_PROMPT` is appended to the system prompt instructing the agent to explore and produce a structured plan. When the agent calls `exit_plan_mode(plan=...)`, the loop extracts the plan text from the tool call's `plan` parameter (falling back to `_extract_plan_text()` from assistant messages if the parameter is empty) and emits a `plan_ready` WebSocket event. The plan is shown to the user for approval. Three outcomes: (1) **Approve** — `plan_mode_active` set to false, DB updated, "Plan approved. Now execute the plan above step by step." injected as user message, agent loop runs with full tool access; (2) **Reject with feedback** — feedback injected as user message ("Plan rejected. Feedback: ..."), agent revises the plan in plan mode; (3) **Reject without feedback** — no action, user can send new message. Activatable four ways: conversation-level flag at creation, `/plan` and `/execute` slash commands in CLI, header toggle button in UI, or **agent-initiated** via `enter_plan_mode` tool. Mid-conversation toggle sends `toggle_plan_mode` WebSocket message which updates mutable state + DB.
- **Agent-initiated plan mode**: The agent can autonomously enter plan mode by calling `enter_plan_mode` tool (sentinel pattern, like compact). `agent/tools/plan_mode_tool.py` defines two tools: `enter_plan_mode` (no params, returns `ENTER_PLAN_SENTINEL`) and `exit_plan_mode` (required `plan` param for the full plan text in markdown, returns `EXIT_PLAN_SENTINEL`). The loop detects sentinels after tool execution and switches mid-loop: `_plan_mode` mutable local + `_plan_start_idx` tracks message index when plan mode began + `_get_tool_defs()`/`_get_system()` helpers recompute tools and system prompt. Tool visibility: `enter_plan_mode` excluded when already in plan mode, `exit_plan_mode` excluded when not in plan mode. When `exit_plan_mode` is called, the loop reads the plan from `tc.input["plan"]` (falling back to `_extract_plan_text(messages, _plan_start_idx)` from assistant messages), emits `plan_ready`, and breaks. Both tools are in `SAFE_TOOLS` (auto-approve). `agent_loop()` returns `plan_mode: bool` in its result dict; callers (`websocket.py`, `app.py`) sync their `plan_mode_active` state from this.
- **Agent teams with async mailbox** (opt-in via `enable_teams`): `agent/message_bus.py` provides per-agent `asyncio.Queue` with optional JSONL persistence (`workspace/.team/inbox/`). `agent/teammate_manager.py` spawns named teammates as `asyncio.Task` instances, each running a simplified agent loop. Teammates get: bash, file tools, think, send_message, read_inbox, idle (but NOT spawn_teammate). Lead's loop drains its inbox before each LLM call. 5 lead tools: `spawn_teammate`, `list_teammates`, `send_message`, `read_inbox`, `broadcast`. Team tools only registered when `enable_teams` is true for the conversation.
- **Team protocols**: `agent/protocol_tracker.py` provides request_id correlation for structured request-response patterns. Shutdown protocol: lead sends request → teammate responds → teammate exits on approval. Plan approval: teammate submits plan → lead reviews → teammate receives decision. Tools: `shutdown_request`, `check_protocol`, `plan_review`.
- **Autonomous agent behavior**: Teammates use a WORK/IDLE state machine. WORK: standard agent loop with inbox drain; exits on `idle` tool or max turns. IDLE: event-driven via `asyncio.Event` from `MessageBus.notify_event()` — wakes instantly on incoming messages, with 5s timeout fallback for task board scanning and 60s total IDLE timeout → auto-shutdown. Auto-claims tasks from the board. Identity re-injection after context compaction (`len(messages) <= 3`).
- **Cancellation & Interrupt**: an `asyncio.Event` (`cancelled`) is created per WebSocket session. It is set when the client disconnects, sends `{"type": "cancel"}`, or sends `{"type": "interrupt", "content": "..."}`. The agent loop checks it before each LLM call and before tool execution; subagents also respect it. After cancellation the WebSocket handler checks the `interrupt_queue` — if an interrupt message is found, it sends an `interrupted` event, sets `pending_content`, and continues the main loop (starting a new agent turn with the interrupt content as the user message). If no interrupt, it breaks cleanly. In the CLI, Ctrl+C sets `cancelled` and shows a feedback prompt; user-typed feedback is sanitized (orphaned `tool_use` blocks stripped) and re-injected as the next user message.
- **Think tool**: `agent/tools/thinking_tool.py` — a no-op tool that gives the agent a dedicated space for complex reasoning between tool calls. Does not obtain new information or cause side effects; the thought is simply appended to the conversation log. Useful for analyzing tool outputs, multi-step planning, policy compliance, and **self-verification** (checking work before finishing). Available everywhere: main loop (always registered), all subagent types (explore, plan, research via curated list; code via `"*"`), and teammates (registered in `_build_teammate_registry`). See [Anthropic engineering blog](https://www.anthropic.com/engineering/claude-think-tool).
- **Loop completion guarantees**: Three mechanisms ensure the agent always produces a final response. (1) *Truncation auto-continuation*: when the model hits `max_output_tokens` mid-generation (`stop_reason=max_tokens`), the loop detects this via `LLMResponse.stop_reason` and injects a continuation prompt — up to `MAX_CONTINUATIONS=3` times. This prevents the model from writing code but stopping before executing it. (2) *Wrap-up nudge*: `WRAPUP_TURNS_REMAINING=3` turns before `max_turns`, the system prompt is augmented with `WRAPUP_HINT` telling the model to finish up. (3) *Forced final summary*: if the for-loop exhausts all turns (Python `for...else`), one final no-tools LLM call is made with `FINAL_SUMMARY_PROMPT` to produce a text summary.
- **Self-verification via think tool**: Instead of separate verify/summary phases, the agent is instructed (via system prompt) to use the `think` tool to verify its work before finishing. The agent decides when to verify, what to check, and whether to fix issues — all within the normal tool loop. The loop simply exits when the agent responds with no tool calls.
- Skills inject knowledge via tool_result (cache-preserving)
- **Agent loop return value**: `agent_loop()` returns `{"input_tokens": int, "output_tokens": int, "last_input_tokens": int, "plan_mode": bool}`. The `last_input_tokens` field is the input tokens from the final LLM call in the turn — used by the CLI to compute context window percentage. The `plan_mode` field reflects whether plan mode is active at loop exit (may differ from input if agent called `enter_plan_mode`).
- WebSocket streams JSON events: text_delta, tool_call, tool_result, tool_approval_request, tool_approval_result, subagent_start (includes `subagent_id`, `task`, `agent_type`), subagent_end (includes `subagent_id`, `summary`, `tool_count`, `elapsed`, `agent_type`, `usage`), todo_update, task_update, compact, background_result, teammate_status, plan_mode_changed, teams_changed, approval_changed, plan_ready, plan_approved, plan_rejected, llm_request, llm_response (when tracing enabled), interrupted (includes `usage` + `files`), done (includes `files` array), error. Client→server control messages: `toggle_plan_mode` (enabled: bool), `toggle_teams` (enabled: bool), `toggle_approval` (enabled: bool), `plan_approval` (decision: "approve"|"reject", feedback?: string), `interrupt` (content: string — mid-stream feedback that cancels current turn and starts a new one with the content as user message), `cancel` (stops current turn without feedback)
- Only `main.py` imports `anthropic` SDK — everything else uses the `LLMClient` protocol
- **Session memory**: `agent/memory.py` provides cross-session continuity. On WebSocket disconnect, an LLM analyzes the full conversation and merges extracted facts/preferences/decisions into `workspace/.agent/memory.md` (fire-and-forget via `asyncio.create_task`). On session start, memory is read and injected into the system prompt. Sections: User Preferences, Project Context, Decisions, Corrections. Max 4KB, toggle with `ENABLE_MEMORY=false`. The memory analyzer is instructed to never persist the agent's role/persona (that's determined by the preset, not memory) to prevent cross-preset contamination.
- **Workspace directories**: `.agent/` (memory), `.transcripts/` (compaction audit trail), `.tasks/` (persistent tasks), `.team/` (team config + inbox). All excluded from workspace file listing and cleanup.
- **WebSocket import**: `api/websocket.py` imports `database` as a module (not the factory directly) so the session factory is resolved at call time after `init_db()` runs
- **No assert for config validation**: `websocket.py` uses `if not ...: raise RuntimeError(...)` instead of `assert` so the check is not stripped by `python -O`
- **Prompt presets**: System prompts are decoupled from the loop into loadable `prompts/*/PROMPT.md` files. `PromptLoader` (mirrors `SkillLoader`) reads them at startup. `build_system_prompt()` loads the preset body, substitutes `{workspace}`, and appends dynamic sections (memory, skills, subagents). Each conversation stores its preset; null defaults to `config.default_preset` ("coding"). `GET /api/presets` lists available presets. Frontend shows a preset selector modal on new chat creation.
- **File downloads + deferred cleanup**: When the agent loop completes, `websocket.py` scans the workspace (skipping `.agent/`, `.transcripts/`, `.tasks/`, `.team/`) and includes a `files` array (`[{name, path, size}]`) in the `"done"` WebSocket event. `GET /api/files/{conv_id}/{file_path:path}` serves workspace files via `FileResponse` with path-traversal and `.agent/` access guards. Workspace cleanup is deferred by `WORKSPACE_CLEANUP_DELAY` seconds (default 300) via `asyncio.create_task`, giving users time to download files before they're removed. The frontend renders a "Files created" card with download links for each file.
- **Workspace file browsing & upload**: `GET /api/workspace/files` lists all workspace files (same skip logic as `_list_workspace_files` in websocket.py). `GET /api/workspace/file/{path}` reads file content for preview with language detection from extension (30+ mappings), binary detection (MIME type, known binary extensions, null-byte scan), and 100 KB truncation. `POST /api/workspace/upload` accepts `multipart/form-data` with multiple files and optional `subdir` query param; enforces 10 MB per-file limit, reuses path-traversal and `_SKIP_DIRS` security guards, creates subdirectories as needed, returns `{"uploaded": ["path1", ...]}`. Same path-traversal and hidden-dir security guards as the file download endpoint. The frontend `filepanel.js` module provides a right-side panel (420px flex child of `#app`) with file list, click-to-preview (syntax highlighting via highlight.js, markdown rendering via marked.js), and file upload (button + drag-and-drop). Auto-refreshes on `done` events.
- **DB migrations**: `database.py` includes `_migrate_add_column()` for safe `ALTER TABLE` on existing SQLite databases (checks `PRAGMA table_info` before adding columns)
- **MCP (Model Context Protocol) support** (opt-in via `mcp_servers.json`): Integrates external tools from MCP-compatible servers. Two complementary modes configured in a single `mcp_servers.json` file (no file or empty `servers` = no MCP, zero impact on existing functionality):
  - *Client-mode*: `agent/mcp_manager.py` connects to MCP servers via the `mcp` SDK (`stdio_client` for local processes, `streamablehttp_client` for HTTP). Tools are namespaced as `mcp__{server}__{tool}` and injected into `ToolRegistry` — works with any LLM provider. Long-lived connections: connect at startup in `main.py` lifespan, disconnect on shutdown.
  - *Remote-mode*: Server params passed to Anthropic's beta API (`beta.messages.create/stream` with `mcp_servers` + `betas=["mcp-client-2025-04-04"]`). `AnthropicAdapter._mcp_servers` attribute set via `_attach_mcp_remote()` helper in `loop.py` which walks the wrapper chain (`_inner`) to find the adapter. `mcp_tool_use`/`mcp_tool_result` blocks in responses are added to `content` but NOT to `tool_calls` (server-side execution). Other providers silently skip remote MCP.
  - *Config format*: `mcp_servers.json` at `MCP_SERVERS_FILE` path (default: `mcp_servers.json`). Supports `${VAR}` env variable substitution in all string values. Each server entry: `transport` ("stdio"|"http"), `mode` ("client"|"remote"), plus transport-specific fields (`command`/`args`/`env` for stdio; `url`/`authorization_token`/`headers` for http).
  - *Integration points*: `MCPManager` follows the `SkillLoader` pattern (standalone class, created at startup, injected). `build_registry()` accepts `mcp_manager` param → calls `mcp_manager.register_tools(registry)`. `build_system_prompt()` accepts `mcp_tool_descriptions` param → appends MCP tool listing. `agent_loop()` accepts `mcp_manager` → passes to both. `websocket.configure()` accepts `mcp_manager` → stored as module global, passed to `agent_loop()`. `main.py` lifespan: `MCPManager.from_config_file()` → `connect_all()` → `websocket.configure(…, mcp_manager)` → tool info extended for `GET /api/tools` → `disconnect_all()` on shutdown.
- **Planned tool-discovery architecture**: Current behavior still passes the full bound tool list to the provider each turn (`agent_loop()` computes `tool_defs` and sends them through `llm.stream(..., tools=tool_defs, ...)`). The intended evolution is a retrieval-then-bind model rather than shipping the entire catalog every turn.
  - *Core idea*: keep native provider tool-calling, but shrink the provider-facing tool list to a small working set. The registry still contains every handler; only the `tools=` payload becomes selective.
  - *Conversation state*: maintain four conceptual buckets per conversation:
    - `bootstrap_tool_names` — always-bound universal tools
    - `discovery_tool_names` — always-bound catalog-management tools
    - `active_tool_names` — currently bound executable tools chosen for this task
    - `tool_catalog` — searchable metadata for every registered built-in and MCP tool
    - optional `recent_tool_usage` — ranking and eviction signal
  - *Bootstrap tools*: always available because they are universal primitives or coordination tools. Recommended baseline: `think`, `read_file`, `search_code`, `bash`, `task`, and `compact`.
  - *Discovery tools*: also always available. Planned examples: `search_tools`, `describe_tool`, `activate_tools`, `deactivate_tools`.
  - *Active tools*: a small dynamic subset selected by the model after discovery. The loop would pass `bootstrap + discovery + active_tools` instead of the whole registry.
  - *Turn flow*:
    1. Start with bootstrap + discovery tools only.
    2. Let the model inspect the repo with always-on primitives such as `read_file`, `search_code`, and `bash`.
    3. When a specialized capability is needed, let the model call `search_tools(query=...)`.
    4. If more detail is needed, let it call `describe_tool(name=...)`.
    5. Let it call `activate_tools(names=[...])`.
    6. On the next provider call, pass only `bootstrap + discovery + active_tools`.
    7. Real execution still happens via normal tool calls and the existing `registry.execute(...)` path.
    8. Optionally evict inactive tools after N turns, cap the active set size, or support explicit `deactivate_tools(names=[...])`.
  - *Why these bootstrap choices*:
    - `read_file` stays bootstrap because it is the most common grounding primitive and is often useful before any catalog search.
    - `bash` stays bootstrap because shell inspection and verification are common (`ls`, `rg`, `git status`, tests). Safety still comes from the approval gate, not from hiding the tool.
    - `task` stays bootstrap for the lead agent because it is a control-plane primitive. The model may need delegation before it knows which concrete long-tail tools matter.
  - *Subagent rule*: subagents should inherit a smaller bootstrap set and should continue to exclude `task` (`include_task=False`) to prevent recursive delegation spirals.
  - *Search/ranking expectations*: `search_tools` can start with simple lexical scoring over tool name, description, tags, MCP server name, and input-schema field names. Semantic retrieval can be deferred until the catalog becomes large enough to justify it.
  - *Implementation boundary*: `activate_tools` should update per-conversation state, not mutate the global registry. `ToolRegistry` remains the execution source of truth; only the provider-facing `tool_defs` list becomes selective.
  - *Why not a generic executor*: avoid replacing native tools with a single `execute_tool(name, args)` tool. That would hide per-tool schemas from the model, weaken structured argument generation, reduce provider-side validation, collapse approval UX into one opaque tool, and make parallel execution less natural. Discovery should narrow exposure to real tools, not replace real tools.
- **Planned skill-retrieval architecture**: The current skill flow scales poorly once the catalog gets large. Today `build_system_prompt()` embeds a flat list of all skill descriptions, `list_skills` returns a text dump, and `read_skill` injects one full `SKILL.md` body into the transcript. That works for a small catalog but degrades with 50+ installed skills.
  - *Core idea*: move from `list -> read full body` to `retrieve -> summarize -> pin`. The model should search a ranked skill catalog, load one or more relevant skills, and keep compact reusable summaries active across turns.
  - *Conversation state*:
    - `skill_catalog` — all parsed skills with structured metadata
    - `active_skills` — pinned skills currently in effect for the conversation
    - `recent_skill_usage` — reuse/ranking signal
    - `skill_summary_cache` — compact summaries for already loaded skills
    - optional `skill_groups` — complementary bundles of related skills
  - *Recommended always-on skill tools*:
    - `search_skills(query, limit?, tags?, include_related?, include_bundles?)`
    - `describe_skill(skill, detail?)`
    - `load_skills(skills[])`
    - `pin_skills(skills[])`
    - `unpin_skills(skills[])`
    - `list_active_skills()`
  - *Prompt strategy*: stop embedding the full flat skill catalog in the main system prompt. Replace it with a short instruction that skills are available and should be searched and loaded when relevant.
  - *Retrieval flow*:
    1. Model calls `search_skills(query=...)`.
    2. Tool returns ranked candidates with name, short description, why it matched, tags/domains, estimated token cost, and related skills.
    3. Model optionally calls `describe_skill(...)` for a richer summary.
    4. Model calls `load_skills(["skill-a", "skill-b"])` when one or more skills are needed.
    5. Loaded skills are converted into compact normalized summaries and pinned for later turns.
  - *Multi-skill support*: this should be a first-class feature, not an edge case. Retrieval should be able to suggest complementary skills or bundles, for example a primary skill plus one or two related skills that are commonly useful together.
  - *Metadata expectations*: the current `name + description` model is not enough for good retrieval. Recommended frontmatter additions include `tags`, `domains`, `triggers`, `when_to_use`, `when_not_to_use`, `related_skills`, `examples`, `summary`, and `token_budget`.
  - *Ranking expectations*: start with lexical scoring over name, description, tags, triggers, and related-skill overlap. Then rerank using workspace/task signals such as repo contents, recent tool usage, and prior successful skill usage in the same conversation.
  - *Layered loading*: avoid injecting full skill bodies into rolling context by default.
    - Layer 1: search result
    - Layer 2: summarized description with workflow/resources
    - Layer 3: full raw `SKILL.md` body only when explicitly needed
  - *Pinned summary format*: each active skill summary should preserve the skill name, one-sentence purpose, key workflow steps, available scripts/resources, and important caveats.
  - *Compaction rule*: when the transcript is compacted, preserve active skill summaries and the rationale for loading them, but drop raw skill bodies unless they remain central to the task.

## Testing

```bash
# Agent API tests (245 tests, ~2s)
cd agent-api && .venv/bin/python -m pytest tests/ -v

# Agent CLI tests (172 tests, <1s)
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# Lint + type check
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-api && .venv/bin/mypy src/

# Pre-commit (runs ruff, mypy, pytest for both packages)
pre-commit run --all-files
```

### Agent API test suite (`agent-api/tests/`)

- `conftest.py` — shared fixtures: `workspace` (tmp_path), `MockLLMClient` (single fixed response), `mock_llm`
- `test_integration.py` — agent loop integration (48 tests): `ScriptedLLMClient` (multi-response scripted LLM), `EventCollector`, helpers `_make_settings`/`_text_response`/`_tool_response`. Covers: text-only QA, tool use (write/read/edit), parallel tools, bash execution, max turns + forced summary, truncation continuation, cancellation, token budget, wrap-up hint, tool approval (approve/deny/auto-approve/safe-tools), context compaction, task manager, subagents, build_registry, build_system_prompt, message sanitization, agent-initiated plan mode (enter/exit sentinels, tool restriction, no-op guards, return value), `_extract_plan_text` helper, compaction failure recovery, cancellation during loop, max_tokens retry exhaustion, subagent max_depth enforcement.
- `test_plan_mode_tool.py` — plan mode tool unit tests (12 tests): sentinel values, definition structure (exit_plan_mode requires `plan` param), handler returns.
- `test_team_integration.py` — team system integration (26 tests): wires real MessageBus, ProtocolTracker, TeammateManager with `ScriptedLLMClient`. Patches `asyncio.wait_for` for instant IDLE phase (event-driven). Covers: bus send/receive/broadcast/JSONL persistence/validation, protocol tracker lifecycle + type filtering, teammate WORK phase (text exit, write_file on disk, duplicate rejection, inbox drain), teammate shutdown (via message, `shutdown_all` cancellation), lead loop with team tools (spawn, send_message, read_inbox, broadcast, tool/protocol registration), end-to-end shutdown protocol, plan approval/rejection roundtrip, IDLE phase (resume on inbox via notify event, auto-claim from task board, timeout→shutdown), identity re-injection on short context.
- `test_mcp_manager.py` — MCP manager unit tests (20 tests): `_substitute_env` (known var, missing var, nested dict, list, passthrough), `MCPManager.from_config_file` (missing file, empty servers, invalid JSON, stdio server, remote server with auth, default mode), `register_tools` (injection, definitions), `_call_mcp_tool` (success, error, empty result, multiple blocks), `get_remote_server_params` (builds params, empty when no remote, skips auth when empty), tool info/names/descriptions.
- `test_api_routes.py` — REST endpoint tests (10 tests)
- `test_bash_tool.py` — bash tool command extraction + safety (18 tests): includes command substitution bypass, backtick injection, arithmetic expansion, env injection, destructive command blocking
- `test_file_tools.py` — file tool path safety + CRUD (18 tests): includes symlink escape, intermediate symlink, `../` traversal, null byte injection, dotdot-in-middle, read/write traversal blocking
- `test_code_nav_tools.py` — code navigation tools (8 tests): range reads, text/regex search, symbol extraction, reference search, binary-file skipping
- `test_websocket.py` — WebSocket handler tests (11 tests): `TestSanitizeMessages` (message sanitization), `TestListWorkspaceFiles` (file listing), `TestConnectionLifecycle` (connect/disconnect/error handling)
- `test_llm.py` — LLM abstraction: response parsing, retry, tracing (11 tests)
- `test_memory.py` — memory manager: read/write/compact/cleanup (9 tests)
- `test_message_bus.py` — MessageBus unit tests (7 tests)
- `test_micro_compact.py` — micro-compaction logic (4 tests)
- `test_schemas.py` — Pydantic schema validation (7 tests)
- `test_task_manager.py` — task CRUD, dependencies, claim, render (14 tests)
- `test_tool_registry.py` — ToolRegistry register/execute/definitions (7 tests)

### Agent CLI test suite (`agent-cli/tests/`)

- `test_main.py` — argument parser (28 tests): default values, long/short flags, combined flags, `--resume`, `--version`
- `test_renderer.py` — event renderer (50 tests): `_summarize_input`, `_result_lines`, `_end_stream`, `StreamingRenderer` (plain text, code block detection, reset, finish flush), `make_send_event` (text_delta, tool_call, tool_result, error, done with/without cost tracker, compact, subagent, tool approval, teammate, thinking spinner, teams_changed, approval_changed, stream ending)
- `test_approval.py` — approval handler (12 tests): decisions (y/n/a/unknown), tool name extraction, queue handling
- `test_config.py` — CLI config (13 tests): defaults, TOML loading (full/partial/missing), agent_dir override, ensure_dirs
- `test_cost.py` — cost tracking (15 tests): init, accumulation, cost per model (Opus/Sonnet/Haiku/unknown), cost_for, format_usage_line (with/without context %), pricing table
- `test_session.py` — session persistence (16 tests): create, messages (save/load/empty/nonexistent/count), usage, listing (empty/order/limit/latest), get session, title update/truncation
- `test_commands.py` — slash commands (26 tests): dispatch (non-command/unknown/help/quit/exit/clear/compact/cost/model/plan/execute), command registry, history, resume (no sessions/with ID/nonexistent), teams (on/off/no-args/invalid), approval (on/off/no-args/invalid)

## Security Hardening

- **Command injection**: `bash_tool.py` blocks dangerous patterns including `$(...)` command substitution, backtick expansion, `$((...))` arithmetic, and environment variable injection
- **Path traversal**: `file_tools.py` `_safe_path()` validates every intermediate path component for symlinks escaping workspace, rejects null bytes, and resolves all paths before access
- **XSS prevention**: All markdown rendering (marked.js) in the frontend is sanitized through DOMPurify before DOM insertion (`markdown.js`, `filepanel.js`, `app.js`)
- **Secret redaction**: `TracingLLMClient` runs all emitted payloads through `_redact_sensitive()` which masks API keys, Bearer tokens, and long base64 strings
- **No assert for validation**: Production config checks use `if not ...: raise RuntimeError(...)` instead of `assert` (not stripped by `python -O`)

## DevOps

- **CI/CD**: `.github/workflows/ci.yml` — test matrix (Python 3.11/3.12/3.13), lint (ruff), type check (mypy), dependency vulnerability scanning
- **Pre-commit**: `.pre-commit-config.yaml` — ruff check + format, mypy, pytest hooks for both packages
- **Linting**: `[tool.ruff]` config in both `pyproject.toml` files (line-length 120, Python 3.11 target)
- **Type checking**: `[tool.mypy]` config in both `pyproject.toml` files (warn_return_any, warn_unused_configs)
- **Dependency pinning**: All dependencies in both packages have upper bounds (e.g., `fastapi>=0.115,<1.0`)
- **Project files**: `CONTRIBUTING.md` (branch naming, commit format, PR checklist), `LICENSE` (Business Source License 1.1), `.env.example` (all env vars documented)

### Manual smoke tests

```bash
# API endpoints
curl --noproxy localhost http://localhost:8000/health
curl --noproxy localhost http://localhost:8000/api/tools
curl --noproxy localhost http://localhost:8000/api/skills
curl --noproxy localhost http://localhost:8000/api/presets
curl --noproxy localhost http://localhost:8000/api/workspace/files
curl --noproxy localhost http://localhost:8000/api/workspace/file/hello.py
# Upload files to workspace
curl --noproxy localhost -X POST http://localhost:8000/api/workspace/upload -F 'files=@myfile.txt'
curl --noproxy localhost -X POST 'http://localhost:8000/api/workspace/upload?subdir=data' -F 'files=@data.csv'
# File download (after agent creates files in workspace)
curl --noproxy localhost -O http://localhost:8000/api/files/{conv_id}/filename.pdf

# MCP smoke test (create mcp_servers.json with a real server, then start)
# Should log MCP connection and include mcp__filesystem__* in /api/tools
cat > mcp_servers.json << 'MCPEOF'
{"servers":{"filesystem":{"transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"],"mode":"client"}}}
MCPEOF
.venv/bin/uvicorn agent_service.main:app --reload
curl --noproxy localhost http://localhost:8000/api/tools

# CLI
cd agent-cli
.venv/bin/openagent --version
echo "hello" | .venv/bin/openagent --no-approval   # pipe mode
.venv/bin/openagent                                  # interactive REPL
.venv/bin/openagent --plan                           # start in plan mode
.venv/bin/openagent --resume                         # resume latest session
```
