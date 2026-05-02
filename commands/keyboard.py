from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam


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
        return AgentResponse.success({"text": text[:80], "enter": enter})
    except ImportError:
        # Fallback without clipboard
        import pyautogui
        pyautogui.write(text, interval=0.03)
        if enter:
            pyautogui.press("enter")
        return AgentResponse.success({"text": text[:80], "enter": enter})
    except Exception as e:
        return AgentResponse.failure(f"Type failed: {e}")


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
        return AgentResponse.success({"keys": keys})
    except Exception as e:
        return AgentResponse.failure(f"Hotkey failed: {e}")


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
        return AgentResponse.success({"key": key, "times": times})
    except Exception as e:
        return AgentResponse.failure(f"Press failed: {e}")
