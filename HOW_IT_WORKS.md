# How This AI Coding Agent Works

A beginner-friendly, learn-by-doing guide to understanding every part of this system.

---

## What Is This Project?

This project is designed for beginners who are curious about how agents work. Instead of hiding the system behind a black box, it gives you a real agent you can run, inspect, and modify while you learn.

You type a message like *"Create a Python script that sorts a list of names"*, and the assistant:

1. Thinks about what to do
2. Writes the code using tools (file editor, terminal, etc.)
3. Runs it to verify
4. Reports back with results

All of this happens in **real time** so you can learn by watching the agent think, write code, and use tools live.

```
┌─────────────────────────────────────────────────────────┐
│                    YOU (the browser)                     │
│                                                         │
│   "Create a Python script that sorts names"             │
│                        │                                │
│                        ▼                                │
│              ┌─────────────────┐                        │
│              │   Chat Window   │  ◄── you see live      │
│              │                 │      streaming text     │
│              │  Agent: "I'll   │      and tool results   │
│              │  create a file  │                        │
│              │  called..."     │                        │
│              └─────────────────┘                        │
└─────────────────────────────────────────────────────────┘
                        │
                   (WebSocket)
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                 THE SERVER (backend)                     │
│                                                         │
│     ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│     │  Agent   │───▶│   LLM    │───▶│  Tools   │       │
│     │  Loop    │◀───│   API    │    │ (bash,   │       │
│     │          │    │          │    │  files)  │       │
│     └──────────┘    └──────────┘    └──────────┘       │
└─────────────────────────────────────────────────────────┘
```

---

## The Three Interfaces

This project has three ways to interact with the agent, all talking to the same backend:

```
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│                      │  │                      │  │                      │
│   DEVELOPER UI       │  │   USER UI            │  │   TERMINAL CLI       │
│   (agent-ui/)        │  │   (agent-user-ui/)   │  │   (agent-cli/)       │
│                      │  │                      │  │                      │
│   For developers     │  │   For end users      │  │   For terminal       │
│   Dark theme         │  │   Forest Canopy      │  │   lovers             │
│   Tool blocks        │  │   light theme        │  │                      │
│   Dev panel          │  │   Activity indicators│  │   Rich REPL          │
│   port 3500          │  │   port 3501          │  │   Direct call        │
│                      │  │                      │  │                      │
└──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
           │                         │                          │
           │  WebSocket              │  WebSocket               │  Direct
           └────────────┬────────────┘                          │
                        └──────────────────┬────────────────────┘
                                           ▼
                              ┌──────────────────────┐
                              │                      │
                              │   BACKEND            │
                              │   (agent-api/)       │
                              │                      │
                              │   What THINKS        │
                              │   and ACTS           │
                              │                      │
                              │   Python + FastAPI   │
                              │   + LLM API          │
                              │                      │
                              └──────────────────────┘
```

**Developer UI** (`agent-ui/`) = full-featured chat interface with tool blocks, dev panel, and raw WebSocket inspector — built for developers building and debugging the agent
**User UI** (`agent-user-ui/`) = streamlined chat interface with activity indicators and simplified dialogs — built for end users who just want to use the agent
**Terminal CLI** (`agent-cli/`) = rich REPL with history, autocomplete, and vi mode — for terminal lovers
**Backend** = the brain that receives your messages, talks to the configured LLM provider, runs tools, and sends results back

They communicate in two ways:

| Method | What It Does | Analogy |
|--------|-------------|---------|
| **REST API** (HTTP) | Create conversations, list history, download files | Like sending a letter and getting a reply |
| **WebSocket** | Stream the agent's thinking and actions in real time | Like a phone call — always connected, instant |

---

## The Brain: How the Agent Loop Works

The most important part of the entire system is the **agent loop**. It's surprisingly simple — just a `while` loop:

```
┌─────────────────────────────────────────────────────────────┐
│                    THE AGENT LOOP                           │
│                                                             │
│    START                                                    │
│      │                                                      │
│      ▼                                                      │
│   ┌──────────────────────┐                                  │
│   │  Send messages to    │                                  │
│   │  the LLM            │──── "Here's the conversation      │
│   │                      │      and available tools"        │
│   └──────────┬───────────┘                                  │
│              │                                              │
│              ▼                                              │
│   ┌──────────────────────┐                                  │
│   │  The LLM responds    │                                  │
│   │                      │                                  │
│   │  Either:             │                                  │
│   │  A) Just text ─────── DONE! (agent decided it's          │
│   │  B) Tool requests    │       finished)                   │
│   └──────────┬───────────┘                                  │
│              │ (B)                                           │
│              ▼                                              │
│   ┌──────────────────────┐                                  │
│   │  Execute the tools   │──── Run bash commands,           │
│   │  the LLM asked for   │     read/write files, etc.       │
│   │  (all in parallel!)  │                                  │
│   └──────────┬───────────┘                                  │
│              │                                              │
│              ▼                                              │
│   ┌──────────────────────┐                                  │
│   │  Add tool results    │                                  │
│   │  to the conversation │──── "Here's what happened        │
│   │                      │      when I ran your tools"      │
│   └──────────┬───────────┘                                  │
│              │                                              │
│              └──────── Go back to the top ──────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**In plain English:**

1. Send the full conversation + available tools to the LLM
2. The LLM either gives a final answer (done!) or asks to use tools
3. If tools were requested, run them all at the same time
4. Send the results back to the LLM
5. Repeat until the LLM gives a final answer (or we hit safety limits)

The agent uses the **think tool** to self-verify its work before finishing — reviewing tool results for errors, confirming all parts of the request are addressed, and fixing any issues it finds. No separate verification phase is needed; the agent handles this naturally within the loop.

This is the standard pattern used by tool-calling AI assistants and coding agents.

### A Concrete Example

You say: *"What files are in this directory?"*

```
Turn 1:
  You → LLM:  "What files are in this directory?"
  LLM → You:  I'll check. [uses tool: bash("ls -la")]

  System runs:   bash("ls -la") → "file1.py  file2.py  README.md"

Turn 2:
  You → LLM:  [tool result: "file1.py  file2.py  README.md"]
  LLM → You:  "There are 3 files: file1.py, file2.py, and README.md"
  (no more tool calls → DONE)
```

---

## The Universal Plug: Provider-Agnostic LLM Layer

### The Problem

Today you might use Anthropic. Tomorrow you might want OpenAI, a self-hosted model, or some internal compatible endpoint. We don't want to rewrite the entire agent just to switch.

### The Solution: A Travel Adapter

Think of electrical outlets around the world. Your laptop just needs electricity — it doesn't care whether the outlet is American, European, or British. A **travel adapter** handles the translation.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  WITHOUT adapter (tightly coupled — bad):                   │
│                                                             │
│    Agent Loop ──── directly calls ──── Provider SDK/API     │
│                                                             │
│    (If you switch providers, you rewrite the entire loop)   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  WITH adapter (loosely coupled — good):                     │
│                                                             │
│    Agent Loop ──── calls ──── Universal Interface            │
│                                       │                     │
│                                       ├── ProviderAdapter A │
│                                       ├── ProviderAdapter B │
│                                       └── ProviderAdapter C │
│                                                             │
│    (Switch provider by changing ONE line in main.py)        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### The Three Pieces

**Piece 1: The Contract** — `LLMClient` Protocol

```
"Any LLM client must have these two methods:

  create()  → send messages, get a response (one shot)
  stream()  → send messages, get response piece by piece (live)

I don't care HOW you implement them. Just that they exist."
```

This is like saying "any electrical outlet must provide electricity at a certain voltage." The shape can vary — the adapter handles that.

**Piece 2: The Universal Response** — `LLMResponse`

Every provider returns data differently. This dataclass is the **universal format** that the loop always receives:

```
LLMResponse:
  content      →  what the model said (text blocks, tool requests)
  tool_calls   →  list of tools it wants to use
  done         →  true if the model is finished (no tools requested)
  input_tokens  →  how many tokens we sent
  output_tokens →  how many tokens we received
```

**Piece 3: The Adapter** — a provider adapter such as `AnthropicAdapter` or `OpenAIAdapter`

The actual translator. It does two things:
1. Forward calls to the real provider SDK or API client
2. Convert provider-specific responses into the universal `LLMResponse`

```
┌─────────────┐        ┌───────────────────┐        ┌─────────────┐
│ Agent Loop  │──────▶│ ProviderAdapter    │──────▶│ Provider API │
│             │        │                   │        │             │
│ "I just     │        │ 1. Takes universal │        │ Returns     │
│  need an    │        │    format          │        │ Provider-   │
│  LLMResponse│        │ 2. Calls backend   │        │ specific    │
│  back"      │◀──────│ 3. Converts back   │◀──────│ response    │
│             │        │    to LLMResponse  │        │ object      │
└─────────────┘        └───────────────────┘        └─────────────┘
```

### Where Each Piece Lives

| File | Knows about provider SDK details? | Role |
|------|:-:|------|
| `main.py` | No | Wires the configured provider into the application lifecycle. |
| `llm.py` | Yes (adapter layer only) | Defines the contract, provider adapters, and lazy SDK imports |
| `loop.py` | No | The agent loop. Only sees `LLMClient`. |
| `memory.py` | No | Memory system. Only sees `LLMClient`. |
| `websocket.py` | No | WebSocket handler. Only sees `LLMClient`. |

To add another backend, you'd write a new adapter and change the provider wiring. Nothing else changes.

---

## The Tools: What the Agent Can Do

The agent isn't just a chatbot — it can **take actions**. Tools are the hands of the agent.

```
┌─────────────────────────────────────────────────────────────┐
│                     TOOL REGISTRY                           │
│                                                             │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐             │
│   │   bash    │  │ read_file │  │write_file │             │
│   │           │  │           │  │           │             │
│   │ Run shell │  │ Read any  │  │ Create or │             │
│   │ commands  │  │ file in   │  │ overwrite │             │
│   │ (ls, git, │  │ workspace │  │ files     │             │
│   │  python)  │  │           │  │           │             │
│   └───────────┘  └───────────┘  └───────────┘             │
│                                                             │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐             │
│   │ edit_file │  │  think    │  │   task    │             │
│   │           │  │           │  │           │             │
│   │ Surgical  │  │ Pause and │  │ Spawn a   │             │
│   │ find &    │  │ reason    │  │ sub-agent │             │
│   │ replace   │  │ step-by-  │  │ for       │             │
│   │ in files  │  │ step      │  │ subtasks  │             │
│   └───────────┘  └───────────┘  └───────────┘             │
│                                                             │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐             │
│   │ todo_*    │  │ task_*    │  │ compact   │             │
│   │           │  │           │  │           │             │
│   │ Track     │  │ Persistent│  │ Manually  │             │
│   │ progress  │  │ tasks     │  │ compress  │             │
│   │ with a    │  │ with deps │  │ context   │             │
│   │ checklist │  │ on disk   │  │ window    │             │
│   └───────────┘  └───────────┘  └───────────┘             │
│                                                             │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐     │
│   │ list_skills │  │ read_skill   │  │background_*  │     │
│   │             │  │              │  │              │     │
│   │ See what    │  │ Load expert  │  │ Run long     │     │
│   │ skills are  │  │ knowledge    │  │ commands in  │     │
│   │ available   │  │ (e.g. how to │  │ background   │     │
│   │             │  │  make PDFs)  │  │ (fire-and-   │     │
│   └─────────────┘  └──────────────┘  │  forget)     │     │
│                                       └──────────────┘     │
│  Plan mode tools:                                          │
│   ┌────────────────┐  ┌─────────────────┐                  │
│   │enter_plan_mode │  │ exit_plan_mode  │                  │
│   │                │  │                 │                  │
│   │Agent decides to│  │Signal that plan │                  │
│   │enter read-only │  │is ready for     │                  │
│   │exploration mode│  │user approval    │                  │
│   │(sentinel-based)│  │(sentinel-based) │                  │
│   └────────────────┘  └─────────────────┘                  │
│                                                             │
│  Team tools (when enabled):                                │
│   ┌──────────────┐  ┌──────────┐  ┌───────────┐           │
│   │spawn_teammate│  │send_     │  │ broadcast │           │
│   │              │  │ message  │  │           │           │
│   │Create a named│  │Talk to a │  │Message    │           │
│   │teammate agent│  │specific  │  │all team   │           │
│   │with its own  │  │teammate  │  │members at │           │
│   │agent loop    │  │or lead   │  │once       │           │
│   └──────────────┘  └──────────┘  └───────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### How Tools Work

Each tool has two parts:

1. **Definition** — a JSON description that tells the LLM what the tool does and what inputs it needs (like a manual)
2. **Handler** — the actual Python function that runs when the LLM calls the tool

When the LLM sees the tool definitions, it decides which ones to use. The system then calls the corresponding handler and sends the result back.

### Safety Features

Tools aren't a free-for-all. There are guardrails:

- **bash**: Blocks dangerous commands (`rm -rf /`, `sudo`, `shutdown`). Has a 60-second timeout.
- **file tools**: Can only access files inside the workspace folder. Path traversal attacks (like `../../etc/passwd`) are blocked.
- **task (sub-agents)**: Maximum depth of 2 — a sub-agent can't spawn more sub-agents forever.
- **token budget**: The whole system has a spending limit (default 200K tokens) so it doesn't run forever.

---

## The WebSocket: Real-Time Streaming

### Why Not Just HTTP?

With normal HTTP (REST), the flow would be:

```
You:     "Write me a program"
         .......... (wait 30 seconds, staring at blank screen) ..........
Server:  "Here's everything I did" (one giant response)
```

With WebSocket, you see everything **as it happens**:

```
You:     "Write me a program"
Server:  "I'll start by..." (text_delta)
Server:  "Using tool: write_file" (tool_call)
Server:  "File created successfully" (tool_result)
Server:  "Now let me test it..." (text_delta)
Server:  "Using tool: bash" (tool_call)
Server:  "Output: Hello World!" (tool_result)
Server:  "All done! Here's what I did..." (text_delta)
Server:  {type: "done", files: [...], usage: {...}} (done)
```

### The Event Types

The server sends different types of JSON events through the WebSocket:

```
┌──────────────────┬──────────────────────────────────────────┐
│ Event            │ What it means                            │
├──────────────────┼──────────────────────────────────────────┤
│ text_delta       │ A chunk of the agent's response text     │
│                  │ (arrives word by word, like typing)       │
├──────────────────┼──────────────────────────────────────────┤
│ tool_call        │ The agent wants to use a tool            │
│                  │ (e.g. "running bash command: ls")        │
├──────────────────┼──────────────────────────────────────────┤
│ tool_result      │ The tool finished, here's the output     │
├──────────────────┼──────────────────────────────────────────┤
│ subagent_start   │ A sub-agent was spawned for a subtask    │
├──────────────────┼──────────────────────────────────────────┤
│ subagent_end     │ The sub-agent finished                   │
├──────────────────┼──────────────────────────────────────────┤
│ todo_update      │ The task checklist was updated           │
├──────────────────┼──────────────────────────────────────────┤
│ task_update      │ A persistent task was created, updated,  │
│                  │ or completed                             │
├──────────────────┼──────────────────────────────────────────┤
│ background_result│ A background command finished running    │
├──────────────────┼──────────────────────────────────────────┤
│ teammate_status  │ A teammate agent changed state           │
│                  │ (spawned, working, idle, shutdown)       │
├──────────────────┼──────────────────────────────────────────┤
│ compact          │ Old messages were summarized to save     │
│                  │ memory (context window management)       │
├──────────────────┼──────────────────────────────────────────┤
│ tool_approval    │ The agent wants permission to run a tool │
│ _request         │ (when approval is enabled)               │
├──────────────────┼──────────────────────────────────────────┤
│ tool_approval    │ User responded to an approval request    │
│ _result          │                                          │
├──────────────────┼──────────────────────────────────────────┤
│ plan_mode        │ Plan mode was toggled on or off          │
│ _changed         │                                          │
├──────────────────┼──────────────────────────────────────────┤
│ plan_ready       │ The agent finished planning and the      │
│                  │ plan is ready for review                 │
├──────────────────┼──────────────────────────────────────────┤
│ plan_approved    │ User approved the plan                   │
├──────────────────┼──────────────────────────────────────────┤
│ plan_rejected    │ User rejected the plan (with optional    │
│                  │ feedback)                                │
├──────────────────┼──────────────────────────────────────────┤
│ teams_changed    │ Teams were toggled on or off             │
├──────────────────┼──────────────────────────────────────────┤
│ approval_changed │ Tool approval was toggled on or off      │
├──────────────────┼──────────────────────────────────────────┤
│ llm_request      │ (tracing) The exact prompt sent to       │
│                  │ the LLM                                  │
├──────────────────┼──────────────────────────────────────────┤
│ llm_response     │ (tracing) The exact response from        │
│                  │ the LLM                                  │
├──────────────────┼──────────────────────────────────────────┤
│ interrupted      │ Agent was interrupted mid-stream by      │
│                  │ user feedback                            │
├──────────────────┼──────────────────────────────────────────┤
│ done             │ The agent loop finished. Includes        │
│                  │ token usage and any files created.       │
├──────────────────┼──────────────────────────────────────────┤
│ error            │ Something went wrong                     │
└──────────────────┴──────────────────────────────────────────┘
```

---

## How Everything Connects: The Full Journey of a Message

Let's trace what happens when you type *"Create a hello world Python script"* from start to finish:

```
 STEP 1: You type and hit Send
 ═══════════════════════════════════════════════════════════

   Browser (app.js)
     │
     ├── Renders your message in the chat window
     ├── Disables the input box (streaming mode)
     └── Sends via WebSocket:
         {"type": "message", "content": "Create a hello world Python script"}


 STEP 2: Server receives your message
 ═══════════════════════════════════════════════════════════

   WebSocket handler (websocket.py)
     │
     ├── Acquires per-conversation lock (prevents race conditions)
     ├── Loads conversation history from SQLite database
     ├── Appends your message to the history
     ├── Starts a cancel listener (in case you disconnect)
     └── Calls agent_loop() ──────────────────────────────────┐
                                                               │
                                                               ▼
 STEP 3: The agent loop runs                              agent_loop()
 ═══════════════════════════════════════════════════════════
                                                               │
   TURN 1:                                                     │
     │                                                         │
     ├── Builds system prompt:                                 │
     │     "You are a coding agent. Workspace: /workspace"     │
     │     + memory from past sessions                         │
     │     + available skills list                             │
     │     + available sub-agent types                         │
     │                                                         │
     ├── Calls the configured LLM via llm.stream():            │
     │     - model: "configured model name"                    │
     │     - system: (the system prompt above)                 │
     │     - messages: [your message + any history]            │
     │     - tools: [bash, read_file, write_file, ...]         │
     │                                                         │
     ├── Streams text back to browser:                         │
     │     ◄── text_delta: "I'll create a hello world..."      │
     │     ◄── text_delta: "script for you."                   │
     │                                                         │
     ├── The LLM also requested a tool:                        │
     │     write_file({path: "hello.py", content: "print(..."})│
     │                                                         │
     │     ◄── tool_call: {tool: "write_file", input: {...}}   │
     │                                                         │
     ├── Executes the tool:                                    │
     │     write_file handler creates the file on disk         │
     │                                                         │
     │     ◄── tool_result: {tool: "write_file",               │
     │                       result: "File written: hello.py"} │
     │                                                         │
     ├── Appends tool result to conversation                   │
     │                                                         │
     └── Continues to TURN 2...                                │
                                                               │
   TURN 2:                                                     │
     │                                                         │
     ├── Calls the LLM again with updated history              │
     │   (now includes the tool result)                        │
     │                                                         │
     ├── The LLM responds with just text (no tools):           │
     │     ◄── text_delta: "I've created hello.py with..."     │
     │                                                         │
     ├── response.done = true → EXIT LOOP                      │
     │                                                         │
     └── Returns usage: {input_tokens: 1234, output_tokens: 89}


 STEP 4: Cleanup and finalization
 ═══════════════════════════════════════════════════════════

   WebSocket handler (websocket.py)
     │
     ├── Saves all new messages to SQLite database
     ├── Saves token usage to database
     ├── Sets conversation title to "Create a hello world..."
     ├── Scans workspace for files the agent created
     │     → finds: [{name: "hello.py", path: "hello.py", size: 28}]
     │
     └── Sends final event:
         ◄── done: {usage: {input: 1234, output: 89},
                     files: [{name: "hello.py", ...}]}


 STEP 5: Browser updates
 ═══════════════════════════════════════════════════════════

   Browser (app.js)
     │
     ├── Re-enables the input box
     ├── Updates token counter in the header
     ├── Renders a "Files created" card with download link
     └── Refreshes the conversation list in the sidebar
```

---

## Smart Features

### 1. Self-Verification via Think Tool

Instead of a separate verification phase injected by the loop, the agent uses the **think tool** to verify its own work before finishing. The system prompt instructs the agent to:

1. Review tool results for unaddressed errors
2. Confirm all parts of the original request were completed
3. Re-read any files it created or modified
4. Fix any issues it finds (using tools as needed)
5. Summarize what was done

```
Agent writes file → Agent runs it → Agent uses think tool:
                                       │
                                       ▼
                                  "Let me verify:
                                   - File created ✓
                                   - Ran successfully ✓
                                   - Output correct ✓
                                   - All parts addressed ✓"
                                       │
                                       ├── Finds issue → fixes with tools → re-verifies
                                       └── All good → responds with summary → DONE!
```

**Key design choices:**
- **Agent-driven**: The agent decides when, what, and how to verify — not forced by the loop
- **Natural flow**: Verification happens within the normal tool loop, not as a separate phase
- **No extra turns**: For simple tasks, the agent may skip explicit verification and just respond
- **Flexible depth**: The agent can verify as many times as needed — no hardcoded round limits

### 2. Three-Layer Compaction (Memory Management)

LLMs have a limited "memory" per conversation (called a **context window**). As conversations get long, they might not fit. The system handles this with three layers of compaction, each progressively more aggressive:

**Layer 1 — Micro-compact (every turn, zero LLM cost)**

This is the cheapest trick in the book. Every turn, the system scans old tool results (more than 100 characters, excluding the last 3 results) and replaces them with a short placeholder like `[Previous: used bash]`. This happens silently every turn and costs nothing — no LLM call needed, just string replacement. It keeps the conversation history from ballooning with huge tool outputs that the agent no longer needs to see.

**Layer 2 — Auto-compact with transcript preservation**

When input tokens exceed a threshold, the system kicks in with a heavier approach. First, it saves the full conversation history to `workspace/.transcripts/` as a backup (so you always have an audit trail). Then it uses the LLM to summarize the older messages into a concise recap. The last 8 messages are kept intact so the agent doesn't forget what it was just doing. If the LLM summary fails for any reason, the system falls back to hard truncation — it just drops the oldest messages to make things fit.

**Layer 3 — Manual compact tool**

The agent can also call the `compact` tool on demand to trigger compaction whenever it feels the context is getting cluttered. Under the hood, this uses the sentinel pattern: the tool returns `__COMPACT_REQUESTED__`, and the agent loop detects this special value and triggers the Layer 2 compaction process.

Here's how the three layers look in practice:

```
Layer 1 — Micro-compact (every turn, free):
  tool_result from 10 turns ago: "read_file → [487 lines of code...]"
  becomes: "[Previous: used read_file]"

Layer 2 — Auto-compact (when context gets full):

  BEFORE compaction (too long!):
  ┌────────────────────────────────────────┐
  │ Message 1: "Create a web server"       │
  │ Message 2: [tool calls and results]    │
  │ Message 3: "Now add authentication"    │  ← old messages
  │ Message 4: [tool calls and results]    │    (summarized)
  │ Message 5: "Add a database"            │
  │ Message 6: [tool calls and results]    │
  │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
  │ Message 7: "Now deploy it"             │
  │ Message 8: [tool calls and results]    │  ← recent messages
  │ Message 9: "Fix the Docker issue"      │    (kept intact)
  │ Message 10: [tool calls and results]   │
  └────────────────────────────────────────┘

  AFTER compaction (fits!):
  ┌────────────────────────────────────────┐
  │ [Summary]: "User built a web server    │  ← LLM-generated
  │  with auth and database. Files:        │    summary
  │  server.py, auth.py, db.py"            │
  │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
  │ Message 7: "Now deploy it"             │
  │ Message 8: [tool calls and results]    │  ← kept as-is
  │ Message 9: "Fix the Docker issue"      │
  │ Message 10: [tool calls and results]   │
  └────────────────────────────────────────┘

Layer 3 — Manual compact (agent decides):
  Agent calls compact tool → loop triggers Layer 2
```

The key insight is that these layers work together: Layer 1 quietly trims the fat every turn, Layer 2 kicks in automatically when things get tight, and Layer 3 lets the agent take control when it knows a big summarization would help.

### 3. Persistent Memory (Cross-Session Learning)

When you disconnect, the system analyzes your entire conversation and saves key learnings to a file (`.agent/memory.md`). Next time you connect, these learnings are loaded:

```
SESSION 1:
  You: "I always use pytest for testing"
  You: "My project uses PostgreSQL"
  [disconnect]
       │
       ▼ (LLM analyzes and saves to .agent/memory.md)

SESSION 2:
  System prompt now includes:
  "Memory from previous sessions:
   - User prefers pytest for testing
   - Project uses PostgreSQL database"
```

The memory file is organized into sections: User Preferences, Project Context, Decisions, and Corrections.

### 4. Sub-Agents (Divide and Conquer)

For complex tasks, the main agent can spawn **sub-agents** — smaller, focused agents that handle a specific subtask:

```
┌─────────────────────────────────────────────────┐
│              MAIN AGENT                         │
│                                                 │
│  "I need to refactor this codebase.             │
│   Let me break it down..."                      │
│                                                 │
│   ┌──────────────┐  ┌──────────────┐            │
│   │  Sub-agent:  │  │  Sub-agent:  │            │
│   │  "explore"   │  │  "code"      │            │
│   │              │  │              │            │
│   │  Investigates│  │  Does the    │            │
│   │  the codebase│  │  actual      │            │
│   │  (read-only) │  │  refactoring │            │
│   │              │  │  (full tools)│            │
│   └──────┬───────┘  └──────┬───────┘            │
│          │                 │                    │
│          ▼                 ▼                    │
│   "Found 3 files     "Refactored              │
│    that need work"    successfully"            │
│                                                 │
└─────────────────────────────────────────────────┘
```

There are four types:

| Type | Purpose | Tools Available |
|------|---------|----------------|
| **explore** | Investigate code (read-only) | bash, read_file, think |
| **code** | Write and modify code | All tools |
| **plan** | Analyze and plan (no changes) | bash, read_file, think |
| **research** | Deep investigation | bash, read_file, write_file, think |

Sub-agents run in isolation — they have their own conversation history, their own system prompt, and they can't spawn more sub-agents (max depth = 2, preventing infinite loops).

### 5. Skills (Expert Knowledge On Demand)

Skills are like **instruction manuals** the agent can read when it needs specialized knowledge:

```
skills/
├── code-review/SKILL.md      ← How to do thorough code reviews
├── api-design/SKILL.md       ← REST API design best practices
├── dockerfile-builder/SKILL.md ← Docker image best practices
├── pdf-writer/SKILL.md       ← How to generate PDFs with Python
├── excel-writer/SKILL.md     ← How to create Excel files
├── ppt-writer/SKILL.md       ← How to make PowerPoint slides
├── docx-writer/SKILL.md      ← How to create Word documents
└── design/SKILL.md           ← Frontend design patterns
```

The agent doesn't load all skills at once (that would waste context). Instead, it sees a **short description** of each skill, and only loads the full content when it decides it needs it. This is called **progressive disclosure**:

```
Layer 1 (always visible):   "pdf-writer — Create PDF documents with Python"
                                       │
                            Agent thinks: "I need this!"
                                       │
                                       ▼
Layer 2 (loaded on demand): Full SKILL.md with templates, code examples,
                            library APIs, and best practices
                                       │
                                       ▼
Layer 3 (referenced):      scripts/, assets/ folders with helper files
```

### 6. Presets (Different Personalities)

The agent can behave differently based on the **preset** chosen:

```
┌─────────────────────────────────────┐
│  "coding" preset (default)          │
│                                     │
│  System: "You are a coding agent.   │
│   Use tools to write code.          │
│   Plan → Act → Report."            │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  "work" preset                      │
│                                     │
│  System: "You are a work assistant. │
│   Help create documents,            │
│   spreadsheets, presentations."     │
└─────────────────────────────────────┘
```

Presets are stored as `PROMPT.md` files in the `prompts/` directory. When you start a new chat, you pick a preset, and that determines the agent's system prompt (its "personality" and instructions).

### 7. Think Tool (Structured Reasoning & Self-Verification)

Sometimes the agent needs to **pause and think** before acting — especially when analyzing complex tool outputs, weighing trade-offs, planning multi-step tasks, or **verifying its own work** before finishing. The `think` tool gives it a dedicated space to reason without side effects:

```
Agent receives complex error output from bash tool
     │
     ▼
┌──────────────────────────────────────────────────┐
│  think({                                          │
│    thought: "The error says 'ModuleNotFoundError' │
│    for pandas. This means:                        │
│    1. pandas isn't installed in this env          │
│    2. I should check if there's a requirements    │
│       file first before pip installing            │
│    3. The user might have a venv I should use     │
│    Let me check for requirements.txt and venvs."  │
│  })                                               │
└──────────────────────────────────────────────────┘
     │
     ▼
Agent now calls bash("ls requirements*.txt .venv/")
     (makes a better decision because it thought first)
```

The tool is a **no-op** — it doesn't fetch new information or change anything. The thought is simply logged in the conversation. The value is in forcing the model to articulate its reasoning as a discrete step, which often leads to better decisions on complex tasks.

The think tool serves double duty as the agent's **self-verification mechanism**. Before finishing a task, the agent uses `think` to review its work — checking tool results for errors, confirming all parts of the request were addressed, and deciding whether to fix issues or respond. This replaces the need for a separate verification phase in the loop.

The think tool is available everywhere: the main agent loop, all sub-agent types, and all teammates.

### 8. Agent Teams (Multi-Agent Collaboration)

For truly complex projects, a single agent isn't enough. The system can spawn **named teammate agents** that work in parallel, each with their own agent loop:

```
┌──────────────────────────────────────────────────────┐
│                    LEAD AGENT                         │
│                                                       │
│  "I need to build a REST API with tests.              │
│   Let me spawn teammates for parallel work."          │
│                                                       │
│   spawn_teammate("alice", "backend", "Build the API") │
│   spawn_teammate("bob", "tester", "Write tests")      │
│                                                       │
│        ┌──────────────┐      ┌──────────────┐         │
│        │  "alice"     │      │  "bob"       │         │
│        │  (backend)   │      │  (tester)    │         │
│        │              │      │              │         │
│        │  WORKING...  │      │  WORKING...  │         │
│        │  Building    │      │  Writing     │         │
│        │  the API     │      │  tests       │         │
│        └──────┬───────┘      └──────┬───────┘         │
│               │                     │                 │
│               └──── message bus ────┘                 │
│                    (async inbox)                      │
│                                                       │
│  Lead reads inbox:                                    │
│    alice: "API ready at routes.py"                    │
│    bob: "Tests passing, 12 assertions"                │
└──────────────────────────────────────────────────────┘
```

**How teammates work:**

Each teammate runs a **WORK/IDLE state machine**:
- **WORK phase**: Standard agent loop — call LLM, execute tools, drain inbox. When done, call the `idle` tool.
- **IDLE phase**: Poll every 5 seconds for new inbox messages or unclaimed tasks on the task board. If nothing arrives after 60 seconds, auto-shutdown.

Teammates have their own tools: bash, file tools, think, send_message, read_inbox, and idle. They can **not** spawn more teammates (prevents infinite spawning).

Communication happens through a **message bus** — an async inbox per agent. The lead can send targeted messages, broadcast to everyone, or request structured protocols (shutdown requests, plan approvals).

Teams are **opt-in per conversation** — you enable them when creating a new chat.

### 9. Background Tasks (Fire-and-Forget)

Some commands take a long time (builds, test suites, downloads). Instead of blocking the agent loop, the agent can run them in the **background**:

```
Agent: "I'll run the test suite in the background
        while I work on the next feature."

  background_run("pytest -v tests/")
     │
     ├── Returns immediately: "task_id: bg_001"
     │
     │   Agent continues working on other things...
     │
     ▼ (later, at start of next turn)

  Loop automatically drains notifications:
     "bg_001 completed: 42 passed, 1 failed"

  Agent sees the result and can react to it.
```

Background tasks run as async subprocesses. Their results are collected in a notification queue and automatically injected into the conversation at the start of each turn.

### 10. Persistent Tasks (File-Backed Task Board)

For complex multi-step work, the agent can create **persistent tasks** that survive context compaction:

```
┌─────────────────────────────────────────────────┐
│  TASK BOARD (.tasks/ directory)                   │
│                                                   │
│  #1 ✓ Set up project structure                   │
│  #2 ● Implement authentication  ← in progress    │
│       blockedBy: []                              │
│  #3 ○ Add rate limiting         ← pending         │
│       blockedBy: [#2]           ← can't start    │
│  #4 ○ Write integration tests                     │
│       blockedBy: [#2, #3]       ← blocked by 2   │
└─────────────────────────────────────────────────┘
```

Each task is stored as a JSON file on disk (`workspace/.tasks/task_1.json`). Tasks support:
- **Dependencies**: `blockedBy` and `blocks` arrays
- **Cascade completion**: Finishing task #2 automatically unblocks #3
- **Ownership**: Teammates can claim unclaimed tasks from the board
- **Metadata**: Arbitrary key-value pairs

This is separate from the simpler `todo_*` tools (which are in-memory checklists).

### 11. Plan Mode (Think Before You Act)

For complex tasks, it's better to **plan first** rather than dive straight into writing code. Plan mode is a read-only exploration phase where the agent can look at the codebase but can't make any changes.

```
                     ┌─────────────────────┐
  User sends         │    Normal Mode      │
  complex task  ───► │  (all tools)        │
                     └──────────┬──────────┘
                                │
                    Agent calls enter_plan_mode
                    (or user activates it)
                                │
                                ▼
                     ┌─────────────────────┐
                     │    Plan Mode        │
                     │  (read-only tools)  │◄──── revise
                     │                     │        │
                     │  - read_file        │        │
                     │  - think            │        │
                     │  - task_create      │        │
                     │  - exit_plan_mode   │        │
                     │                     │        │
                     │  ✗ bash             │        │
                     │  ✗ write_file       │        │
                     │  ✗ edit_file        │        │
                     └──────────┬──────────┘        │
                                │                   │
                    Agent calls exit_plan_mode       │
                                │                   │
                                ▼                   │
                     ┌─────────────────────┐        │
                     │  Plan presented     │        │
                     │  for approval       │        │
                     └──┬──────┬───────┬───┘        │
                        │      │       │            │
                   Approve  Feedback  Reject        │
                        │      │                    │
                        │      └────────────────────┘
                        ▼
                     ┌─────────────────────┐
                     │  Execute plan       │
                     │  (full tools)       │
                     └─────────────────────┘
```

**How it works under the hood:**

Plan mode uses the **sentinel pattern** (same as the compact tool). The `enter_plan_mode` tool returns a magic string `__ENTER_PLAN_MODE__`. The agent loop detects this and:

1. Sets `_plan_mode = True` (a mutable local variable)
2. Recalculates which tools are available (only read-only ones)
3. Appends `PLAN_MODE_PROMPT` to the system prompt
4. Emits a `plan_mode_changed` event to the UI

When the agent is done planning, it calls `exit_plan_mode` (returns `__PLAN_READY__`). The loop:

1. Extracts the plan text from the last assistant message
2. Emits a `plan_ready` event
3. Breaks out of the loop

The plan then goes through the approval flow — the user can approve (switches to execution), reject with feedback (agent revises), or just reject.

**Four ways to activate plan mode:**

| Method | Who initiates |
|--------|--------------|
| `enable_plan_mode` flag at chat creation | User (UI/API) |
| `/plan` slash command in CLI | User (CLI) |
| Toggle button in web UI header | User (UI) |
| `enter_plan_mode` tool call | **Agent** (autonomous) |

The last one is new — the agent can **decide on its own** that a task is complex enough to warrant planning first, just like a human developer would sketch out an approach before coding.

### 12. Tool Approval (Human-in-the-Loop)

Some tools are harmless — reading a file or thinking out loud can't break anything. But running a shell command like `rm -rf /` or overwriting a config file? You probably want a say in that.

When **tool approval** is enabled for a conversation, the agent pauses before running any "dangerous" tool and asks you for permission first. Read-only tools like `think`, `read_file`, `list_skills`, and `compact` are in a **SAFE_TOOLS** set — they execute automatically without bothering you. But write tools like `bash`, `write_file`, and `edit_file` trigger a permission prompt.

Here's what happens under the hood:

```
Agent wants to run bash("rm old_files/")
    │
    ▼
Is bash in SAFE_TOOLS? → No
    │
    ▼
Send tool_approval_request to user
    │
    ▼
┌─────────────────────────────────┐
│  "Agent wants to run:           │
│   bash: rm old_files/           │
│                                 │
│  [Approve] [Deny] [Auto]       │
└─────────────────────────────────┘
    │
    ├── Approve → execute normally
    ├── Deny → "User denied this tool call" sent to LLM
    └── Auto-approve → no more prompts this session
```

When the agent hits a tool that needs approval, it sends a `tool_approval_request` event over the WebSocket to the UI. Then it **blocks** — the agent loop waits on an `asyncio.Queue` until it hears back from you. You have three choices:

- **Approve**: The tool runs normally, and the agent continues.
- **Deny**: The tool is skipped, and the LLM receives `"User denied this tool call"` as the tool result. This lets the agent adjust its approach — maybe it'll try a safer command or ask you for guidance.
- **Auto-approve**: Approval is turned off for the rest of the session. Every tool runs without asking from that point on.

There's a **5-minute timeout** on the approval prompt. If you disconnect or walk away, the agent won't hang forever — it times out and treats it as a denial.

One important detail: **sub-agents don't get their own approval prompts**. When you approve the `task` tool (which spawns a sub-agent), that sub-agent runs autonomously. The approval happened at the parent level — you approved the delegation, so the sub-agent is trusted to do its job.

Tool approval is **opt-in per conversation**. You enable it when creating a chat (via the API or a UI toggle), so your normal quick-and-dirty sessions aren't slowed down by constant prompts.

### 13. Cancellation & Interrupt (Mid-Stream Feedback)

Sometimes the agent starts heading in the wrong direction and you don't want to wait for it to finish before correcting course. Cancellation and interrupt let you **stop the agent mid-stream** and either bail out or redirect it.

Each WebSocket session creates an `asyncio.Event` called `cancelled`. This is the kill switch — the agent loop checks it before every LLM call and before every tool execution.

```
Agent is working...  ──── user sends new message ────►  Interrupt!
    │                                                      │
    ▼                                                      ▼
Stops at next            New agent turn starts with:
checkpoint               "User interrupted: actually do X instead"
```

There are two flavors:

**Cancel** — just stop. The client sends `{"type": "cancel"}` over the WebSocket. The agent finishes whatever atomic operation it's in the middle of (it doesn't kill a running subprocess mid-byte), then stops at the next checkpoint and sends a `done` event. Clean exit.

**Interrupt with feedback** — stop and redirect. The client sends `{"type": "interrupt", "content": "actually do X instead"}`. The agent stops the same way, but instead of just quitting, it starts a **new turn** with your feedback as the user message. The agent sees something like `"User interrupted: actually do X instead"` and picks up from there with the new direction.

In the **CLI**, this works through `Ctrl+C`. When you interrupt, the CLI shows a feedback prompt — you can type a new direction (like "focus on the tests instead") or just press Enter to cancel without feedback.

In the **web UI**, there's a cancel button that appears in the input bar while the agent is streaming. Typing a new message while the agent is working triggers an interrupt with your message as the feedback.

One subtle detail: when the agent is interrupted mid-response, it might have produced a partial assistant message that includes a `tool_use` block without a matching `tool_result`. The provider message format requires these to be paired, so the system **strips orphaned tool_use blocks** from the interrupted message before starting the new turn. Without this cleanup, the next API call would fail validation.

### 14. MCP — Plugging In External Tools

The agent comes with a solid set of built-in tools (bash, file read/write, think, etc.), but what if you want it to interact with GitHub, Slack, a database, or some custom internal service? That's where **MCP** (Model Context Protocol) comes in.

MCP is a plugin system for AI tools. It lets external servers **expose tools** that the agent can use, just like its built-in ones. Think of it like browser extensions — the browser works fine on its own, but extensions give it new powers.

```
Without MCP:
  Agent --> built-in tools only (bash, files, think...)

With MCP:
  Agent --> built-in tools + external MCP tools
              |
              |-- mcp__filesystem__read_file
              |-- mcp__filesystem__write_file
              |-- mcp__github__create_issue
              +-- mcp__slack__send_message
```

**How to set it up:** Create a file called `mcp_servers.json` in the backend directory. No file = no MCP, zero performance impact. The agent works exactly the same without it.

Here's what a config looks like:

```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "env": { "NODE_ENV": "production" }
  },
  "github": {
    "url": "https://mcp.github.example.com",
    "headers": { "Authorization": "Bearer ${GITHUB_TOKEN}" }
  }
}
```

Notice the `${GITHUB_TOKEN}` syntax — the config supports **environment variable substitution**, so you don't have to hardcode secrets.

**Two connection modes:**

| Mode | How it works | When to use |
|------|-------------|-------------|
| **Client-mode** | The backend connects to MCP servers itself (local processes via `stdio`, or remote HTTP servers). Tools get namespaced as `mcp__{server}__{tool}` and injected into the ToolRegistry. | Works with any LLM provider. You control the servers. |
| **Remote-mode** | Server connection params are passed directly to Anthropic's API — the MCP server runs on Anthropic's side. | For Anthropic-hosted MCP services. |

In client-mode, when the backend starts up, it reads `mcp_servers.json`, connects to each configured server, discovers what tools they offer, and registers them in the ToolRegistry with namespaced names. From the agent's perspective, `mcp__filesystem__read_file` is just another tool — it doesn't know or care that the tool lives in an external process.

```
┌──────────────────────────────────────────────────────────┐
│  Backend (agent-api)                                     │
│                                                          │
│  ToolRegistry                                            │
│  |-- bash              (built-in)                        │
│  |-- write_file         (built-in)                       │
│  |-- read_file          (built-in)                       │
│  |-- think              (built-in)                       │
│  |-- mcp__filesystem__read_file    --+                   │
│  |-- mcp__filesystem__write_file   --+-- from MCP server │
│  |-- mcp__github__create_issue     --+                   │
│  +-- mcp__slack__send_message      --+                   │
│                                                          │
└──────────────────────────────────────────────────────────┘
         |                    |                 |
         v                    v                 v
   +───────────+      +───────────+     +───────────+
   | filesystem|      |  github   |     |   slack   |
   | MCP server|      | MCP server|     | MCP server|
   | (stdio)   |      | (HTTP)    |     | (HTTP)    |
   +───────────+      +───────────+     +───────────+
```

The key insight: MCP is **purely additive**. It doesn't change how the agent loop works, doesn't affect the LLM wrapper chain, and doesn't touch existing tools. It just makes the ToolRegistry bigger.

### 15. Loop Completion Guarantees

What happens if the agent is halfway through writing code and runs out of output tokens? Or hits the turn limit while still working? You'd get an incomplete response — a half-written file, an unexplained stop, or no summary of what was accomplished.

The agent loop has **three safety nets** to make sure you always get a proper conclusion:

**1. Truncation auto-continuation**

When the model hits `max_output_tokens` mid-generation (the API returns `stop_reason=max_tokens`), the loop doesn't just give up. It injects a **continuation prompt** — essentially saying "keep going from where you left off" — and lets the model finish its thought. This can happen up to **3 times** in a row, preventing the common problem where the model writes code but stops before it can execute it.

```
LLM response stopped:  stop_reason = "max_tokens"  (hit the limit!)
    |
    v
Continuation #1:  "Please continue from where you left off."
    |
    v
LLM continues...  stop_reason = "max_tokens"  (still going!)
    |
    v
Continuation #2:  "Please continue from where you left off."
    |
    v
LLM continues...  stop_reason = "end_turn"  (done naturally!)
```

**2. Wrap-up nudge**

When the agent is **3 turns away from the turn limit**, the system prompt gets a little extra paragraph telling the model to start wrapping things up. It's a gentle hint, not a hard stop — the agent can still use tools and do real work, but it knows time is running out.

**3. Forced final summary**

If the agent exhausts all its turns and still hasn't stopped, the loop makes **one last LLM call** with all tools disabled. The model has no choice but to produce a text response — a summary of everything it accomplished (and anything it didn't finish). This guarantees you always get a readable conclusion, never a silent stop.

Here's how these three mechanisms work together near the end of a run:

```
Turn 47/50:  "You're approaching the turn limit. Please wrap up."
                  (nudge added to system prompt)
Turn 48/50:  Agent continues working...
Turn 49/50:  Agent continues working...
Turn 50/50:  FORCED: "Summarize everything you've done" (no tools)
                --> Agent produces final summary --> DONE
```

The result: no matter what happens — token limits, turn limits, or the model just being verbose — you always get a meaningful final response.

---

## The LLM Wrapper Chain: Safety Layers

The system doesn't talk to a provider API directly from the loop. Instead, it wraps the adapter in **transparent layers**, each adding one concern:

```
┌───────────────────────────────────────────────────────┐
│                                                       │
│  Agent Loop                                           │
│     │                                                 │
│     ▼                                                 │
│  TracingLLMClient (optional, per-session)             │
│  │  Emits llm_request/llm_response events            │
│  │  to the WebSocket for the dev panel                │
│  │                                                    │
│  ▼                                                    │
│  RetryingLLMClient                                    │
│  │  Retries on 429 (rate limit), 500, 502, 503       │
│  │  Exponential backoff with jitter                   │
│  │  Max 3 retries                                     │
│  │                                                    │
│  ▼                                                    │
│  ProviderAdapter                                      │
│  │  Translates to/from provider SDK format            │
│  │                                                    │
│  ▼                                                    │
│  Provider API                                         │
│                                                       │
└───────────────────────────────────────────────────────┘
```

Each wrapper satisfies the same `LLMClient` interface, so the agent loop doesn't know (or care) how many layers exist. You can add or remove layers by changing one line in `main.py`.

---

## The Database: Remembering Conversations

Everything is saved in a SQLite database (`agent.db`) with three tables:

```
┌─────────────────────────────────────────────────────────────┐
│                        SQLite Database                      │
│                                                             │
│  ┌─────────────────┐                                        │
│  │  conversations  │                                        │
│  │─────────────────│                                        │
│  │ id (UUID)       │──┐                                     │
│  │ title           │  │                                     │
│  │ system_prompt   │  │  one conversation                   │
│  │ preset          │  │  has many messages                  │
│  │ enable_teams    │  │  and many token usage records       │
│  │ enable_tracing  │  │                                     │
│  │ enable_approval │  │                                     │
│  │ enable_plan_mode│  │                                     │
│  │ created_at      │  │                                     │
│  │ updated_at      │  │                                     │
│  └─────────────────┘  │                                     │
│                       │                                     │
│  ┌─────────────────┐  │  ┌─────────────────┐               │
│  │    messages     │  │  │   token_usage   │               │
│  │─────────────────│  │  │─────────────────│               │
│  │ id              │  │  │ id              │               │
│  │ conversation_id │◄─┤  │ conversation_id │◄──┘           │
│  │ role (user/     │  │  │ input_tokens    │               │
│  │   assistant)    │  │  │ output_tokens   │               │
│  │ content (JSON)  │  │  │ model           │               │
│  │ created_at      │  │  │ created_at      │               │
│  └─────────────────┘  │  └─────────────────┘               │
│                       │                                     │
└───────────────────────┴─────────────────────────────────────┘
```

This means you can close your browser, come back later, and your conversations are still there.

---

## The Frontend: What You See

There are two web frontends, both built with **plain HTML, CSS, and JavaScript** — no React, no Vue, no build step. Just open them in a browser.

### The Developer UI (agent-ui/)

```
┌─────────────────────────────────────────────────────────────────┐
│  ┌──────────┐  ┌──────────────────────────────────────────────┐ │
│  │ SIDEBAR  │  │                CHAT AREA                    │ │
│  │          │  │                                              │ │
│  │ + New    │  │  ┌─────────────────────────────────┐        │ │
│  │          │  │  │ You: Create a Python script     │        │ │
│  │ Chat 1   │  │  └─────────────────────────────────┘        │ │
│  │ Chat 2 ● │  │                                              │ │
│  │ Chat 3   │  │  ┌─────────────────────────────────┐        │ │
│  │          │  │  │ Agent: I'll create that for you  │        │ │
│  │          │  │  │                                   │        │ │
│  │          │  │  │ ▼ Tool: write_file               │        │ │
│  │          │  │  │   {path: "script.py", ...}       │        │ │
│  │          │  │  │   ✓ File written successfully    │        │ │
│  │          │  │  │                                   │        │ │
│  │          │  │  │ ▼ Tool: bash                      │        │ │
│  │          │  │  │   python script.py                │        │ │
│  │          │  │  │   ✓ Output: Hello World!         │        │ │
│  │          │  │  │                                   │        │ │
│  │          │  │  │ Done! Created script.py           │        │ │
│  │          │  │  └─────────────────────────────────┘        │ │
│  │          │  │                                              │ │
│  │          │  │  ┌─────────────────────────────────┐        │ │
│  │          │  │  │ 📄 Files: script.py (128 bytes) │        │ │
│  │          │  │  │    [Download]                     │        │ │
│  │          │  │  └─────────────────────────────────┘        │ │
│  │          │  │                                              │ │
│  │          │  │  ┌──────────────────────────┐ [Send]        │ │
│  │          │  │  │ Type a message...        │               │ │
│  │          │  │  └──────────────────────────┘               │ │
│  └──────────┘  └──────────────────────────────────────────────┘ │
│                                                                 │
│  Tokens: 1,234 in / 89 out          ● Connected    [Dev Panel] │
└─────────────────────────────────────────────────────────────────┘
```

### Key Developer UI Files (agent-ui/)

| File | Purpose |
|------|---------|
| `index.html` | Page structure, loads everything |
| `css/styles.css` | Dark theme styling |
| `js/app.js` | Main orchestrator — wires everything together |
| `js/state.js` | Simple state management (current conversation, messages, etc.) |
| `js/api.js` | HTTP REST client (create chats, list conversations, etc.) |
| `js/websocket.js` | WebSocket connection with auto-reconnect |
| `js/renderer.js` | Builds DOM elements (messages, tool blocks, file cards) |
| `js/markdown.js` | Renders markdown text with syntax highlighting |
| `js/devpanel.js` | Developer panel showing raw WebSocket traffic |

### The User UI (agent-user-ui/)

The User UI is a separate frontend designed for **end users** who want to interact with the agent without seeing developer-level detail. It connects to the same backend as the Developer UI.

```
┌─────────────────────────────────────────────────────────────────┐
│  Developer UI (agent-ui)        │  User UI (agent-user-ui)      │
│                                 │                               │
│  ● Dark theme                   │  ● Forest Canopy light theme  │
│  ● Expandable tool blocks       │  ● Activity indicators        │
│    with raw input/output        │    ("Thinking...", "Writing")  │
│  ● Dev panel (WebSocket         │  ● Simplified approval        │
│    frame inspector)             │    dialogs                    │
│  ● Token usage display          │  ● Clean, minimal layout      │
│  ● Full technical detail        │  ● User-friendly messaging    │
│                                 │                               │
│  For: developers, debugging     │  For: end users, demos        │
└─────────────────────────────────┴───────────────────────────────┘
```

### Key User UI Files (agent-user-ui/)

| File | Purpose |
|------|---------|
| `index.html` | Page structure, loads everything |
| `css/styles.css` | Forest Canopy light theme styling |
| `js/app.js` | Main orchestrator — wires everything together |
| `js/state.js` | Simple state management |
| `js/api.js` | HTTP REST client |
| `js/websocket.js` | WebSocket connection with auto-reconnect |
| `js/renderer.js` | Builds DOM elements (messages, activity indicators) |
| `js/markdown.js` | Renders markdown text with syntax highlighting |
| `js/config.js` | Configuration (API endpoint, ports) |
| `js/filepanel.js` | File browser panel |

---

## The Terminal CLI (agent-cli/)

Not everyone wants to open a browser. The **Terminal CLI** is a rich command-line interface that gives you the full agent experience right in your terminal. Same backend, same agent loop, same tools — just a different way to interact.

The binary is called `openagent`. You install it, type `openagent`, and you're in a conversation.

```
┌─────────────────────────────────────────────────────────┐
│  $ openagent                                            │
│                                                         │
│  OpenAgent v0.1.0                                       │
│                                                         │
│  You: Create a hello world script                       │
│                                                         │
│  ● Thinking...                                          │
│                                                         │
│  I'll create a simple Python script for you.            │
│                                                         │
│  ┌─ write_file: hello.py ────────────────────────┐      │
│  │ print("Hello, World!")                         │      │
│  └────────────────────────────────────────────────┘      │
│                                                         │
│  ┌─ bash ────────────────────────────────────────┐      │
│  │ $ python hello.py                              │      │
│  │ Hello, World!                                  │      │
│  └────────────────────────────────────────────────┘      │
│                                                         │
│  Done! 1,234 in · 89 out · $0.02 · 3% ctx              │
│                                                         │
│  You: _                                                 │
└─────────────────────────────────────────────────────────┘
```

### Key Features

**Interactive REPL with prompt-toolkit.** The input line uses Python's `prompt_toolkit` library, which gives you persistent history (your previous messages are saved across sessions), fish-style auto-suggestions (it grays out completions from your history as you type), and `Esc+Enter` for multiline input. There's even a vi mode toggle if you're that kind of person.

**Slash commands.** Type `/` to see what's available:

| Command | What it does |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear the screen |
| `/compact` | Manually trigger context compaction |
| `/model` | Switch the LLM model mid-conversation |
| `/history` | List saved sessions |
| `/resume` | Resume a previous session |
| `/cost` | Show cost breakdown for the current session |
| `/plan` | Enter plan mode (think before acting) |
| `/execute` | Exit plan mode and execute |
| `/teams` | Toggle multi-agent teams on/off |
| `/approval` | Toggle tool approval on/off |
| `/quit` | Exit the CLI |

**Session persistence.** Every conversation is automatically saved. You can come back later and pick up where you left off with `openagent --resume` (shows a list of recent sessions) or `openagent --resume <ID>` (jumps straight to a specific one).

**Cost tracking.** After every agent turn, the CLI shows a summary line with input tokens, output tokens, dollar cost for that turn, and a context window percentage (how full the context is). You always know what you're spending.

```
Done! 1,234 in · 89 out · $0.02 · 3% ctx
       ^          ^         ^        ^
       |          |         |        +-- context window usage
       |          |         +-- cost for this turn
       |          +-- tokens the model generated
       +-- tokens sent to the model
```

**Pipe mode.** For scripting and automation, you can pipe input directly:

```bash
echo "Explain this error: $(cat error.log)" | openagent --no-approval
```

In pipe mode, the CLI reads from stdin, runs the agent without interactive prompts, prints the result, and exits. The `--no-approval` flag skips tool approval prompts so it can run unattended.

**Interrupt with feedback.** Press `Ctrl+C` while the agent is working and you get a choice: type new instructions to redirect the agent (like "stop, focus on the tests instead") or press Enter to just cancel. This is the same interrupt mechanism as the web UI, just adapted for the terminal.

**Code block rendering.** Code in the agent's responses is syntax-highlighted using `rich.Syntax` with the Monokai theme. It looks good even in a plain terminal.

**Config file.** Defaults live in `~/.openagent/config.toml` — you can set your preferred model, approval mode, and other options so you don't have to pass flags every time.

---

## The Complete Architecture

Here's how every piece fits together:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                      YOUR BROWSER                               │
│                                                                 │
│  agent-ui/ (Developer)           agent-user-ui/ (User)          │
│  ┌─────────┐ ┌───────────┐      ┌─────────┐ ┌───────────┐     │
│  │ app.js  │ │renderer.js│      │ app.js  │ │renderer.js│     │
│  │(wiring) │ │(DOM)      │      │(wiring) │ │(activity  │     │
│  └────┬────┘ └─────┬─────┘      └────┬────┘ │indicators)│     │
│       │            │                  │      └─────┬─────┘     │
│  ┌────────────┐ ┌──────────┐    ┌────────────┐ ┌──────────┐   │
│  │websocket.js│ │ api.js   │    │websocket.js│ │ api.js   │   │
│  │(streaming) │ │(REST)    │    │(streaming) │ │(REST)    │   │
│  └─────┬──────┘ └────┬─────┘    └─────┬──────┘ └────┬─────┘   │
│        │             │                │              │          │
│        └──────┬──────┘                └──────┬───────┘          │
│               └──────────────┬───────────────┘                  │
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
               ┌───────────────┼───────────────┐
               │  WebSocket    │    REST/HTTP   │
               │  (streaming)  │    (CRUD)      │
               │               │               │
┌─────────────┼───────────────┼───────────────┼───────────────────┐
│             ▼               ▼               │                   │
│  ┌───────────────────────────────────────┐  │  BACKEND          │
│  │           main.py                     │  │  (FastAPI)        │
│  │  Creates everything at startup:       │  │                   │
│  │  - LLM adapter                        │  │                   │
│  │  - Skill loader                       │  │                   │
│  │  - Prompt loader                      │  │                   │
│  │  - Database connection                │  │                   │
│  └───────────┬───────────────────────────┘  │                   │
│              │                              │                   │
│    ┌─────────┴─────────┐                    │                   │
│    ▼                   ▼                    │                   │
│  ┌───────────┐  ┌─────────────┐             │                   │
│  │websocket  │  │   routes    │             │                   │
│  │.py        │  │   .py       │             │                   │
│  │           │  │             │             │                   │
│  │ Manages   │  │ REST API:   │             │                   │
│  │ real-time │  │ - CRUD      │             │                   │
│  │ streaming │  │ - tools     │             │                   │
│  │ sessions  │  │ - skills    │             │                   │
│  └─────┬─────┘  │ - files     │             │                   │
│        │        └─────────────┘             │                   │
│        ▼                                    │                   │
│  ┌──────────────────────────────────┐       │                   │
│  │         agent_loop()             │       │                   │
│  │         (loop.py)                │       │                   │
│  │                                  │       │                   │
│  │  while not done:                 │       │                   │
│  │    micro_compact()               │       │                   │
│  │    drain background notifs       │       │                   │
│  │    drain team inbox              │       │                   │
│  │    response = llm.stream(...)    │───┐   │                   │
│  │    if done: break                │   │   │                   │
│  │    execute tools in parallel     │───┼──►│  ToolRegistry     │
│  │    append results                │   │   │  ┌──────────────┐ │
│  │    ── sentinel handling ──       │   │   │  │ bash         │ │
│  │    compact? → compress context   │   │   │  │ file tools   │ │
│  │    enter_plan? → switch mode     │   │   │  │ think        │ │
│  │    exit_plan? → emit plan_ready  │   │   │  │ todo_*       │ │
│  │    check budget & auto-compact   │   │   │  │ task_*       │ │
│  │                                  │   │   │  │ task         │ │
│  └──────────────────────────────────┘   │   │  │ compact      │ │
│                                         │   │  │ skills       │ │
│  ┌──────────────────────────────────┐   │   │  │ background_* │ │
│  │     LLMClient (Protocol)         │◄──┘   │  │ team tools   │ │
│  │                                  │       │  │ plan_mode *  │ │
│  │  ┌────────────────────────────┐  │       │  └──────────────┘ │
│  │  │   TracingLLMClient        │  │       │                   │
│  │  │   (optional per-session)  │  │       │                   │
│  │  ├────────────────────────────┤  │       │  └──────────────┘ │
│  │  │   RetryingLLMClient       │  │       │                   │
│  │  │   (auto-retry on errors)  │  │       │                   │
│  │  ├────────────────────────────┤  │       │                   │
│  │  │   ProviderAdapter         │  │       │                   │
│  │  │   (translates to/from     │  │       │                   │
│  │  │    provider SDK format)   │  │       │                   │
│  │  └─────────────┬──────────────┘  │       │                   │
│  └────────────────┼─────────────────┘       │                   │
│                   │                         │                   │
└───────────────────┼─────────────────────────┴───────────────────┘
                    │
                    ▼
           ┌────────────────┐
           │  Provider API  │
           │  (configured)  │
           │                │
           │  The actual    │
           │  AI model      │
           └────────────────┘

  Also in the backend:

  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │ SQLite DB    │  │ SkillLoader  │  │MemoryManager │
  │              │  │              │  │              │
  │ conversations│  │ Reads skill  │  │ Reads/writes │
  │ messages     │  │ files from   │  │ .agent/      │
  │ token usage  │  │ skills/      │  │ memory.md    │
  └──────────────┘  └──────────────┘  └──────────────┘

  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │ TaskManager  │  │ Background   │  │ Teammate     │
  │              │  │ Manager      │  │ Manager      │
  │ Persistent   │  │              │  │              │
  │ tasks with   │  │ Fire-and-    │  │ Spawns named │
  │ dependencies │  │ forget async │  │ teammates    │
  │ (.tasks/)    │  │ subprocesses │  │ with inbox   │
  └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Glossary

| Term | Meaning |
|------|---------|
| **Agent** | An AI that can take actions (not just chat) by using tools in a loop |
| **Agent loop** | The while-loop that repeatedly calls the LLM and executes tools until done |
| **LLM** | Large Language Model — the AI brain behind the agent |
| **Context window** | The maximum amount of text an LLM can "see" at once before older context must be compacted |
| **Token** | A unit of text (~4 characters or ~¾ of a word). LLMs count everything in tokens. |
| **Tool** | A function the AI can call (bash, file read/write, etc.) |
| **Think tool** | A no-op tool that gives the agent a space to reason step-by-step before acting and to self-verify work before finishing |
| **Protocol** | A Python interface — defines what methods a class must have, without specifying how |
| **Adapter** | A wrapper that translates between two different interfaces |
| **Wrapper chain** | Multiple transparent layers stacked on top of each other (retry → tracing → adapter) |
| **WebSocket** | A persistent connection between browser and server for real-time, two-way communication |
| **REST API** | Standard HTTP endpoints for request/response operations (create, read, update, delete) |
| **Streaming** | Sending data piece by piece as it's generated, instead of all at once |
| **Sub-agent** | A child agent spawned for a focused subtask, with its own isolated conversation |
| **Teammate** | A named agent running its own loop in parallel, communicating via an async message bus |
| **Message bus** | Per-agent async inbox (queue) for sending and receiving messages between agents |
| **Compaction** | Summarizing old messages to free up space in the context window |
| **Background task** | A long-running command (build, tests) run as a subprocess without blocking the agent |
| **Task board** | Persistent file-backed tasks with dependencies that survive context compaction |
| **Preset** | A system prompt template that defines the agent's personality and behavior |
| **Skill** | A knowledge document the agent can load on demand for specialized tasks |
| **System prompt** | Hidden instructions that define how the AI behaves (the user doesn't see this) |
| **Plan mode** | A read-only exploration phase where the agent designs a plan before making changes |
| **Sentinel** | A magic string returned by a tool that the loop detects and acts on (e.g. `__ENTER_PLAN_MODE__`) |
| **Feature flags** | Per-conversation toggles (enable_teams, enable_tracing, enable_plan_mode) set at chat creation time |
| **FastAPI** | A Python web framework for building APIs |
| **SQLite** | A lightweight database stored as a single file |
| **MCP** | Model Context Protocol — a standard for AI tools served by external processes, like plugins |
| **Truncation auto-continuation** | When the model hits its output limit mid-response, the loop automatically prompts it to keep going |
| **REPL** | Read-Eval-Print Loop — an interactive prompt that reads input, processes it, and prints the result |
| **Pipe mode** | Running the CLI non-interactively by piping input from another command (e.g. `echo "..." \| openagent`) |
