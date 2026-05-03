from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam


@registry.register(
    group="notify",
    name="send",
    description="Send a Windows toast notification to the user.",
    params=[
        CommandParam("title",   "string", True,  None,    "Notification title"),
        CommandParam("message", "string", True,  None,    "Notification body text"),
        CommandParam("duration","string", False, "short", "'short' (5s) or 'long' (25s)"),
    ]
)
def send(title: str, message: str, duration: str = "short") -> AgentResponse:
    try:
        from windows_toasts import Toast, WindowsToaster, ToastDuration

        toaster  = WindowsToaster("AgentShell")
        toast    = Toast()
        toast.text_fields = [title, message]
        toast.duration    = ToastDuration.Short if duration == "short" else ToastDuration.Long

        toaster.show_toast(toast)

        return AgentResponse.success({
            "sent":     True,
            "title":    title,
            "message":  message,
            "duration": duration,
        })
    except ImportError:
        return AgentResponse.failure(
            "windows-toasts not installed. Run: pip install windows-toasts"
        )
    except Exception as e:
        return AgentResponse.failure(f"Notification failed: {e}")