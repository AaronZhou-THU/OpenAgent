# Remote Control: CLI <-> UI via agent-api

## Context

Currently, `agent-cli` calls `agent_loop()` directly (in-process), while `agent-ui` connects to `agent-api`'s WebSocket. They are completely independent — no shared sessions, no cross-visibility.

**Goal**: Add a `--remote` mode to `agent-cli` so it connects to `agent-api` via WebSocket, sharing the same conversations with `agent-ui`. Both clients see each other's messages and streaming events in real-time.

```
agent-ui  ──WS──►  agent-api  ◄──WS──  agent-cli --remote
                       │
                  agent_service
                  (agent_loop)
```

The standalone local mode (default) remains unchanged.

---

## Architecture

### Current State

```
┌──────────┐                           ┌──────────┐
│ agent-ui │ ──WS/HTTP──► agent-api ──►│agent_loop│
└──────────┘              (port 8000)  └──────────┘

┌───────────┐
│ agent-cli │ ──direct import──► agent_loop (in-process)
└───────────┘
```

- **agent-ui** connects to `agent-api` via REST + WebSocket (`ws://localhost:8000/api/chat/{conv_id}/ws`)
- **agent-cli** imports and calls `agent_loop()` directly from `agent_service` — no network, no shared state
- Sessions are completely separate: UI uses SQLite DB, CLI uses local JSONL files

### Target State

```
┌──────────┐                           ┌──────────┐
│ agent-ui │ ──WS──►                ──►│          │
└──────────┘        │  agent-api  │    │agent_loop│
┌───────────┐       │  (port 8000)│    │          │
│ agent-cli │ ──WS──►  broadcast  ──►  └──────────┘
│ --remote  │
└───────────┘
```

- Both clients connect to the same WebSocket endpoint
- Events are **broadcast** to all connected clients for a conversation
- One client sends a message → all clients see the streaming response
- Either client can start a new turn (serialized by per-conversation lock)

### Design Principles

1. **Same brain, many mouths** (claw0 s04 pattern) — the agent loop runs once; multiple channels observe
2. **Turn ownership** — the client that sends a message owns the turn (cancel/approve). Others are observers
3. **Standalone preserved** — `openagent` (no flags) works exactly as before, no `agent-api` needed
4. **Renderer reuse** — the CLI terminal renderer (`make_send_event`) processes event dicts regardless of source

---

## Usage

### Start the API server

```bash
cd agent-api && .venv/bin/uvicorn agent_service.main:app --reload
```

### CLI in remote mode (new conversation)

```bash
cd agent-cli && .venv/bin/openagent --remote
# Creates a new conversation, connects via WebSocket
# Type messages, see streaming responses in the terminal
```

### CLI in remote mode (join existing conversation)

```bash
# Get the conversation ID from agent-ui or a previous session
openagent --remote -c <conversation_id>
# Joins the conversation — sees all future events
```

### CLI with custom server

```bash
openagent --remote --server http://192.168.1.100:8000
```

### Open agent-ui in browser

```
http://localhost:3500
# Select the same conversation from the sidebar
# See all messages (including ones sent from CLI)
# Send a message from UI → CLI sees the streaming events
```

### Multiple CLI observers

```bash
# Terminal 2: another CLI instance, same conversation
openagent --remote -c <conv_id>
# Sees all events broadcast to it
# Can send messages when the other client is idle
```

### Pipe mode (non-interactive)

```bash
echo "Explain recursion" | openagent --remote --no-approval
# Creates conversation, sends message, waits for response, exits
```

---

## Protocol

Remote mode uses the existing WebSocket event protocol defined in `agent-api/websocket.py`.

### Client → Server

| Message Type | Fields | Description |
|---|---|---|
| `message` | `content: str` | Send a user message |
| `cancel` | — | Cancel the current agent turn |
| `tool_approval_response` | `decision: "approve"\|"deny"\|"auto_approve"` | Respond to tool approval request |
| `plan_approval` | `decision: "approve"\|"reject"`, `feedback?: str` | Approve or reject a plan |
| `toggle_plan_mode` | `enabled: bool` | Toggle plan mode |
| `toggle_teams` | `enabled: bool` | Toggle team mode |
| `toggle_approval` | `enabled: bool` | Toggle tool approval |

### Server → Client (broadcast to all)

| Event Type | Key Fields | Description |
|---|---|---|
| `thinking` | — | Agent is processing |
| `text_delta` | `content` | Streaming text chunk |
| `tool_call` | `tool`, `input` | Agent calling a tool |
| `tool_result` | `result` | Tool execution output |
| `tool_approval_request` | `tools` | Approval needed for tool |
| `subagent_start/end` | `name`, `role` | Subagent lifecycle |
| `plan_ready` | — | Plan awaiting review |
| `plan_approved/rejected` | `feedback?` | Plan decision |
| `plan_mode_changed` | `enabled` | Plan mode toggled |
| `teams_changed` | `enabled` | Teams toggled |
| `approval_changed` | `enabled` | Approval toggled |
| `todo_update` | `todos` | Task list change |
| `task_update` | `task` | Task status change |
| `compact` | — | Context compaction occurred |
| `done` | `usage`, `files` | Turn complete |
| `error` | `message` | Error occurred |

---

## Implementation Plan

### Step 1: Server-side broadcast

**File**: `agent-api/src/agent_service/api/websocket.py`

Add multi-client broadcasting:

- Add `_connections: dict[str, set[WebSocket]]` at module level (alongside existing `_todo_managers`)
- Add `async _broadcast(conv_id, event)` helper — sends to all connections, silently removes dead ones
- In `chat_ws`: register connection on `accept()`, unregister in `finally` block
- Replace `send_event` closure to use `_broadcast()` instead of single `await ws.send_json(event)`
- Keep existing turn ownership: only the message-sending client can cancel/approve

### Step 2: Add dependencies to agent-cli

**File**: `agent-cli/pyproject.toml`

- `websockets>=14.0,<15.0` — async WebSocket client
- `httpx>=0.27,<1.0` — async HTTP client for REST API calls

### Step 3: WebSocket client module

**New file**: `agent-cli/src/agent_cli/ws_client.py`

`RemoteClient` class:
- Connects to `ws://{server}/api/chat/{conv_id}/ws`
- Background task receives JSON events, forwards to `on_event` callback (the terminal renderer)
- Methods: `send_message()`, `send_cancel()`, `send_control()`, `wait_for_done()`, `disconnect()`
- `asyncio.Event` for done-signal coordination

`RemoteApprovalHandler` class:
- Interactive terminal prompt on `tool_approval_request` events (same UX as local)
- Sends `tool_approval_response` back over WebSocket

### Step 4: CLI flags

**File**: `agent-cli/src/agent_cli/main.py`

New arguments:
- `--remote` — enable remote mode
- `--server URL` — agent-api URL (default: `http://localhost:8000`)
- `--conversation / -c ID` — join existing conversation (creates new if omitted)

Dispatch to `run_remote_repl(args)` when `--remote` is set.

### Step 5: Make commands remote-aware

**File**: `agent-cli/src/agent_cli/commands.py`

- `CommandContext.session_store` accepts `None` (no local sessions in remote mode)
- Guard `/history`, `/resume`, `/clear` for remote mode

### Step 6: Remote REPL

**File**: `agent-cli/src/agent_cli/app.py`

New `run_remote_repl(args)` function:
1. Create conversation via `POST /api/chat` (or join existing via `-c`)
2. Build terminal renderer via existing `make_send_event(remote_approval, cost_tracker)` — **reused as-is**
3. Create `RemoteClient(server_url, conv_id, on_event=send_event)`
4. REPL loop: read input → dispatch remote commands → send message over WS → wait for done
5. Pipe mode: read stdin → send → wait for done → exit
6. Ctrl+C sends cancel over WebSocket

Remote slash commands:
- `/plan`, `/teams on|off`, `/approval on|off` → WebSocket toggle messages
- `/help`, `/cost`, `/quit` → work locally
- `/history`, `/resume`, `/clear`, `/compact` → "not available in remote mode"

### Step 7: Tests

- `agent-api/tests/test_websocket.py` — `TestBroadcast` (send to all, dead cleanup, empty set)
- `agent-cli/tests/test_ws_client.py` — `RemoteClient` (connect, send, receive, done, disconnect)
- `agent-cli/tests/test_main.py` — new CLI flags

---

## Files Modified/Created

| File | Action |
|------|--------|
| `agent-api/src/agent_service/api/websocket.py` | Modify — add broadcast |
| `agent-cli/pyproject.toml` | Modify — add websockets, httpx |
| `agent-cli/src/agent_cli/ws_client.py` | **Create** — RemoteClient + RemoteApprovalHandler |
| `agent-cli/src/agent_cli/app.py` | Modify — add `run_remote_repl()` |
| `agent-cli/src/agent_cli/main.py` | Modify — add `--remote`, `--server`, `-c` flags |
| `agent-cli/src/agent_cli/commands.py` | Modify — optional session_store |
| `agent-api/tests/test_websocket.py` | Modify — broadcast tests |
| `agent-cli/tests/test_ws_client.py` | **Create** — client tests |
| `agent-cli/tests/test_main.py` | Modify — flag tests |

---

## Verification

1. **Broadcast**: Open agent-ui in two browser tabs on same conversation → send message in one → both see streaming
2. **CLI remote**: `openagent --remote` → send message → see response → conversation appears in agent-ui sidebar
3. **Cross-channel**: Send from CLI → streams in UI → send from UI → streams in CLI
4. **Standalone**: `openagent` (no `--remote`) → works exactly as before, no agent-api needed
5. **Test suites**: `cd agent-api && .venv/bin/python -m pytest tests/ -v` and `cd agent-cli && .venv/bin/python -m pytest tests/ -v`

---

## Future Enhancements

- **Status on connect**: Send `{"type": "status", "running": true}` when an observer joins mid-turn
- **Multi-client approval**: Any connected client can respond to approval requests (not just turn owner)
- **Session list over REST**: `/history` command uses `GET /api/conversations` in remote mode
- **Auto-reconnect**: CLI WebSocket client with exponential backoff retry (like agent-ui)
- **QR code**: Display a QR code in the terminal for opening the conversation in agent-ui (like Claude Code's `/remote-control`)
