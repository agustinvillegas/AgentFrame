from __future__ import annotations
import subprocess
import webbrowser
from core.response import AgentResponse
from core.registry import registry, CommandParam


_APP_ALIASES: dict[str, str] = {
    # Browsers
    "chrome":        "chrome.exe",
    "firefox":       "firefox.exe",
    "edge":          "msedge.exe",
    # Editors
    "notepad":       "notepad.exe",
    "vscode":        "code.exe",
    "code":          "code.exe",
    # System
    "explorer":      "explorer.exe",
    "calculator":    "calc.exe",
    "taskmgr":       "taskmgr.exe",
    "task manager":  "taskmgr.exe",
    "cmd":           "cmd.exe",
    "powershell":    "powershell.exe",
    "terminal":      "wt.exe",
    # URLs
    "youtube":       "https://www.youtube.com",
    "gmail":         "https://mail.google.com",
    "github":        "https://github.com",
    "google":        "https://www.google.com",
    "maps":          "https://maps.google.com",
    "spotify":       "https://open.spotify.com",
}


@registry.register(
    group="app",
    name="launch",
    description="Launch an application or open a URL. Accepts app names, executable names, or URLs.",
    params=[
        CommandParam("name", "string", True, None, "App name, executable, or URL. Examples: 'chrome', 'notepad', 'youtube', 'https://example.com'"),
    ]
)
def launch(name: str) -> AgentResponse:
    try:
        target = _APP_ALIASES.get(name.lower().strip(), name)

        if target.startswith("http://") or target.startswith("https://"):
            webbrowser.open(target)
            return AgentResponse.success(
                {"launched": target, "type": "url"},
                state_delta={"last_launched": target}
            )

        subprocess.Popen(
            [target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return AgentResponse.success(
            {"launched": target, "type": "app"},
            state_delta={"last_launched": target}
        )

    except FileNotFoundError:
        return AgentResponse.failure(
            f"'{name}' not found. Check the name or provide full path."
        )
    except Exception as e:
        return AgentResponse.failure(f"Launch failed: {e}")


@registry.register(
    group="app",
    name="close",
    description="Close a running application by process name or partial window title.",
    params=[
        CommandParam("name", "string", True, None, "Process name (e.g. 'chrome.exe') or partial window title (e.g. 'Chrome')"),
    ]
)
def close(name: str) -> AgentResponse:
    try:
        import psutil

        killed = []
        name_lower = name.lower().replace(".exe", "")

        for proc in psutil.process_iter(["pid", "name"]):
            proc_name = (proc.info["name"] or "").lower().replace(".exe", "")
            if name_lower in proc_name:
                proc.terminate()
                killed.append(proc.info["name"])

        if killed:
            return AgentResponse.success(
                {"closed": killed},
                state_delta={"closed_app": killed[0]}
            )

        # Fallback: close by window title
        try:
            import win32gui, win32con

            hwnd_list = []
            def _cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if name.lower() in title.lower():
                        hwnd_list.append((hwnd, title))
            win32gui.EnumWindows(_cb, None)

            if hwnd_list:
                for hwnd, title in hwnd_list:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                return AgentResponse.success(
                    {"closed": [t for _, t in hwnd_list]},
                    state_delta={"closed_app": hwnd_list[0][1]}
                )
        except ImportError:
            pass

        return AgentResponse.failure(f"No process or window matching '{name}' found.")

    except ImportError:
        return AgentResponse.failure("psutil not installed. Run: pip install psutil")
    except Exception as e:
        return AgentResponse.failure(f"Close failed: {e}")


@registry.register(
    group="app",
    name="list",
    description="List all running processes with their names and PIDs.",
    params=[
        CommandParam("filter", "string", False, None, "Optional filter string to match process names"),
    ]
)
def list_apps(filter: str | None = None) -> AgentResponse:
    try:
        import psutil

        procs = []
        seen = set()
        for proc in psutil.process_iter(["pid", "name"]):
            name = proc.info["name"] or ""
            if not name or name in seen:
                continue
            if filter and filter.lower() not in name.lower():
                continue
            seen.add(name)
            procs.append({"pid": proc.info["pid"], "name": name})

        procs.sort(key=lambda x: x["name"].lower())
        return AgentResponse.success({"processes": procs, "count": len(procs)})

    except ImportError:
        return AgentResponse.failure("psutil not installed. Run: pip install psutil")
    except Exception as e:
        return AgentResponse.failure(f"List failed: {e}")
