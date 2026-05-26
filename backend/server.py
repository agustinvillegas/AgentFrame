"""
FastAPI Backend for AgentShell Desktop Agent
Exposes REST API for Electron frontend to interact with the AI agent
"""
import re
import sys
from pathlib import Path
from typing import Optional, Literal
import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from agentshell.client import AgentShellClient

# ── Configuration ────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-5-20250929"
MAX_TURNS = 10
MAX_TOKENS = 1024
NO_CMD_RETRIES = 2

SYSTEM = """You are an AI agent controlling a Windows PC via AgentShell. Commands return JSON: {"ok": true/false, "data": {...}}.

When you need to act, output EXACTLY three lines:
BEGIN_COMMAND
<one single AgentShell command line>
END_COMMAND
Use -- for flags. Do not add any other text when outputting a command.

━━━ CRITICAL ━━━
- ONE command per response. Never write prose before the command block.
- If you need multiple steps, execute them one at a time and wait for the result.
- NEVER chain commands. NEVER explain before acting.

━━━ BEFORE EVERY ACTION ━━━
1. Call screen active to verify the focused window
2. If wrong window: use window focus or app focus first
3. NEVER type or click without confirming focus

━━━ PERCEPTION ORDER ━━━
1. screen find --text "..." --window "..."
2. screen elements --window "..."
3. screen text --window "..."
4. screen capture --region active — last resort only
Always use --window. Omitting it captures the terminal, not the app.

PERCEPTION POLICY (ENFORCED)
- Prefer screen elements, then screen find, then screen text.
- Only use screen capture as a last resort, and only as screen capture --region active.

━━━ EXECUTION RULES ━━━
- Complete ONLY what was asked. Stop immediately after ok:true.
- Never repeat, undo, or run extra commands after success.
- On failure: try ONE alternative. If that fails, report and stop.
- AFTER ACTION, ALWAYS VERIFY: If action success (ok:true), capture screen to confirm visual result
- Report what you see: "Paused ✓" or "Click worked, music stopped" or "Failed - music still playing"
- Never report success unless you received ok:true.

━━━ MEMORY ━━━
Session start: call user list and context get.
Store when you learn something:
- user set --category preferences --key ... --value ...
- user set --category environment --key ... --value ...
- user set --category identity --key ... --value ...
- credentials set --service ... --key ... --value ... for sensitive data
Before asking the user for info, check memory first.

━━━ ROUTINES ━━━
Save: routine set --name "..." --steps "cmd1|cmd2|cmd3"
Run: routine run --name "..."
Suggest saving when user repeats multi-step processes.

━━━ COMMUNICATION ━━━
- Respond in the user's language.
- One sentence to confirm completion, after the command block.
- Act directly — never explain before acting.

━━━ MEDIA CONTROL ━━━
For Spotify in browser (Brave, Chrome, Arc):
1. keyboard hotkey --keys "space" (with browser focused) — most reliable
2. keyboard hotkey --keys "media_play_pause" — system-level, works without focus
NEVER use ctrl+m (that is mute, not play/pause)

━━━ VERIFICATION ━━━
- "ok: true" means the command executed, NOT that it had the desired effect
- For media: use screen find BEFORE the action to confirm initial state
  - If "Pause" button found → music is playing → space will pause it
  - If "Play" button found → music already paused → no action needed
- "not found" in screen find means the tree doesn't expose it, NOT that state changed
- If tree doesn't expose play/pause: use screen capture as last resort to visually confirm

━━━ WINDOW FOCUS ━━━
- AgentShell Desktop runs inside Brave — app focus "Brave" may focus the wrong window
- Use window list first to identify the correct Brave window title containing Spotify
- Then use window focus --title with the exact Spotify tab title

━━━ MEDIA IN BROWSER TABS ━━━
Browser tabs (Spotify, YouTube) do NOT appear in window list — they share the browser process.
For media playback in any browser tab: always use keyboard hotkey --keys "media_play_pause"
This is a system-level key that works regardless of focus.
NEVER try to focus a browser window and send space — it will hit the wrong target.

"""




# ── FastAPI Setup ────────────────────────────────────────────────────────────
app = FastAPI(title="AgentShell Desktop API", version="1.0.0")
logger = logging.getLogger("agentshell.api")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Enable CORS for Electron
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global State ─────────────────────────────────────────────────────────────
class AgentState:
    def __init__(self):
        self.client: Optional[anthropic.Anthropic] = None
        self.shell: Optional[AgentShellClient] = None
        self.messages: list[dict] = []
        self.compact_schema: str = ""
        self.full_schema: dict = {}
        self.running = False
        self.session_id: str = ""
        self.log_path: Optional[Path] = None

    def init(self, api_key: str):
        """Initialize agent with API key"""
        self.client = anthropic.Anthropic(api_key=api_key)
        self.shell = AgentShellClient()
        self.compact_schema, self.full_schema = self._build_schema()
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.log_path = Path(__file__).parent / f"agent-{self.session_id}.jsonl"
        # Initialize messages with system prompt
        self.messages = [
            {"role": "system", "content": f"{SYSTEM}\n\nAvailable commands:\n{self.compact_schema}"}
        ]
        self._log_event({"type": "init"})

        # Mandatory onboarding (per README): run help --json once per session.
        try:
            schema_result = self.shell.run("help --json")
            self._log_event({"type": "prime", "command": "help --json", "result": schema_result})
            
        except Exception as e:
            self._log_event({"type": "prime_error", "command": "help --json", "error": str(e)})

        # Prime the agent with mandatory context so it uses the framework correctly.
        try:
            ctx = self.shell.run("context get")
            self._log_event({"type": "prime", "command": "context get", "result": ctx})
            
        except Exception as e:
            self._log_event({"type": "prime_error", "command": "context get", "error": str(e)})

        try:
            status = self.shell.run("listener status")
            self._log_event({"type": "prime", "command": "listener status", "result": status})
            
        except Exception as e:
            self._log_event({"type": "prime_error", "command": "listener status", "error": str(e)})

    def _log_event(self, payload: dict):
        if not self.log_path:
            return
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to write agent log: %s", e)

    def _build_schema(self) -> tuple[str, dict]:
        """Build compact schema from shell and return (compact, full)."""
        try:
            schema = self.shell.schema()
            lines = []
            for group, commands in schema.items():
                for cmd, info in commands.items():
                    parts = []
                    for p, v in info.get("params", {}).items():
                        if v.get("required"):
                            parts.append(f"--{p}(required)")
                        else:
                            parts.append(f"--{p}[={v.get('default')}]")
                    line = f"{group} {cmd} {' '.join(parts)}".strip()
                    lines.append(line)
            return "\n".join(lines), schema
        except Exception as e:
            return f"Error loading schema: {e}", {}

    def close(self):
        """Clean up resources"""
        if self.shell:
            self.shell.close()

    def clear_context(self):
        """Clear conversation history"""
        self.messages = [self.messages[0]]
        self._log_event({"type": "clear"})


agent_state = AgentState()


# ── Models ───────────────────────────────────────────────────────────────────
class InitRequest(BaseModel):
    api_key: str


class MessageRequest(BaseModel):
    message: str
    mode: Literal["auto", "step"] = "auto"
    max_steps: int = 40


class MessageResponse(BaseModel):
    agent_reply: str
    command_executed: Optional[str] = None
    command_result: Optional[dict] = None
    error: Optional[str] = None


class SchemaResponse(BaseModel):
    schema: dict
    compact: str


# ── Utilities ────────────────────────────────────────────────────────────────
def _truncate_result(result: dict, max_chars: int = 600) -> str:
    text = str(result)
    if len(text) > max_chars:
        return text[:max_chars] + "... [truncated]"
    return text


def _build_context(messages: list, max_turns: int) -> list:
    """Always preserve system prompt + last max_turns turns"""
    system = messages[0]
    tail = messages[1:]
    cutoff = max_turns * 2
    return [system] + tail[-cutoff:]


def _extract_first_command(reply: str) -> Optional[str]:
    # Preferred format (no backticks): BEGIN_COMMAND ... END_COMMAND
    m = re.search(r"BEGIN_COMMAND\s*(.*?)\s*END_COMMAND", reply, re.DOTALL)
    if m:
        block = (m.group(1) or "").strip()
        if block:
            return block.splitlines()[0].strip() or None

    return None


def _normalize_command(cmd: str) -> str:
    """
    The model sometimes mistakenly includes the word 'shell' inside the command block
    (e.g. 'shell screen text'). Our runner expects raw commands like 'screen text ...'.
    """
    cmd = (cmd or "").strip()
    if cmd.lower().startswith("shell "):
        return cmd[6:].lstrip()
    return cmd


def _is_valid_command(schema: dict, cmd: str) -> bool:
    """
    Validate 'group name' exists before executing to reduce hallucinated commands.
    We only validate the first two tokens (group + command).
    """
    if not schema or not cmd:
        return True  # don't hard-fail if schema unavailable
    parts = cmd.strip().split()
    if len(parts) < 2:
        return False
    group, name = parts[0], parts[1]
    group_obj = schema.get(group)
    if not isinstance(group_obj, dict):
        return False
    return name in group_obj


def _guardrail_command(cmd: str, perception_attempted: bool) -> tuple[Optional[str], Optional[str], bool]:
    """
    Returns (possibly_rewritten_cmd, error_message, perception_attempted_after).
    - Enforces perception policy: screen capture is last resort.
    - Ensures screen capture always includes --region active (never full).
    """
    parts = cmd.strip().split()
    if len(parts) < 2:
        return cmd, None, perception_attempted

    group, name = parts[0], parts[1]
    is_perception = group == "screen" and name in {"elements", "find", "text", "wait", "waitgone"}
    if is_perception:
        # Enforce explicit target window to avoid reading the shell/terminal by accident.
        # This also makes results more predictable for the model.
        if "--window" not in parts:
            return None, f"Missing --window for {group} {name}. Provide --window \"<window title fragment>\".", perception_attempted
        return cmd, None, True

    if group == "screen" and name == "capture":
        if not perception_attempted:
            return None, "screen capture is last resort. Try screen elements/find/text first.", perception_attempted
        if "--region" not in parts:
            return f"{cmd} --region active", None, perception_attempted
        # If region is specified, force active (avoid full desktop)
        try:
            idx = parts.index("--region")
            if idx + 1 < len(parts) and parts[idx + 1] != "active":
                parts[idx + 1] = "active"
                return " ".join(parts), None, perception_attempted
        except ValueError:
            pass
        return cmd, None, perception_attempted

    return cmd, None, perception_attempted


def _is_ok(result: Optional[dict]) -> Optional[bool]:
    if result is None:
        return None
    ok = result.get("ok") if isinstance(result, dict) else None
    return bool(ok) if ok is not None else None


def _response_text(response) -> str:
    """
    Extract text from Anthropic SDK response safely.
    Avoids 'list index out of range' when content is empty or unexpected.
    """
    try:
        content = getattr(response, "content", None)
        if not content:
            return ""

        # Anthropic SDK typically returns a list of content blocks; concatenate all text blocks.
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text)
            elif isinstance(block, str) and block.strip():
                parts.append(block)

        return "\n".join(parts).strip()
    except Exception:
        return ""


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "agent_running": agent_state.running}


@app.post("/init")
async def init_agent(req: InitRequest):
    """Initialize agent with API key"""
    try:
        agent_state.init(api_key=req.api_key)
        agent_state.running = True
        return {
            "status": "initialized",
            "schema": agent_state.shell.schema(),
            "compact": agent_state.compact_schema,
            "log_file": str(agent_state.log_path) if agent_state.log_path else None,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Initialization failed: {e}")


@app.post("/message", response_model=MessageResponse)
async def send_message(req: MessageRequest):
    """Send a message to the agent and get a response"""
    if not agent_state.running:
        raise HTTPException(status_code=400, detail="Agent not initialized")

    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        agent_state._log_event({"type": "user_message", "message": req.message, "mode": req.mode, "max_steps": req.max_steps})
        agent_state.messages.append({"role": "user", "content": req.message})
        no_cmd_count = 0
        command_executed = None
        command_result = None
        steps = 0
        perception_attempted = False

        while True:
            if req.mode == "auto" and steps >= max(1, req.max_steps):
                return MessageResponse(
                    agent_reply="",
                    command_executed=command_executed,
                    command_result=command_result,
                    error=f"Stopped after max_steps={req.max_steps}",
                )

            context = _build_context(agent_state.messages, MAX_TURNS)

            response = agent_state.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=context[0]["content"],
                messages=context[1:],
            )

            reply = _response_text(response)
            if not reply:
                return MessageResponse(
                    agent_reply="",
                    command_executed=command_executed,
                    command_result=command_result,
                    error="Model returned empty response content",
                )
            agent_state.messages.append({"role": "assistant", "content": reply})
            agent_state._log_event({"type": "model_reply", "text": reply})

            first_cmd = _extract_first_command(reply)

            if first_cmd:
                no_cmd_count = 0

                # Enforce strict one-command execution per /message to avoid "random" extra actions.
                normalized_cmd = _normalize_command(first_cmd)
                if normalized_cmd != first_cmd.strip():
                    agent_state.messages.append(
                        {
                            "role": "user",
                            "content": f'{{"warning":"Do not include the word shell inside the command. Use raw command like: {normalized_cmd}"}}',
                        }
                    )

                if not _is_valid_command(agent_state.full_schema, normalized_cmd):
                    agent_state._log_event({"type": "invalid_command", "raw": first_cmd, "normalized": normalized_cmd})
                    agent_state.messages.append(
                        {
                            "role": "user",
                            "content": f'{{"error":"invalid command: {normalized_cmd}. Use only commands from help --json schema."}}',
                        }
                    )
                    continue

                guarded_cmd, guard_err, perception_attempted = _guardrail_command(
                    normalized_cmd, perception_attempted
                )
                if guard_err:
                    agent_state._log_event({"type": "guardrail_block", "command": normalized_cmd, "reason": guard_err})
                    agent_state.messages.append({"role": "user", "content": f'{{"error":"{guard_err}"}}'})
                    continue
                if guarded_cmd and guarded_cmd != normalized_cmd:
                    agent_state._log_event({"type": "guardrail_rewrite", "from": normalized_cmd, "to": guarded_cmd})
                    normalized_cmd = guarded_cmd

                command_executed = normalized_cmd
                agent_state._log_event({"type": "command", "command": normalized_cmd, "raw": first_cmd})
                result = agent_state.shell.run(normalized_cmd)
                command_result = result
                steps += 1
                agent_state._log_event({"type": "command_result", "command": normalized_cmd, "result": result})

                img_b64 = (result.get("data") or {}).get("image_b64") if isinstance(result, dict) else None
                if img_b64:
                    agent_state.messages.append({
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                        {"type": "text", "text": f"Screen capture result for: {normalized_cmd}"}
                    ]
                })
                else:
                    agent_state.messages.append(
                {
                    "role": "user",
                    "content": f"Command: {normalized_cmd}\nResult: {_truncate_result(result)}",
                }
            )

                if req.mode == "step":
                    ok = _is_ok(result)
                    status = "OK" if ok else "FAILED" if ok is False else "UNKNOWN"
                    return MessageResponse(
                        agent_reply=f"Paso ejecutado ({status}): {first_cmd}",
                        command_executed=command_executed,
                        command_result=command_result,
                    )

                # auto mode continues to let the model decide if more steps are needed
                continue
            else:
                # If we've already executed at least one command for this user message and the
                # model is now responding in prose (no command), treat that as the final answer.
                if steps > 0:
                    return MessageResponse(
                        agent_reply=reply,
                        command_executed=command_executed,
                        command_result=command_result,
                    )

                no_cmd_count += 1
                if no_cmd_count <= NO_CMD_RETRIES:
                    agent_state.messages.append(
                        {
                            "role": "user",
                            "content": '{"error": "no command found. If you need to act, use BEGIN_COMMAND and END_COMMAND with exactly one command line inside."}',
                        }
                    )
                else:
                    # Agent decided to finish or is lost, return its reply.
                    return MessageResponse(
                        agent_reply=reply,
                        command_executed=command_executed,
                        command_result=command_result,
                    )

    except Exception as e:
        agent_state._log_event({"type": "error", "error": str(e)})
        return MessageResponse(agent_reply="", error=str(e))


@app.post("/clear")
async def clear_context():
    """Clear conversation history"""
    agent_state.clear_context()
    return {"status": "cleared"}


@app.get("/schema", response_model=SchemaResponse)
async def get_schema():
    """Get available commands schema"""
    if not agent_state.running:
        raise HTTPException(status_code=400, detail="Agent not initialized")

    return SchemaResponse(
        schema=agent_state.shell.schema(),
        compact=agent_state.compact_schema,
    )


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    agent_state.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5000)
