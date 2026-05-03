from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam


@registry.register(
    group="window",
    name="list",
    description="List all visible windows with their titles.",
    params=[]
)
def list_windows() -> AgentResponse:
    try:
        import win32gui

        windows = []
        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.strip():
                    windows.append({"hwnd": hwnd, "title": title})

        win32gui.EnumWindows(_cb, None)
        return AgentResponse.success({"windows": windows, "count": len(windows)})
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Window list failed: {e}")


@registry.register(
    group="window",
    name="focus",
    description="Bring a window to focus by partial title match.",
    params=[
        CommandParam("title", "string", True, None, "Partial window title to match (case-insensitive)"),
    ]
)
def focus(title: str) -> AgentResponse:
    try:
        import win32gui
        import win32con

        target = None
        def _cb(hwnd, _):
            nonlocal target
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if title.lower() in t.lower():
                    target = (hwnd, t)

        win32gui.EnumWindows(_cb, None)

        if not target:
            return AgentResponse.failure(f"No window matching '{title}' found.")

        hwnd, matched_title = target
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return AgentResponse.success(
            {"focused": matched_title},
            state_delta={"active_window": matched_title}
        )
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Focus failed: {e}")


@registry.register(
    group="window",
    name="minimize",
    description="Minimize a window by partial title match, or the active window if no title given.",
    params=[
        CommandParam("title", "string", False, None, "Partial window title. Omit for active window."),
    ]
)
def minimize(title: str | None = None) -> AgentResponse:
    try:
        import win32gui
        import win32con

        if title:
            hwnd = _find_window(title)
            if not hwnd:
                return AgentResponse.failure(f"No window matching '{title}' found.")
        else:
            hwnd = win32gui.GetForegroundWindow()

        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        return AgentResponse.success({"minimized": win32gui.GetWindowText(hwnd)})
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Minimize failed: {e}")


@registry.register(
    group="window",
    name="close",
    description="Close a window by partial title match.",
    params=[
        CommandParam("title", "string", True, None, "Partial window title to match (case-insensitive)"),
    ]
)
def close(title: str) -> AgentResponse:
    try:
        import win32gui
        import win32con

        hwnd = _find_window(title)
        if not hwnd:
            return AgentResponse.failure(f"No window matching '{title}' found.")

        matched_title = win32gui.GetWindowText(hwnd)
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return AgentResponse.success(
            {"closed": matched_title},
            state_delta={"closed_window": matched_title}
        )
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Close failed: {e}")


def _find_window(title: str) -> int | None:
    import win32gui
    result = None
    def _cb(hwnd, _):
        nonlocal result
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if title.lower() in t.lower():
                result = hwnd
    win32gui.EnumWindows(_cb, None)
    return result

@registry.register(
    group="window",
    name="resize",
    description="Resize a window by partial title match, or the active window if no title given.",
    params=[
        CommandParam("width",  "int",    True,  None, "New width in pixels"),
        CommandParam("height", "int",    True,  None, "New height in pixels"),
        CommandParam("title",  "string", False, None, "Partial window title. Omit for active window."),
    ]
)
def resize(width: int, height: int, title: str | None = None) -> AgentResponse:
    try:
        import win32gui
        import win32con

        if title:
            hwnd = _find_window(title)
            if not hwnd:
                return AgentResponse.failure(f"No window matching '{title}' found.")
        else:
            hwnd = win32gui.GetForegroundWindow()

        left, top, _, _ = win32gui.GetWindowRect(hwnd)
        win32gui.MoveWindow(hwnd, left, top, width, height, True)

        return AgentResponse.success(
            {"title": win32gui.GetWindowText(hwnd), "width": width, "height": height},
            state_delta={"last_action": f"resized window to {width}x{height}", "result": "window resized"}
        )
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Resize failed: {e}")


@registry.register(
    group="window",
    name="move",
    description="Move a window to specific coordinates, or the active window if no title given.",
    params=[
        CommandParam("x",     "int",    True,  None, "Left edge position in pixels"),
        CommandParam("y",     "int",    True,  None, "Top edge position in pixels"),
        CommandParam("title", "string", False, None, "Partial window title. Omit for active window."),
    ]
)
def move(x: int, y: int, title: str | None = None) -> AgentResponse:
    try:
        import win32gui

        if title:
            hwnd = _find_window(title)
            if not hwnd:
                return AgentResponse.failure(f"No window matching '{title}' found.")
        else:
            hwnd = win32gui.GetForegroundWindow()

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width  = right  - left
        height = bottom - top

        win32gui.MoveWindow(hwnd, x, y, width, height, True)

        return AgentResponse.success(
            {"title": win32gui.GetWindowText(hwnd), "x": x, "y": y},
            state_delta={"last_action": f"moved window to ({x}, {y})", "result": "window moved"}
        )
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Move failed: {e}")


@registry.register(
    group="window",
    name="snap",
    description="Snap a window to a screen position using Windows shortcuts.",
    params=[
        CommandParam("position", "string", True,  None, "'left' | 'right' | 'maximize' | 'restore'"),
        CommandParam("title",    "string", False, None, "Partial window title. Omit for active window."),
    ]
)
def snap(position: str, title: str | None = None) -> AgentResponse:
    try:
        import win32gui
        import win32con
        import pyautogui

        POSITIONS = {"left", "right", "maximize", "restore"}
        if position not in POSITIONS:
            return AgentResponse.failure(f"Invalid position '{position}'. Use: {', '.join(POSITIONS)}")

        if title:
            hwnd = _find_window(title)
            if not hwnd:
                return AgentResponse.failure(f"No window matching '{title}' found.")
            win32gui.SetForegroundWindow(hwnd)

        hotkeys = {
            "left":     ["win", "left"],
            "right":    ["win", "right"],
            "maximize": ["win", "up"],
            "restore":  ["win", "down"],
        }

        pyautogui.hotkey(*hotkeys[position])

        return AgentResponse.success(
            {"position": position},
            state_delta={"last_action": f"snapped window {position}", "result": f"window snapped to {position}"}
        )
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Snap failed: {e}")


@registry.register(
    group="window",
    name="info",
    description="Get detailed info about a window: title, position, size, process, PID.",
    params=[
        CommandParam("title", "string", False, None, "Partial window title. Omit for active window."),
    ]
)
def info(title: str | None = None) -> AgentResponse:
    try:
        import win32gui
        import win32process
        import psutil

        if title:
            hwnd = _find_window(title)
            if not hwnd:
                return AgentResponse.failure(f"No window matching '{title}' found.")
        else:
            hwnd = win32gui.GetForegroundWindow()

        window_title         = win32gui.GetWindowText(hwnd)
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        _, pid               = win32process.GetWindowThreadProcessId(hwnd)

        process_name = None
        try:
            process_name = psutil.Process(pid).name()
        except Exception:
            pass

        return AgentResponse.success({
            "title":   window_title,
            "hwnd":    hwnd,
            "pid":     pid,
            "process": process_name,
            "x":       left,
            "y":       top,
            "width":   right  - left,
            "height":  bottom - top,
            "bounds":  {"left": left, "top": top, "right": right, "bottom": bottom},
        })
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Info failed: {e}")
    