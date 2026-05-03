from __future__ import annotations
import subprocess
import webbrowser
from core.response import AgentResponse
from core.registry import registry, CommandParam
import os
import winreg
from pathlib import Path


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
    "brave": "brave.exe",
}


@registry.register(
    group="app",
    name="launch",
    description="Launch an application or open a URL. Accepts app names, executable names, or URLs.",
    params=[
        CommandParam("name", "string", True, None, "App name, executable, or URL. Examples: 'chrome', 'brave', 'notepad', 'https://example.com'"),
    ]
)
def launch(name: str) -> AgentResponse:
    try:
        target = name.strip()

        # URLs
        if target.startswith("http://") or target.startswith("https://"):
            webbrowser.open(target)
            return AgentResponse.success(
                {"launched": target, "type": "url"},
                state_delta={"last_launched": target}
            )

        # Alias directo a URL
        alias = _APP_ALIASES.get(target.lower())
        if alias and (alias.startswith("http://") or alias.startswith("https://")):
            webbrowser.open(alias)
            return AgentResponse.success(
                {"launched": alias, "type": "url"},
                state_delta={"last_launched": alias}
            )

        # Buscar ejecutable
        resolved = _resolve_executable(target)

        if resolved:
            subprocess.Popen(
                [resolved],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return AgentResponse.success(
                {"launched": resolved, "type": "app"},
                state_delta={"last_launched": resolved}
            )

        # Último recurso — start menu
        _launch_via_start_menu(target)
        return AgentResponse.success(
            {"launched": target, "type": "start_menu", "note": "Launched via Start Menu — verify app opened."},
            state_delta={"last_launched": target}
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

@registry.register(
    group="app",
    name="focus",
    description="Bring an application to the foreground by process name.",
    params=[
        CommandParam("name", "string", True, None, "Process name (e.g. 'brave.exe', 'code.exe')"),
    ]
)
def focus(name: str) -> AgentResponse:
    try:
        import psutil
        import win32gui
        import win32con

        name_lower = name.lower().replace(".exe", "")

        
        target_pid = None
        for proc in psutil.process_iter(["pid", "name"]):
            proc_name = (proc.info["name"] or "").lower().replace(".exe", "")
            if name_lower in proc_name:
                target_pid = proc.info["pid"]
                break

        if not target_pid:
            return AgentResponse.failure(f"No running process matching '{name}' found.")

        # Buscar la ventana principal del proceso
        target_hwnd = None
        def _cb(hwnd, _):
            nonlocal target_hwnd
            if not win32gui.IsWindowVisible(hwnd):
                return
            if not win32gui.GetWindowText(hwnd):
                return
            import win32process
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == target_pid:
                target_hwnd = hwnd

        win32gui.EnumWindows(_cb, None)

        if not target_hwnd:
            return AgentResponse.failure(f"Process '{name}' is running but has no visible window.")

        win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(target_hwnd)
        title = win32gui.GetWindowText(target_hwnd)

        return AgentResponse.success(
            {"focused": title, "pid": target_pid},
            state_delta={"active_window": title, "last_action": f"focused {name}", "result": "app brought to foreground"}
        )

    except ImportError:
        return AgentResponse.failure("pywin32 or psutil not installed.")
    except Exception as e:
        return AgentResponse.failure(f"Focus failed: {e}")
    

def _resolve_executable(name: str) -> str | None:
    alias = _APP_ALIASES.get(name.lower().strip())
    if alias:
        if alias.startswith("http://") or alias.startswith("https://"):
            return alias
        name = alias

    # 2. Si ya es una ruta válida
    p = Path(name)
    if p.exists():
        return str(p)

    search_name = name if name.endswith(".exe") else name + ".exe"

    # 3. Program Files con límite de profundidad
    def _search_dir(base: str, filename: str, max_depth: int = 4) -> str | None:
        base_path = Path(base)
        if not base_path.exists():
            return None
        for dirpath, dirs, files in os.walk(base_path):
            depth = len(Path(dirpath).relative_to(base_path).parts)
            if depth >= max_depth:
                dirs.clear()
                continue
            for f in files:
                if f.lower() == filename.lower():
                    return str(Path(dirpath) / f)
        return None

    search_dirs = [
        os.environ.get("ProgramFiles",      r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA",      ""),
        os.environ.get("APPDATA",           ""),
    ]
    for base in search_dirs:
        if not base:
            continue
        result = _search_dir(base, search_name)
        if result:
            return result

    # 4. Registro de Windows
    key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{search_name}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "")
            if value and Path(value).exists():
                return value
    except Exception:
        pass

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "")
            if value and Path(value).exists():
                return value
    except Exception:
        pass

    # 5. PATH del sistema
    import shutil
    found = shutil.which(search_name) or shutil.which(name)
    if found:
        return found

    return None


def _launch_via_start_menu(name: str) -> bool:
    """Último recurso — Win, escribir, Enter."""
    try:
        import pyautogui
        import time
        pyautogui.press("win")
        time.sleep(0.8)
        pyautogui.write(name, interval=0.05)
        time.sleep(1.0)
        pyautogui.press("enter")
        return True
    except Exception:
        return False