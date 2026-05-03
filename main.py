"""
AgentShell — Agent-oriented PC control shell
"""
from __future__ import annotations
import importlib
import json
import os
import pkgutil
import shlex
import sys
import commands
from core.response import AgentResponse
from core.registry import registry
import pyautogui

VERSION = "0.5.0"
PROMPT  = ">>> "
pyautogui.FAILSAFE = False

# ── Auto-discover and register all command modules ────────────────────────────
for _, name, _ in pkgutil.iter_modules(commands.__path__):
    importlib.import_module(f"commands.{name}")
# ─────────────────────────────────────────────────────────────────────────────

# ── Memory session (optional — requires GROQ_API_KEY) ────────────────────────
_memory = None

def _launch_listener():
    """Launch the C# Listener as a background process if the exe exists."""
    from pathlib import Path
    import subprocess

    candidates = [
        # Published self-contained exe (recommended)
        Path(__file__).parent / "listener" / "bin" / "Release"
            / "net8.0-windows" / "win-x64" / "publish" / "AgentShellListener.exe",
        # Debug build fallback
        Path(__file__).parent / "listener" / "bin" / "Debug"
            / "net8.0-windows" / "AgentShellListener.exe",
    ]

    for exe in candidates:
        if exe.exists():
            try:
                subprocess.Popen(
                    [str(exe)],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"[Listener] Launched: {exe.name}")
                return True
            except Exception as e:
                print(f"[Listener] ⚠️ Could not launch listener: {e}")
                return False

    print("[Listener] Exe not found — skipping. Run 'dotnet publish' in listener/ to build it.")
    return False


def _init_memory():
    global _memory
    _launch_listener()
    api_key = os.environ.get("GROQ_API_KEY") or _load_api_key()
    if api_key:
        try:
            from memory import MemorySession
            _memory = MemorySession(groq_api_key=api_key)
        except Exception as e:
            print(f"[Memory] ⚠️ Could not initialize memory session: {e}")

def _load_api_key() -> str | None:
    try:
        from pathlib import Path
        config = Path(__file__).resolve().parent / "config" / "api_keys.json"
        if config.exists():
            data = json.loads(config.read_text(encoding="utf-8"))
            return data.get("groq_api_key")
    except Exception:
        pass
    return None
# ─────────────────────────────────────────────────────────────────────────────


def _parse_args(tokens: list[str]) -> tuple[dict, list[str]]:
    kwargs: dict    = {}
    positional: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            key = tok[2:]
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                val = tokens[i + 1]
                if val.lower() == "true":   val = True
                elif val.lower() == "false": val = False
                else:
                    try: val = int(val)
                    except ValueError:
                        try: val = float(val)
                        except ValueError: pass
                kwargs[key] = val
                i += 2
            else:
                kwargs[key] = True
                i += 1
        else:
            positional.append(tok)
            i += 1
    return kwargs, positional


def _handle_help(kwargs: dict) -> str:
    schema = registry.schema()
    if kwargs.get("json"):
        return json.dumps({"ok": True, "data": schema}, ensure_ascii=False)

    lines = [f"AgentShell v{VERSION}", ""]
    for group, cmds in schema.items():
        lines.append(f"  {group}")
        for cmd, info in cmds.items():
            lines.append(f"    {group} {cmd} — {info['description']}")
            for param, pinfo in info["params"].items():
                req = "required" if pinfo["required"] else f"default: {pinfo['default']}"
                lines.append(f"      --{param} ({pinfo['type']}, {req}) {pinfo['description']}")
        lines.append("")
    return "\n".join(lines)


def _get_active_window() -> str:
    try:
        import win32gui
        return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or "unknown"
    except Exception:
        return "unknown"


def _dispatch(line: str) -> str:
    line = line.strip()
    if not line:
        return ""

    try:
        tokens = shlex.split(line)
    except ValueError as e:
        return AgentResponse.failure(f"Parse error: {e}").dump()

    if not tokens:
        return ""

    if tokens[0] == "help":
        kwargs, _ = _parse_args(tokens[1:])
        return _handle_help(kwargs)

    if tokens[0] in ("exit", "quit"):
        if _memory:
            _memory.flush()
        print(AgentResponse.success({"message": "Goodbye."}).dump())
        sys.exit(0)

    if len(tokens) < 2:
        return AgentResponse.failure(
            f"Usage: <group> <command> [--param value]. Groups: {', '.join(registry.groups())}"
        ).dump()

    group, cmd_name = tokens[0], tokens[1]
    kwargs, _       = _parse_args(tokens[2:])

    command = registry.get(group, cmd_name)
    if not command:
        available = registry.commands(group)
        if available:
            return AgentResponse.failure(
                f"Unknown command '{cmd_name}' in '{group}'. Available: {', '.join(available)}"
            ).dump()
        return AgentResponse.failure(
            f"Unknown group '{group}'. Available: {', '.join(registry.groups())}"
        ).dump()

    try:
        result: AgentResponse = command.fn(**kwargs)
    except TypeError as e:
        return AgentResponse.failure(f"Invalid arguments: {e}").dump()
    except Exception as e:
        return AgentResponse.failure(f"Command error: {e}").dump()

    # Auto-update context from state_delta
    if result.ok and result.state_delta:
        try:
            from memory.store import store
            ctx_update: dict = {}
            delta = result.state_delta
            if "last_launched" in delta:
                ctx_update["last_action"] = f"launched {delta['last_launched']}"
                ctx_update["result"]      = "app or URL opened"
            if "active_window" in delta:
                ctx_update["active_window"] = delta["active_window"]
            if "closed_window" in delta or "closed_app" in delta:
                closed = delta.get("closed_window") or delta.get("closed_app")
                ctx_update["last_action"] = f"closed {closed}"
                ctx_update["result"]      = "window or app closed"
            if "volume" in delta:
                ctx_update["last_action"] = f"set volume to {delta['volume']}"
                ctx_update["result"]      = f"volume is now {delta['volume']}"
            if "muted" in delta:
                state = "muted" if delta["muted"] else "unmuted"
                ctx_update["last_action"] = f"{state} audio"
                ctx_update["result"]      = f"audio is {state}"
            if "last_click" in delta:
                c = delta["last_click"]
                ctx_update["last_action"] = f"clicked {c['button']} at ({c['x']}, {c['y']})"
            if ctx_update:
                store.update_context(ctx_update)
        except Exception:
            pass

    # Record to memory
    if _memory and result.ok:
        try:
            window = _get_active_window()
            _memory.record(window=window, action=f"{group} {cmd_name}", source="agent")
        except Exception:
            pass

    return result.dump()


def repl():
    print(f"AgentShell v{VERSION} — type 'help' for commands, 'exit' to quit")
    _init_memory()

    while True:
        try:
            line = input(PROMPT) if sys.stdin.isatty() else sys.stdin.readline()
            if not line:
                break
            line = line.rstrip("\n")
        except (EOFError, KeyboardInterrupt):
            break

        output = _dispatch(line)
        if output:
            print(output)
            sys.stdout.flush()

    if _memory:
        _memory.flush()


def main():
    if len(sys.argv) > 1:
        _init_memory()
        line   = " ".join(sys.argv[1:])
        output = _dispatch(line)
        if output:
            print(output)
        if _memory:
            _memory.flush()
        return

    repl()


if __name__ == "__main__":
    main()