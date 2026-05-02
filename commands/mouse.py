from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam


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
        return AgentResponse.success(
            {"x": x, "y": y, "button": button, "double": double},
            state_delta={"last_click": {"x": x, "y": y, "button": button}}
        )
    except Exception as e:
        return AgentResponse.failure(f"Click failed: {e}")


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
        return AgentResponse.success({"x": x, "y": y})
    except Exception as e:
        return AgentResponse.failure(f"Move failed: {e}")


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
        return AgentResponse.success({"amount": amount, "x": x, "y": y})
    except Exception as e:
        return AgentResponse.failure(f"Scroll failed: {e}")


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
        return AgentResponse.success({"from": [x1, y1], "to": [x2, y2]})
    except Exception as e:
        return AgentResponse.failure(f"Drag failed: {e}")
