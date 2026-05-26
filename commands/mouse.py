from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam

def _active_window_title() -> str:
    try:
        import win32gui
        return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or "unknown"
    except Exception:
        return "unknown"

def _mouse_response(ok: bool, data: dict = None, error: str = "") -> AgentResponse:
    """
    Wrapper that enriches mouse responses with consistent metadata.
    All mouse commands should use this to return responses.
    """
    if data is None:
        data = {}
    
    meta = {
        "target_window": _active_window_title(),
        "note": "ok:true means click was sent, not that it had effect. Verify with screen find if outcome matters."
                if ok
                else "Click failed before reaching the OS. No action was sent.",
    }
    
    if ok:
        return AgentResponse.success({**data, **meta})
    else:
        return AgentResponse.failure(error, state_delta=meta)

@registry.register(
    group="mouse",
    name="click",
    description="Click at screen coordinates.",
    params=[
        CommandParam("x", "int", True, None, "X coordinate"),
        CommandParam("y", "int", True, None, "Y coordinate"),
        CommandParam("button", "string", False, "left", "Mouse button: 'left', 'right', 'middle'"),
        CommandParam("double", "bool", False, False, "Double click if true"),
    ]
)
def click(x: int, y: int, button: str = "left", double: bool = False) -> AgentResponse:
    try:
        import pyautogui
        if double:
            pyautogui.doubleClick(x, y, button=button)
        else:
            pyautogui.click(x, y, button=button)
        return _mouse_response(True, {"x": x, "y": y, "button": button, "double": double})
    except Exception as e:
        return _mouse_response(False, error=f"Click failed: {e}")


@registry.register(
    group="mouse",
    name="move",
    description="Move mouse to coordinates without clicking.",
    params=[
        CommandParam("x", "int", True, None, "X coordinate"),
        CommandParam("y", "int", True, None, "Y coordinate"),
        CommandParam("duration", "float", False, 0.1, "Movement duration in seconds"),
    ]
)
def move(x: int, y: int, duration: float = 0.1) -> AgentResponse:
    try:
        import pyautogui
        pyautogui.moveTo(x, y, duration=duration)
        return _mouse_response(True, {"x": x, "y": y, "duration": duration})
    except Exception as e:
        return _mouse_response(False, error=f"Move failed: {e}")


@registry.register(
    group="mouse",
    name="scroll",
    description="Scroll at current mouse position or at given coordinates.",
    params=[
        CommandParam("amount", "int", True, None, "Scroll amount. Positive = up, negative = down"),
        CommandParam("x", "int", False, None, "X coordinate (optional, uses current if omitted)"),
        CommandParam("y", "int", False, None, "Y coordinate (optional, uses current if omitted)"),
    ]
)
def scroll(amount: int, x: int | None = None, y: int | None = None) -> AgentResponse:
    try:
        import pyautogui
        if x is not None and y is not None:
            pyautogui.scroll(amount, x=x, y=y)
        else:
            pyautogui.scroll(amount)
        return _mouse_response(True, {"amount": amount, "x": x, "y": y})
    except Exception as e:
        return _mouse_response(False, error=f"Scroll failed: {e}")


@registry.register(
    group="mouse",
    name="drag",
    description="Drag from one coordinate to another.",
    params=[
        CommandParam("x1", "int", True, None, "Start X"),
        CommandParam("y1", "int", True, None, "Start Y"),
        CommandParam("x2", "int", True, None, "End X"),
        CommandParam("y2", "int", True, None, "End Y"),
        CommandParam("duration", "float", False, 0.3, "Drag duration in seconds"),
    ]
)
def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.3) -> AgentResponse:
    try:
        import pyautogui
        pyautogui.drag(x2 - x1, y2 - y1, duration=duration, startX=x1, startY=y1)
        return _mouse_response(True, {"from": [x1, y1], "to": [x2, y2], "duration": duration})
    except Exception as e:
        return _mouse_response(False, error=f"Drag failed: {e}")
