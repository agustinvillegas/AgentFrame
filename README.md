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
  if complete=false   → screen capture --region active  (fallback)
<execute action>      → mouse click / keyboard type / app launch / etc.
context get           → verify state updated after action
index query --last 5  → retrieve recent activity history if needed
```

## Perception priority

1. `screen elements` — structured UI tree, no vision model needed, fastest
2. `screen capture --region active` — active window only, use when elements incomplete
3. `screen capture --region full` — full desktop, last resort

## Memory system

- `context get` — mandatory context, always current (5 fields: active_window, last_action, result, state, session_goal)
- `index query` — pull-based history, call only when you need past context
- Context updates automatically after every command via state_delta
- Indexer runs in background, does not block commands

## Command reference

Run `help --json` for full schema with parameter types and descriptions.

Groups: screen | mouse | keyboard | audio | window | app | index | context

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
