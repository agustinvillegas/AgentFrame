"""
AgentShell — Terminal chat with the agent (no frontend needed).

Usage:
  python agent_chat.py                    # Start backend + listener + chat
  python agent_chat.py --url http://...   # Connect to running backend
"""
from __future__ import annotations

import json, os, subprocess, sys, time, shlex
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

BASE = Path(__file__).resolve().parent

class C:
    BOLD = "\033[1m"
    RED  = "\033[91m"
    GRN  = "\033[92m"
    YEL  = "\033[93m"
    BLU  = "\033[94m"
    CYN  = "\033[96m"
    END  = "\033[0m"

BACKEND_URL = "http://127.0.0.1:5000"


def _log(tag, msg, color=C.CYN):
    print(f"{color}[{tag}]{C.END} {msg}")


def _load_groq_key() -> str | None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        cfg = BASE / "config" / "api_keys.json"
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text("utf-8"))
                key = data.get("groq_api_key")
            except Exception:
                pass
    return key


def _launch_listener():
    candidates = [
        BASE / "listener" / "bin" / "Release" / "net8.0-windows"
            / "win-x64" / "publish" / "AgentShellListener.exe",
        BASE / "listener" / "bin" / "Debug"
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
                _log("LISTENER", f"Launched: {exe.name}", C.GRN)
                return True
            except Exception as e:
                _log("LISTENER", str(e), C.RED)
                return False
    _log("LISTENER", "exe not found (run 'dotnet publish' in listener/)", C.YEL)
    return False


def _start_backend() -> subprocess.Popen | None:
    _log("BACKEND", "Starting FastAPI on http://127.0.0.1:5000 ...")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app",
             "--host", "127.0.0.1", "--port", "5000",
             "--log-level", "warning"],
            cwd=BASE / "backend",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log("BACKEND", f"PID {proc.pid}", C.GRN)
        return proc
    except Exception as e:
        _log("BACKEND", str(e), C.RED)
        return None


def _wait_for_backend(timeout=15):
    _log("BACKEND", "Waiting for API to be ready...", C.YEL)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{BACKEND_URL}/health", timeout=2)
            if r.ok:
                _log("BACKEND", "Ready!", C.GRN)
                return True
        except Exception:
            pass
        time.sleep(0.5)
    _log("BACKEND", f"Not ready after {timeout}s", C.RED)
    return False


def _colorize(text: str) -> str:
    """Highlight commands in output."""
    text = text.replace("BEGIN_COMMAND", f"{C.GRN}BEGIN_COMMAND{C.END}")
    text = text.replace("END_COMMAND", f"{C.GRN}END_COMMAND{C.END}")
    return text


def chat_loop(url: str):
    api_key = _load_groq_key()
    if not api_key:
        print(f"{C.RED}No GROQ_API_KEY found. Set env var or add to config/api_keys.json{C.END}")
        return

    # Init agent
    _log("INIT", "Initializing agent...", C.CYN)
    try:
        r = requests.post(f"{url}/init", json={"api_key": api_key}, timeout=10)
        r.raise_for_status()
        data = r.json()
        _log("INIT", f"Agent initialized", C.GRN)
        if data.get("compact"):
            print(f"  Commands available: {len(data['compact'].split(chr(10)))}")
    except Exception as e:
        _log("INIT", f"Failed: {e}", C.RED)
        return

    print()
    print(f"{C.BOLD}{C.BLU}╔══════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}{C.BLU}║   AgentShell — Terminal Chat         ║{C.END}")
    print(f"{C.BOLD}{C.BLU}║   Model: qwen/qwen3-32b (Groq)      ║{C.END}")
    print(f"{C.BOLD}{C.BLU}║   Vision: Florence-2-base (local)   ║{C.END}")
    print(f"{C.BOLD}{C.BLU}╚══════════════════════════════════════╝{C.END}")
    print(f"{C.YEL}Type your message, or /clear, /step, /auto, /exit{C.END}\n")

    mode = "auto"
    max_steps = 10

    while True:
        try:
            user = input(f"{C.BOLD}{C.BLU}»{C.END} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user:
            continue

        if user == "/exit":
            break
        if user == "/clear":
            requests.post(f"{url}/clear")
            print(f"{C.YEL}Context cleared.{C.END}")
            continue
        if user == "/step":
            mode = "step"
            print(f"{C.YEL}Mode: step{C.END}")
            continue
        if user == "/auto":
            mode = "auto"
            print(f"{C.YEL}Mode: auto{C.END}")
            continue

        # Send message
        try:
            r = requests.post(
                f"{url}/message",
                json={"message": user, "mode": mode, "max_steps": max_steps},
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"{C.RED}Error: {e}{C.END}")
            continue

        reply = data.get("agent_reply", "")
        cmd = data.get("command_executed")
        cmd_result = data.get("command_result")
        err = data.get("error")

        print()
        if reply:
            print(_colorize(reply))
        if cmd:
            print(f"{C.GRN}  ⤷ {cmd}{C.END}")
        if cmd_result:
            ok = cmd_result.get("ok")
            status = f"{C.GRN}✓{C.END}" if ok else f"{C.RED}✗{C.END}"
            brief = json.dumps(cmd_result.get("data", cmd_result), ensure_ascii=False)
            if len(brief) > 200:
                brief = brief[:200] + "..."
            print(f"  {status} {brief}")
        if err:
            print(f"{C.RED}  Error: {err}{C.END}")
        print()


def main():
    if "--url" in sys.argv:
        idx = sys.argv.index("--url")
        url = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else BACKEND_URL
        chat_loop(url)
        return 0

    # Start everything
    _launch_listener()
    time.sleep(0.3)

    backend = _start_backend()
    if not backend:
        return 1

    if not _wait_for_backend():
        backend.kill()
        return 1

    chat_loop(BACKEND_URL)

    # Cleanup
    _log("SHUTDOWN", "Stopping backend...", C.YEL)
    backend.terminate()
    try:
        backend.wait(timeout=5)
    except subprocess.TimeoutExpired:
        backend.kill()
    _log("SHUTDOWN", "Done.", C.GRN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
