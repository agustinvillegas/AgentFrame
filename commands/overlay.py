from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam
from core.overlay import overlay


@registry.register(
    group="overlay",
    name="notify",
    description="Show a floating notification on screen.",
    params=[
        CommandParam("message",  "string", True,  None, "Notification text"),
        CommandParam("duration", "int",    False, 3,    "Seconds before it disappears"),
    ]
)
def notify(message: str, duration: int = 3) -> AgentResponse:
    try:
        overlay.send("notify", message=message, duration=duration)
        return AgentResponse.success({"message": message, "duration": duration})
    except Exception as e:
        return AgentResponse.failure(f"Notify failed: {e}")


@registry.register(
    group="overlay",
    name="status",
    description="Show or hide a status indicator at the top of the screen.",
    params=[
        CommandParam("message", "string", False, None, "Status text to show. Omit to hide."),
    ]
)
def status(message: str | None = None) -> AgentResponse:
    try:
        overlay.send("status", message=message)
        return AgentResponse.success({"visible": message is not None, "message": message})
    except Exception as e:
        return AgentResponse.failure(f"Status failed: {e}")


@registry.register(
    group="overlay",
    name="confirm",
    description="Show a Yes/No confirmation dialog. Blocks until user responds.",
    params=[
        CommandParam("message", "string", True, None, "Question to ask the user"),
    ]
)
def confirm(message: str) -> AgentResponse:
    try:
        result = overlay.confirm(message)
        return AgentResponse.success({"confirmed": result, "message": message})
    except Exception as e:
        return AgentResponse.failure(f"Confirm failed: {e}")


@registry.register(
    group="overlay",
    name="chat",
    description="Add a message to the floating chat window, or clear it.",
    params=[
        CommandParam("message", "string", False, None,    "Message to add"),
        CommandParam("sender",  "string", False, "agent", "'agent' or 'user'"),
        CommandParam("clear",   "bool",   False, False,   "Clear all messages if true"),
    ]
)
def chat(message: str | None = None, sender: str = "agent", clear: bool = False) -> AgentResponse:
    try:
        if clear:
            overlay.send("chat", clear=True)
            return AgentResponse.success({"cleared": True})
        if not message:
            return AgentResponse.failure("Provide --message or --clear true.")
        overlay.send("chat", message=message, sender=sender)
        return AgentResponse.success({"message": message, "sender": sender})
    except Exception as e:
        return AgentResponse.failure(f"Chat failed: {e}")