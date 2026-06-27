# AgentShell

Local shell for AI agents to control a Windows PC.

## Onboarding (agent)

On session start, call `help --json` to receive the full command schema.
Every command returns `{"ok": bool, "data": {...}, "error": str|null, "state_delta": {...}}`.

## Session flow

```
help --json           → receive full schema (do this once per session)
context get           → get current mandatory context (active window, last action, state, goal)
listener status       → verify listener and indexer are active before trusting context
screen active         → check active window title
screen elements       → get UI elements via Accessibility Tree (preferred over capture)
  if complete=false   → description via OCR returned automatically (0.3+)
  if description insufficient → screen capture --region active (last resort)
screen find           → find a specific element by text instead of parsing all elements
screen wait           → wait for an element to appear after triggering an action
<execute action>      → mouse click / keyboard type / app launch / etc.
context get           → verify state updated after action
index query --last 5  → retrieve recent activity history if needed
```

## Perception priority

1. `screen elements` — structured UI tree, no vision model needed, fastest
2. `screen find` — when you know what you're looking for, skip full element list
3. OCR description — auto-attached when tree is incomplete, text-based, no token cost
4. `screen capture --region active` — active window only, use when OCR is insufficient
5. `screen capture --region full` — full desktop, last resort

## Memory system

- `context get` — mandatory context, always current (5 fields: active_window, last_action, result, state, session_goal)
- `index query` — pull-based history, call only when you need past context
- `index logs` — query internal error log (WARNING/ERROR level)
- `listener status` — check if C# listener and indexer are active
- Context updates automatically after every command via state_delta
- Indexer runs in background, does not block commands

## Command reference

Run `help --json` for full schema with parameter types and descriptions.

Groups: screen | mouse | keyboard | audio | window | app | clipboard | index | context | listener

## Running

### Terminal chat (agent + listener + chat) — recommended
```
python agent_chat.py               # start everything + chat
python agent_chat.py --url http://...  # connect to running backend
```

### Agent (backend + listener) — headless
```
python agent_init.py
python agent_init.py --frontend   # also start React UI
```

### Interactive REPL (shell only)
```
python main.py
```

### Subprocess (single command)
```
python main.py audio volume --set 60
```

Installed (after pip install):
```
agentshell
agentshell audio volume --set 60
```

## Environment

- `GROQ_API_KEY` — required for agent (main LLM + memory indexing)
- Or place key in `config/api_keys.json` as `{"groq_api_key": "..."}`

---

## Version history

### v0.1 — Core foundation
- REPL with auto-discovery of command modules
- Executor with full command set: `screen`, `mouse`, `keyboard`, `audio`, `window`, `app`, `files`
- Uniform JSON response schema with `state_delta`
- Machine-readable docs via `help --json`
- Memory system: Listener (C#) → Aggregator → Indexer (Groq llama-3.1-8b) → SQLite store
- Mandatory context (5 fields, always flat)
- Pull-based index queries
- Accessibility Tree as primary perception layer, screenshot as fallback
- Subprocess mode (`agentshell <command>`)

### v0.2 — Consolidation and fixes
- **Fix:** `Program.cs` — stopWatcher resource leak
- **Fix:** `indexer.py` — context validated and merged before writing, prevents partial overwrites
- **Fix:** `ListenerClient.py` — pipe read now uses overlapped I/O with 1s timeout, no more thread hangs
- **Fix:** `screen.py` — element deduplication no longer drops elements at close positions
- **New:** `clipboard read` / `clipboard write` commands
- **New:** `screen region` — screenshot of arbitrary coordinates
- **New:** Structured logging to SQLite via `core/logger.py`, queryable with `index logs`

### v0.3 — Perception improvement
- **New:** OCR as intermediate perception layer between Accessibility Tree and raw screenshot
- When `screen elements` returns `complete: false`, a text description via OCR is automatically attached to the response — no extra command needed
- Agent only requests raw screenshot when OCR description is insufficient
- Eliminates vision model token cost in the vast majority of fallback cases

### v0.4 — Observability and environment awareness
- **New:** `screen monitors` — enumerate all connected monitors with bounds and resolution
- Multi-monitor support in `screen capture`, `screen region`, and OCR — active window captured correctly regardless of which monitor it's on
- **New:** `listener status` — check if C# listener is running via heartbeat file, includes indexer state
- C# listener writes heartbeat every 5s to `data/listener_heartbeat.json`
- **New:** Clipboard watch in C# listener — emits `clipboard_change` events when user copies content
- Clipboard changes flow through Aggregator → Indexer → context, agent sees them via `index query`

### v0.5 — Command depth
- **audio:** `audio devices` — list input/output devices, `audio device` — switch default device, `audio app` — per-app volume and mute control
- **screen:** `screen find` — locate element by text, returns position directly, `screen text` — extract all visible text in reading order, `screen wait` — wait for element to appear with timeout
- **window:** `window resize`, `window move`, `window snap` (left/right/maximize/restore), `window info` — detailed window metadata including process and PID
- **response:** removed null/empty fields from JSON output — cleaner signal for the agent

### v0.6 — Gap coverage
- **mouse:** `mouse position` — current cursor coordinates
- **files:** `files exists` — check if path exists without listing directory, `files info` — file/directory metadata (size, dates, extension)
- **app:** `app focus` — bring app to foreground by process name
- **screen:** `screen waitgone` — wait for element to disappear, complements `screen wait`
- **fix:** `pyautogui.FAILSAFE = False` — prevents cursor corner exception from killing the agent

### v0.7 — App resolution 
- **app:** `app launch` rewritten — now searches Program Files, Program Files (x86), Windows registry, and system PATH before falling back to Start Menu
- Depth-limited directory search (4 levels) via `os.walk` — faster than `rglob`
- `_APP_ALIASES` now used as search accelerator, not hard requirement — unlisted apps resolve automatically
- Start Menu fallback (Win → type → Enter) as last resort with `note` in response
- **app:** `_launch_via_start_menu` now verifies the process actually started by comparing process list before and after — returns `ok: false` instead of false positive if launch failed

### v0.8 — System awareness and notifications 
- **New group `system`:** `system info`, `system cpu`, `system ram`, `system disk`, `system battery` — full hardware and OS state queryable by the agent
- **New group `network`:** `network status`, `network ip`, `network connections` — connectivity state and active connections, filterable by process
- **New group `notify`:** `notify send` — Windows toast notifications with configurable duration

### v0.9 — REPL improvements 
- **New:** Command history — up/down arrows navigate previous commands, persists across sessions in `data/.shell_history`
- **New:** Tab autocompletion — completes groups and commands, double Tab shows all options
- **New:** Verbose mode — `--verbose on/off` shows command timing and state delta after each response

### v1.0 — Agent integration 
- **New:** `AgentShellClient` — Python SDK to connect any LLM to the framework without managing subprocess or JSON parsing manually
- **New:** `examples/` — reference integration scripts for Groq, OpenAI, and Anthropic showing the recommended agent loop pattern
- Agent sends commands wrapped in ```shell blocks, shell returns JSON, agent continues — no framework-specific training needed

### v1.1 — User memory 
- **New group `user`:** persistent key-value memory about the user, organized in fixed categories
- Categories: `preferences`, `environment`, `schedule`, `identity`, `projects`, `misc`
- Commands: `user set`, `user get`, `user list`, `user delete`
- Stored in SQLite alongside session memory — persists across sessions
- Agent writes to memory as it learns about the user, reads it to personalize behavior

### v1.2 — Bug fixes 
- **Fix:** `app focus` — now collects all PIDs matching the process name before searching for a visible window, resolves multi-instance apps like Brave and Spotify
- **Fix:** `screen text/elements/find/wait/waitgone` — `_resolve_window` now excludes the shell process itself when no `--window` is specified, avoids capturing the terminal instead of the target app
- **Fix:** `audio volume` — fallback to `IMMDeviceEnumerator` when `GetSpeakers().Activate()` fails, resolves pycaw version compatibility issue

### v1.2 — Routines 
- **New group `routine`:** `routine set`, `routine get`, `routine list`, `routine delete`, `routine run`
- User describes a routine in natural language, agent translates to shell commands and saves them
- `routine run` executes saved commands directly — deterministic, zero token cost, no model interpretation needed
- Routines stored in SQLite under the `routines` user memory category, persist across sessions

### v1.3 — Credentials store
- **New group `credentials`:** `credentials set`, `credentials get`, `credentials list`, `credentials delete`
- Values encrypted at rest using Fernet symmetric encryption (`cryptography` library)
- Encryption key stored in `data/.secret.key` — excluded from git, auto-generated on first run
- `credentials list` shows services and keys but never values
- Agent can retrieve credentials to authenticate with external services without exposing secrets in conversation history

### v1.4 — Overlay system  *(previous)*
- **New group `overlay`:** `overlay notify`, `overlay status`, `overlay confirm`, `overlay chat`
- `overlay notify` — floating notification, auto-dismisses after configurable duration
- `overlay status` — persistent indicator at top of screen showing agent activity, cleared with `overlay status` (no message)
- `overlay confirm` — blocking Yes/No dialog, returns `{"confirmed": true/false}`
- `overlay chat` — floating chat window with message history, supports agent/user sender roles
- All visual constants extracted to `core/overlay_theme.py` — developers replace this file to apply custom themes without touching core logic

### v1.6 — Florence-2 vision backend  *(current)*
- **Vision backend rewritten:** replaced LocateAnything-3B (GGUF + safetensors) with `florence-community/Florence-2-base` (231M params, ~1.6GB)
- **Built-in transformers class:** uses `Florence2ForConditionalGeneration` (transformers 4.57.6+), no `trust_remote_code` needed
- **Task prompt `<OPEN_VOCABULARY_DETECTION>`** — open-vocabulary detection with pixel-coordinate bboxes, no 0-1000 normalization
- **GGUF path removed:** `llama-cpp-python` mmproj silently ignored in 0.3.18; mtmd.dll does not support `locateanything` projector type
- **Performance:** ~1-2s inference on GTX 1050 Ti 4GB, ~2.5GB VRAM peak
- **Dependencies:** removed `llama-cpp-python` soft dependency; added `einops`, `timm`

### v1.5 — Visual grounding & Screen Entity Memory
- **Perception pipeline upgraded:** Accessibility Tree → OCR → Vision → raw capture (each fallback triggers only when prior layer is insufficient)
- **New command `screen detect`** — locate UI elements by natural language prompt: `screen detect --prompt "play button" --window "Spotify"`
- **New group `entity`:** persistent screen entity registry with LLM-friendly names
  - `entity register` — save element with `llm_name` (e.g. "botón play"), window, bounds, detection source
  - `entity get` — resolve by `llm_name` + optional window, returns coordinates for direct click
  - `entity find` — partial name search across windows
  - `entity list` / `entity delete` / `entity update` — management
- **Auto-registration:** successful detections from `screen elements`, `screen detect`, `screen find` automatically stored as entities
- **New command `screen click_entity`** — click by `llm_name` using memorized coordinates, zero vision cost on repeat
- **Disambiguation by window:** same `llm_name` across different windows resolved via `active_window` context or explicit `--window`
- **New SQLite table `screen_entities`** — UUID stable ID, hit count, `last_seen`, source tracking (accessibility / ocr / locate_anything / manual)
- **Dependencies added:** `llama-cpp-python`, `huggingface-hub`