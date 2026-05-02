from __future__ import annotations
import base64
import io
from core.response import AgentResponse
from core.registry import registry, CommandParam


@registry.register(
    group="screen",
    name="capture",
    description=(
        "Capture a screenshot. Returns base64 PNG. "
        "Use 'active' to capture only the active window (faster, less tokens). "
        "Use 'full' for the full desktop."
    ),
    params=[
        CommandParam("region", "string", False, "active", "'active' (active window only) or 'full' (full desktop)"),
    ]
)
def capture(region: str = "active") -> AgentResponse:
    try:
        import pyautogui

        if region == "active":
            img = _capture_active_window()
        else:
            img = pyautogui.screenshot()

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        return AgentResponse.success({
            "image_b64": b64,
            "format":    "png",
            "width":     img.width,
            "height":    img.height,
            "region":    region,
        })
    except Exception as e:
        return AgentResponse.failure(f"Screen capture failed: {e}")


@registry.register(
    group="screen",
    name="elements",
    description=(
        "Get UI elements in the active window via Accessibility Tree. "
        "Faster and cheaper than capture — use this first. "
        "Check 'complete' in the response: if false, the tree was partial "
        "and you may want to call screen capture as well."
    ),
    params=[
        CommandParam("filter", "string", False, None, "Filter by type: 'button' | 'edit' | 'text' | 'link' | 'checkbox' | 'list' | 'menu'. Omit for all."),
        CommandParam("enabled_only", "bool", False, False, "If true, return only interactable (enabled) elements."),
    ]
)
def elements(filter: str | None = None, enabled_only: bool = False) -> AgentResponse:
    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")

        try:
            active = desktop.active()
        except Exception:
            return AgentResponse.failure("Could not access active window.")

        if not active:
            return AgentResponse.failure("No active window found.")

        window_title = ""
        try:
            window_title = active.element_info.name or ""
        except Exception:
            pass

        raw_elements = []
        complete = True

        try:
            descendants = active.descendants()
        except Exception as e:
            return AgentResponse.success({
                "elements": [],
                "count":    0,
                "window":   window_title,
                "complete": False,
                "note":     f"Accessibility Tree unavailable for this window: {e}",
            })

        for ctrl in descendants:
            try:
                info      = ctrl.element_info
                ctrl_type = (info.control_type or "").lower()
                label     = info.name or ""
                rect      = info.rectangle
                enabled   = info.enabled

                if not ctrl_type:
                    continue
                if enabled_only and not enabled:
                    continue
                if filter and ctrl_type != filter.lower():
                    continue

                element: dict = {
                    "type":    ctrl_type,
                    "label":   label,
                    "enabled": enabled,
                }

                if rect:
                    element["bounds"] = {
                        "left":   rect.left,
                        "top":    rect.top,
                        "right":  rect.right,
                        "bottom": rect.bottom,
                        "center": [
                            (rect.left + rect.right) // 2,
                            (rect.top + rect.bottom) // 2,
                        ],
                    }

                try:
                    val = ctrl.get_value()
                    if val:
                        element["value"] = str(val)[:200]
                except Exception:
                    pass

                raw_elements.append(element)

            except Exception:
                complete = False
                continue

        # Deduplicate: same type + label + approximate position
        seen = set()
        elements_out = []
        for el in raw_elements:
            center = el.get("bounds", {}).get("center", [0, 0])
            key = (el["type"], el["label"], center[0] // 5, center[1] // 5)
            if key not in seen:
                seen.add(key)
                elements_out.append(el)

        note = None
        if not complete:
            note = "Some elements could not be read. Tree may be partial."
        if not elements_out and not filter:
            note = "No elements found. App may not expose Accessibility Tree — try screen capture."
            complete = False

        result: dict = {
            "elements": elements_out,
            "count":    len(elements_out),
            "window":   window_title,
            "complete": complete,
        }
        if note:
            result["note"] = note

        return AgentResponse.success(result)

    except ImportError:
        return AgentResponse.failure("pywinauto not installed. Run: pip install pywinauto")
    except Exception as e:
        return AgentResponse.failure(f"Elements fetch failed: {e}")


@registry.register(
    group="screen",
    name="active",
    description="Get the title and bounds of the currently active window.",
    params=[]
)
def active_window() -> AgentResponse:
    try:
        import win32gui
        hwnd  = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)

        return AgentResponse.success({
            "title":  title,
            "hwnd":   hwnd,
            "bounds": {"left": left, "top": top, "right": right, "bottom": bottom},
            "width":  right - left,
            "height": bottom - top,
        })
    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Active window query failed: {e}")


def _capture_active_window():
    """Capture only the bounding box of the active window."""
    import pyautogui
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return pyautogui.screenshot(region=(left, top, right - left, bottom - top))
    except ImportError:
        return pyautogui.screenshot()
