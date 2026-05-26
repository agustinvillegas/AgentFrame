from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam


def _active_window_title() -> str:
    try:
        import win32gui
        return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or "unknown"
    except Exception:
        return "unknown"


def _keyboard_response(ok: bool, data: dict = None, error: str = "") -> AgentResponse:
    """
    Wrapper that enriches keyboard responses with consistent metadata.
    All keyboard commands should use this to return responses.
    """
    if data is None:
        data = {}
    
    meta = {
        "target_window": _active_window_title(),
        "note": "ok:true means command was sent, not that it had effect. Verify with screen find if outcome matters."
                if ok
                else "Command failed before reaching the OS. No keypress was sent.",
    }
    
    if ok:
        return AgentResponse.success({**data, **meta})
    else:
        return AgentResponse.failure(error, state_delta=meta)

@registry.register(
    group="keyboard",
    name="type",
    description="Type text at the current cursor position. Uses clipboard for reliability.",
    params=[
        CommandParam("text", "string", True, None, "Text to type"),
        CommandParam("enter", "bool", False, False, "Press Enter after typing"),
    ]
)
def type_text(text: str, enter: bool = False) -> AgentResponse:
    try:
        import pyperclip
        import pyautogui
        import time
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        if enter:
            time.sleep(0.05)
            pyautogui.press("enter")
        return _keyboard_response(True, {"text": text[:80], "enter": enter})

    except ImportError:
        # Fallback without clipboard
        import pyautogui
        pyautogui.write(text, interval=0.03)
        if enter:
            pyautogui.press("enter")
        return _keyboard_response(True, {"text": text[:80], "enter": enter})

    except Exception as e:
        return _keyboard_response(False, error=f"Type failed: {e}")


@registry.register(
    group="keyboard",
    name="hotkey",
    description="Press a keyboard shortcut.",
    params=[
        CommandParam("keys", "string", True, None, "Keys separated by '+'. Example: 'ctrl+c', 'win+d', 'alt+f4'"),
    ]
)
def hotkey(keys: str) -> AgentResponse:
    try:
        import pyautogui
        parts = [k.strip() for k in keys.split("+")]
        pyautogui.hotkey(*parts)
        return _keyboard_response(True, {"keys": keys})
    except Exception as e:
        return _keyboard_response(False, error=f"Hotkey failed: {e}")


@registry.register(
    group="keyboard",
    name="press",
    description="Press a single key.",
    params=[
        CommandParam("key", "string", True, None, "Key name. Examples: 'enter', 'escape', 'f5', 'tab', 'space', 'backspace'"),
        CommandParam("times", "int", False, 1, "Number of times to press"),
    ]
)
def press(key: str, times: int = 1) -> AgentResponse:
    try:
        import pyautogui
        for _ in range(times):
            pyautogui.press(key)
        return _keyboard_response(True, {"key": key, "times": times})
    except Exception as e:
        return _keyboard_response(False, error=f"Press failed: {e}")


