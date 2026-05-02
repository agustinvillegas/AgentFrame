# AgentShell

Local shell for AI agents to control a Windows PC.

## Onboarding (agent)

On session start, call `help --json` to receive the full command schema.
Every command returns `{"ok": bool, "data": {...}, "error": str|null, "state_delta": {...}}`.

## Session flow

```
help --json           → receive full schema (do this once per session)
context get           → get current mandatory context (active window, last action, state, goal)
screen active         → check active window title
screen elements       → get UI elements via Accessibility Tree (preferred over capture)
  if complete=false   → description via OCR returned automatically (0.3+)
  if description insufficient → screen capture --region active (last resort)
<execute action>      → mouse click / keyboard type / app launch / etc.
context get           → verify state updated after action
index query --last 5  → retrieve recent activity history if needed
```

## Perception priority

1. `screen elements` — structured UI tree, no vision model needed, fastest
2. OCR description — auto-attached when tree is incomplete, text-based, no token cost
3. `screen capture --region active` — active window only, use when OCR is insufficient
4. `screen capture --region full` — full desktop, last resort

## Memory system

- `context get` — mandatory context, always current (5 fields: active_window, last_action, result, state, session_goal)
- `index query` — pull-based history, call only when you need past context
- `index logs` — query internal error log (WARNING/ERROR level)
- Context updates automatically after every command via state_delta
- Indexer runs in background, does not block commands

## Command reference

Run `help --json` for full schema with parameter types and descriptions.

Groups: screen | mouse | keyboard | audio | window | app | clipboard | index | context

## Running

Interactive REPL:
```
python main.py
```

Subprocess (single command):
```
python main.py audio volume --set 60
```

Installed (after pip install):
```
agentshell
agentshell audio volume --set 60
```

## Environment

- `GROQ_API_KEY` — enables memory indexing (optional, shell works without it)
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

### v0.3 — Perception improvement *(current)*
- **New:** OCR as intermediate perception layer between Accessibility Tree and raw screenshot
- When `screen elements` returns `complete: false`, a text description via OCR is automatically attached to the response — no extra command needed
- Agent only requests raw screenshot when OCR description is insufficient
- Eliminates vision model token cost in the vast majority of fallback cases