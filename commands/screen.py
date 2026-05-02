from __future__ import annotations
import base64
import io
from core.response import AgentResponse
from core.registry import registry, CommandParam
import threading

_ocr_reader = None
_ocr_lock   = threading.Lock()

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
            label = el.get("label", "").strip()
            bounds = el.get("bounds", {})
    
            if label:
                # Elementos con label: deduplicar por tipo + texto
                key = (el["type"], label)
            else:
            # Elementos sin label: usar posición exacta
                key = (el["type"], bounds.get("left"), bounds.get("top"))
    
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
            
        if not complete:
            ocr = _ocr_active_window()
            result["ocr"] = ocr
            result["note"] = (
                "Accessibility Tree incomplete. OCR description attached. "
                "Request 'screen capture' only if OCR is insufficient for your task."
            )

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
    """Captura la ventana activa independientemente del monitor en que esté."""
    import pyautogui
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)

        # GetWindowRect devuelve coordenadas virtuales del escritorio
        # que son correctas para capturas multi-monitor con pyautogui
        width  = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            return pyautogui.screenshot()

        return pyautogui.screenshot(region=(left, top, width, height))
    except ImportError:
        return pyautogui.screenshot()


@registry.register(
    group="screen",
    name="region",
    description=(
        "Capture a specific region of the screen by coordinates. "
        "Use when you need a specific area, not the full desktop or active window."
    ),
    params=[
        CommandParam("x",      "int", True, None, "Left edge of region"),
        CommandParam("y",      "int", True, None, "Top edge of region"),
        CommandParam("width",  "int", True, None, "Width of region in pixels"),
        CommandParam("height", "int", True, None, "Height of region in pixels"),
    ]
)
def region(x: int, y: int, width: int, height: int) -> AgentResponse:
    try:
        import pyautogui

        if width <= 0 or height <= 0:
            return AgentResponse.failure("Width and height must be greater than 0.")

        img = pyautogui.screenshot(region=(x, y, width, height))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        return AgentResponse.success({
            "image_b64": b64,
            "format":    "png",
            "x":         x,
            "y":         y,
            "width":     img.width,
            "height":    img.height,
        })
    except Exception as e:
        return AgentResponse.failure(f"Region capture failed: {e}")
    
def _get_ocr_reader():
    """Lazy init — easyocr descarga modelos la primera vez, no querés hacerlo en import."""
    global _ocr_reader
    if _ocr_reader is None:
        with _ocr_lock:
            if _ocr_reader is None:
                import easyocr
                _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _ocr_reader


def _ocr_active_window() -> dict:
    """
    Captura la ventana activa y corre OCR sobre ella.
    Devuelve texto estructurado con posición y confianza.
    """
    try:
        import pyautogui
        import numpy as np

        # Captura la ventana activa como array numpy
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width  = right - left
            height = bottom - top
            if width > 0 and height > 0:
                img = pyautogui.screenshot(region=(left, top, width, height))
            else:
                img = pyautogui.screenshot()
        except Exception:
            img = pyautogui.screenshot()

        img_np  = np.array(img)
        reader  = _get_ocr_reader()
        results = reader.readtext(img_np)

        # Filtramos resultados con confianza baja
        MIN_CONFIDENCE = 0.4
        texts = []
        for bbox, text, confidence in results:
            if confidence < MIN_CONFIDENCE:
                continue
            # Centro del bounding box
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            texts.append({
                "text":       text.strip(),
                "confidence": round(confidence, 2),
                "center":     [int(sum(xs) / 4), int(sum(ys) / 4)],
            })

        # Descripción textual legible para el agente
        description = " | ".join(t["text"] for t in texts if t["text"])

        return {
            "description": description or "No readable text found.",
            "elements":    texts,
            "count":       len(texts),
        }

    except Exception as e:
        return {
            "description": f"OCR failed: {e}",
            "elements":    [],
            "count":       0,
        }
    
@registry.register(
    group="screen",
    name="monitors",
    description="List all connected monitors with their bounds and resolution.",
    params=[]
)
def monitors() -> AgentResponse:
    try:
        import win32api

        monitors_raw = win32api.EnumDisplayMonitors()
        result = []

        for i, (hMonitor, hdcMonitor, rect) in enumerate(monitors_raw):
            info = win32api.GetMonitorInfo(hMonitor)
            work = info["Work"]
            mon  = info["Monitor"]
            result.append({
                "index":   i,
                "primary": info["Flags"] == 1,
                "bounds":  {
                    "left":   mon[0],
                    "top":    mon[1],
                    "right":  mon[2],
                    "bottom": mon[3],
                    "width":  mon[2] - mon[0],
                    "height": mon[3] - mon[1],
                },
                "work_area": {
                    "left":   work[0],
                    "top":    work[1],
                    "right":  work[2],
                    "bottom": work[3],
                },
            })

        return AgentResponse.success({
            "monitors": result,
            "count":    len(result),
        })

    except ImportError:
        return AgentResponse.failure("pywin32 not installed. Run: pip install pywin32")
    except Exception as e:
        return AgentResponse.failure(f"Monitor enumeration failed: {e}")