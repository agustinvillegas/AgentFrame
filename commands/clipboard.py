from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam


@registry.register(
    group="clipboard",
    name="read",
    description="Read the current clipboard content.",
    params=[]
)
def read() -> AgentResponse:
    try:
        import pyperclip
        content = pyperclip.paste()
        return AgentResponse.success({
            "content": content,
            "length":  len(content),
            "empty":   not bool(content.strip()),
        })
    except ImportError:
        return AgentResponse.failure("pyperclip not installed. Run: pip install pyperclip")
    except Exception as e:
        return AgentResponse.failure(f"Clipboard read failed: {e}")


@registry.register(
    group="clipboard",
    name="write",
    description="Write text to the clipboard.",
    params=[
        CommandParam("text", "string", True, None, "Text to copy to clipboard"),
    ]
)
def write(text: str) -> AgentResponse:
    try:
        import pyperclip
        pyperclip.copy(text)
        return AgentResponse.success(
            {"written": len(text)},
            state_delta={"last_action": "wrote to clipboard", "result": f"{len(text)} chars in clipboard"}
        )
    except ImportError:
        return AgentResponse.failure("pyperclip not installed. Run: pip install pyperclip")
    except Exception as e:
        return AgentResponse.failure(f"Clipboard write failed: {e}")