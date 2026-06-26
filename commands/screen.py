from __future__ import annotations
import base64
import io
import json as _json
import uuid
from core.response import AgentResponse
from core.registry import registry, CommandParam
from core.vision import detect_ui_elements, is_available as vision_available
from memory.store import store
import threading

from pywinauto import Desktop
import win32gui, win32con

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
        CommandParam("filter",       "string", False, None,  "Filter by type: 'button' | 'edit' | 'text' | 'link' | 'checkbox' | 'list' | 'menu'. Omit for all."),
        CommandParam("enabled_only", "bool",   False, False, "If true, return only interactable (enabled) elements."),
        CommandParam("window",       "string", False, None,  "Partial window title to inspect. Omit for active window."),
    ]
)
def elements(filter: str | None = None, enabled_only: bool = False, window: str | None = None) -> AgentResponse:
    try:
        active, err = _resolve_window(window)
        if err:
            return AgentResponse.failure(err)

        window_title = ""
        try:
            window_title = active.element_info.name or ""
        except Exception:
            pass

        raw_elements = []
        complete = True

# Run descendants() in a thread with timeout — Electron/Chromium windows
# can crash the process via COM if enumerated without a safety net
        _desc_result: list = []
        _desc_error:  list = []

        def _fetch_descendants():
            try:
                _desc_result.append(active.descendants())
            except Exception as e:
                _desc_error.append(str(e))

        _t = threading.Thread(target=_fetch_descendants, daemon=True)
        _t.start()
        _t.join(timeout=4.0)

        if _t.is_alive() or not _desc_result:
            err_msg = _desc_error[0] if _desc_error else "timed out"
            ocr = _ocr_active_window()
            result = {
                "elements": [],
                "count":    0,
                "window":   window_title,
                "complete": False,
                "note":     (
                    f"Accessibility Tree unavailable ({err_msg}). "
                    "Common cause: Electron/Chromium windows. OCR attached as fallback."
                ),
            }
            if ocr and ocr.get("elements"):
                result["ocr"] = ocr
                for el in ocr["elements"]:
                    text = el.get("text", "").strip()
                    center = el.get("center")
                    if text and center:
                        _auto_register_entity(
                            label=text,
                            bounds={"left": center[0]-20, "top": center[1]-10,
                                    "right": center[0]+20, "bottom": center[1]+10,
                                    "center": center},
                            window_title=window_title,
                            source="ocr",
                            confidence=el.get("confidence", 0.5),
                        )
            return AgentResponse.success(result)

        descendants = _desc_result[0]
       

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

        # Auto-register elements as entities for future reuse
        for el in elements_out:
            label = el.get("label", "").strip()
            if label and el.get("bounds"):
                _auto_register_entity(
                    label=label,
                    bounds=el["bounds"],
                    window_title=window_title,
                    source="accessibility",
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
    
def _auto_register_entity(
    label: str, bounds: dict, window_title: str,
    source: str, confidence: float = 1.0
):
    """Automatically register a detected element as a screen entity for future reuse."""
    try:
        entity_id = str(uuid.uuid4())
        name = label.strip().lower().replace(" ", "_")
        store.register_screen_entity(
            entity_id=entity_id,
            name=name,
            llm_name=label.strip(),
            window_title=window_title,
            window_class="",
            bounds=bounds,
            source=source,
            confidence=confidence,
        )
    except Exception:
        pass


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


@registry.register(
    group="screen",
    name="detect",
    description=(
        "Locate UI elements visually using the local vision model (Locate Anything). "
        "Provide a natural language prompt describing what to find. "
        "Detected elements are auto-registered as entities for future reuse."
    ),
    params=[
        CommandParam("prompt",     "string", True,  None,    "What to find (e.g. 'play button', 'search field', 'settings icon')"),
        CommandParam("window",     "string", False, None,    "Window title to inspect. Omit for active window."),
        CommandParam("threshold",  "float",  False, None,    "Confidence threshold 0-1. Defaults to AGENTSHELL_VISION_CONFIDENCE."),
        CommandParam("auto_register", "bool", False, True,   "Auto-register detected elements as entities."),
    ]
)
def detect(
    prompt: str,
    window: str | None = None,
    threshold: float | None = None,
    auto_register: bool = True,
) -> AgentResponse:
    try:
        import pyautogui
        import win32gui
        import win32process

        if window:
            hwnd = None
            def _cb(h, _):
                nonlocal hwnd
                if win32gui.IsWindowVisible(h):
                    t = win32gui.GetWindowText(h)
                    if window.lower() in t.lower():
                        hwnd = h
            win32gui.EnumWindows(_cb, None)
            if not hwnd:
                return AgentResponse.failure(f"No window matching '{window}' found.")
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            _, fgw_pid = win32process.GetWindowThreadProcessId(hwnd)
            if fgw_pid != __import__("os").getpid():
                win32gui.SetForegroundWindow(hwnd)
            __import__("time").sleep(0.3)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            window_title = win32gui.GetWindowText(hwnd)
        else:
            hwnd = win32gui.GetForegroundWindow()
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            window_title = win32gui.GetWindowText(hwnd) or "active window"

        width  = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return AgentResponse.failure("Window has zero size.")

        # Use --window or active window caption for entity registration
        caption = window_title

        img = pyautogui.screenshot(region=(left, top, width, height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        detections = detect_ui_elements(img_bytes, prompt, threshold)

        # Map coordinates back to screen space
        for d in detections:
            d["bounds"]["left"]   += left
            d["bounds"]["right"]  += left
            d["bounds"]["top"]    += top
            d["bounds"]["bottom"] += top
            d["center"][0] += left
            d["center"][1] += top

            if auto_register:
                _auto_register_entity(
                    label=d["label"],
                    bounds=d["bounds"],
                    window_title=caption,
                    source="locate_anything",
                    confidence=d["confidence"],
                )

        return AgentResponse.success({
            "detections": detections,
            "count":      len(detections),
            "prompt":     prompt,
            "window":     caption,
            "region":     {"left": left, "top": top, "width": width, "height": height},
            "note":       None if detections else (f"Vision model found no '{prompt}' in '{caption}'. Try a different prompt or use screen capture."),
        })

    except ImportError:
        return AgentResponse.failure("pyautogui or pywin32 not installed.")
    except Exception as e:
        return AgentResponse.failure(f"Detect failed: {e}")


@registry.register(
    group="screen",
    name="find",
    description=(
        "Find a UI element by text in the Accessibility Tree. "
        "Returns position and type of the first match. "
        "Use this instead of 'screen elements' when you know what you're looking for."
    ),
    params=[
        CommandParam("text",         "string", True,  None,  "Text to search for (case-insensitive partial match)"),
        CommandParam("type",         "string", False, None,  "Filter by element type: 'button' | 'edit' | 'link' | etc."),
        CommandParam("enabled_only", "bool",   False, True,  "Only return enabled/interactable elements"),
        CommandParam("window",       "string", False, None,  "Partial window title to inspect. Omit for active window."),
    ]
)
def find(text: str, type: str | None = None, enabled_only: bool = True, window: str | None = None) -> AgentResponse:
    try:
        active, err = _resolve_window(window)
        if err:
            return AgentResponse.failure(err)

        text_lower = text.lower()
        matches    = []

        for ctrl in active.descendants():
            try:
                info      = ctrl.element_info
                ctrl_type = (info.control_type or "").lower()
                label     = (info.name or "").strip()
                enabled   = info.enabled

                if not label:
                    continue
                if enabled_only and not enabled:
                    continue
                if type and ctrl_type != type.lower():
                    continue
                if text_lower not in label.lower():
                    continue

                rect = info.rectangle
                element = {
                    "type":    ctrl_type,
                    "label":   label,
                    "enabled": enabled,
                }
                if rect:
                    element["center"] = [
                        (rect.left + rect.right)  // 2,
                        (rect.top  + rect.bottom) // 2,
                    ]
                    element["bounds"] = {
                        "left": rect.left, "top": rect.top,
                        "right": rect.right, "bottom": rect.bottom,
                    }
                matches.append(element)

            except Exception:
                continue

        if not matches:
            return AgentResponse.success({
                "found":   False,
                "matches": [],
                "count":   0,
            })

        # Auto-register matched elements as entities
        window_title = ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            window_title = win32gui.GetWindowText(hwnd)
        except Exception:
            pass
        for m in matches:
            if m.get("label") and m.get("bounds"):
                _auto_register_entity(
                    label=m["label"],
                    bounds=m["bounds"],
                    window_title=window_title,
                    source="accessibility",
                )

        return AgentResponse.success({
            "found":   True,
            "matches": matches,
            "count":   len(matches),
            "first":   matches[0],
        })

    except ImportError:
        return AgentResponse.failure("pywinauto not installed. Run: pip install pywinauto")
    except Exception as e:
        return AgentResponse.failure(f"Find failed: {e}")


@registry.register(
    group="screen",
    name="text",
    description=(
        "Extract all visible text from the active window in reading order. "
        "Use when you need to read content, not interact with elements."
    ),
    params=[
        CommandParam("min_length", "int", False, 2, "Ignore text shorter than this. Filters out icons and single chars."),
    ]
)
def text(min_length: int = 2) -> AgentResponse:
    try:
        from pywinauto import Desktop

        active = Desktop(backend="uia").active()
        if not active:
            return AgentResponse.failure("No active window.")

        window_title = ""
        try:
            window_title = active.element_info.name or ""
        except Exception:
            pass

        texts = []
        for ctrl in active.descendants():
            try:
                info  = ctrl.element_info
                label = (info.name or "").strip()
                rect  = info.rectangle

                if not label or len(label) < min_length:
                    continue

                # Ordenar por posición vertical luego horizontal
                top  = rect.top  if rect else 0
                left = rect.left if rect else 0
                texts.append((top, left, label))

            except Exception:
                continue

        # Deduplicar y ordenar en orden de lectura
        seen   = set()
        result = []
        for _, _, label in sorted(texts):
            if label not in seen:
                seen.add(label)
                result.append(label)

        content = "\n".join(result)

        return AgentResponse.success({
            "window":  window_title,
            "content": content,
            "lines":   len(result),
        })

    except ImportError:
        return AgentResponse.failure("pywinauto not installed. Run: pip install pywinauto")
    except Exception as e:
        return AgentResponse.failure(f"Text extraction failed: {e}")


@registry.register(
    group="screen",
    name="wait",
    description=(
        "Wait until a UI element with the given text appears on screen. "
        "Use after triggering an action that causes a page load, dialog, or state change."
    ),
    params=[
        CommandParam("text",     "string", True,  None, "Text to wait for (case-insensitive partial match)"),
        CommandParam("timeout",  "int",    False, 10,   "Max seconds to wait before giving up"),
        CommandParam("interval", "float",  False, 0.5,  "How often to check, in seconds"),
        CommandParam("window",   "string", False, None, "Partial window title to inspect. Omit for active window."),
    ]
)
def wait(text: str, timeout: int = 10, interval: float = 0.5, window: str | None = None) -> AgentResponse:
    try:
        import time
        text_lower = text.lower()
        elapsed    = 0.0

        while elapsed < timeout:
            active, _ = _resolve_window(window)
            if active:
                try:
                    for ctrl in active.descendants():
                        try:
                            label = (ctrl.element_info.name or "").strip()
                            if text_lower in label.lower():
                                rect   = ctrl.element_info.rectangle
                                center = None
                                if rect:
                                    center = [
                                        (rect.left + rect.right)  // 2,
                                        (rect.top  + rect.bottom) // 2,
                                    ]
                                return AgentResponse.success({
                                    "found":     True,
                                    "text":      label,
                                    "elapsed_s": round(elapsed, 1),
                                    "center":    center,
                                })
                        except Exception:
                            continue
                except Exception:
                    pass

            time.sleep(interval)
            elapsed += interval

        return AgentResponse.success({
            "found":     False,
            "elapsed_s": round(elapsed, 1),
            "timeout":   timeout,
        })
    except Exception as e:
        return AgentResponse.failure(f"Wait failed: {e}")


@registry.register(
    group="screen",
    name="waitgone",
    description=(
        "Wait until a UI element with the given text disappears from screen. "
        "Use after triggering an action that should close a dialog, spinner, or loading state."
    ),
    params=[
        CommandParam("text",     "string", True,  None, "Text to wait for disappearance (case-insensitive partial match)"),
        CommandParam("timeout",  "int",    False, 10,   "Max seconds to wait before giving up"),
        CommandParam("interval", "float",  False, 0.5,  "How often to check, in seconds"),
        CommandParam("window",   "string", False, None, "Partial window title to inspect. Omit for active window."),
    ]
)
def waitgone(text: str, timeout: int = 10, interval: float = 0.5, window: str | None = None) -> AgentResponse:
    try:
        import time
        text_lower = text.lower()
        elapsed    = 0.0

        while elapsed < timeout:
            active, _ = _resolve_window(window)
            found = False
            if active:
                try:
                    for ctrl in active.descendants():
                        try:
                            label = (ctrl.element_info.name or "").strip()
                            if text_lower in label.lower():
                                found = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            if not found:
                return AgentResponse.success({
                    "gone":      True,
                    "elapsed_s": round(elapsed, 1),
                })

            time.sleep(interval)
            elapsed += interval

        return AgentResponse.success({
            "gone":      False,
            "elapsed_s": round(elapsed, 1),
            "timeout":   timeout,
        })
    except Exception as e:
        return AgentResponse.failure(f"Wait gone failed: {e}")


@registry.register(
    group="screen",
    name="click_entity",
    description=(
        "Click a previously registered screen entity by its LLM-friendly name. "
        "Resolves coordinates from memory — zero vision cost. "
        "Uses active window for disambiguation when the same name exists in multiple windows."
    ),
    params=[
        CommandParam("llm_name", "string", True,  None,  "Entity LLM name as used in entity register/get (e.g. 'play button')"),
        CommandParam("window",   "string", False, None,  "Window title to disambiguate. Omit for active window."),
        CommandParam("button",   "string", False, "left", "Mouse button: 'left', 'right', 'middle'"),
    ]
)
def click_entity(llm_name: str, window: str | None = None, button: str = "left") -> AgentResponse:
    try:
        import pyautogui
        import win32gui

        window_title = window
        if not window_title:
            hwnd = win32gui.GetForegroundWindow()
            window_title = win32gui.GetWindowText(hwnd) or "unknown"

        entity = store.get_screen_entity(llm_name.strip(), window_title)
        if not entity:
            candidates = store.find_screen_entities(llm_name.strip())

            if len(candidates) == 1:
                entity = candidates[0]
            elif len(candidates) > 1:
                return AgentResponse.success({
                    "clicked":    False,
                    "ambiguous":  True,
                    "candidates": candidates,
                    "count":      len(candidates),
                    "note":       f"Found {len(candidates)} entities matching '{llm_name}'. Specify --window or focus the target window.",
                })
            else:
                return AgentResponse.failure(
                    f"No entity found for '{llm_name}' in '{window_title}'. "
                    "Use 'screen detect' or 'screen find' to discover and register it first."
                )

        store.update_screen_entity_hit(entity["entity_id"])
        bounds = entity["bounds"]
        cx = bounds.get("center", [bounds.get("left", 0) + bounds.get("right", 0) // 2, 0])[0]
        cy = bounds.get("center", [0, bounds.get("top", 0) + bounds.get("bottom", 0) // 2])[1]

        pyautogui.click(cx, cy, button=button)

        return AgentResponse.success(
            {
                "clicked":      True,
                "entity_name":  entity.get("name"),
                "llm_name":     entity.get("llm_name"),
                "x":            cx,
                "y":            cy,
                "window":       entity.get("window_title"),
                "from_memory":  True,
            },
            state_delta={"last_action": f"clicked {entity.get('llm_name')} via entity memory", "result": "click executed from memorized coordinates"}
        )

    except ImportError:
        return AgentResponse.failure("pyautogui not installed. Run: pip install pyautogui")
    except Exception as e:
        return AgentResponse.failure(f"Click entity failed: {e}")


def _resolve_window(window: str | None):
    import win32gui, win32con
    import win32process
    import time
    import os
    from pywinauto import Application

    current_pid = os.getpid()

    if window:
        hwnd = None
        def _cb(h, _):
            nonlocal hwnd
            if win32gui.IsWindowVisible(h):
                title = win32gui.GetWindowText(h)
                if window.lower() in title.lower():
                    hwnd = h
        win32gui.EnumWindows(_cb, None)

        if not hwnd:
            return None, f"No window matching '{window}' found."

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            import win32api
            cur_tid = win32api.GetCurrentThreadId()
            tgt_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            win32api.AttachThreadInput(cur_tid, tgt_tid, True)
            win32gui.SetForegroundWindow(hwnd)
            win32api.AttachThreadInput(cur_tid, tgt_tid, False)
        except Exception:
            pass
        time.sleep(0.3)

    else:
        # Sin --window: usar la ventana en foco excluyendo el proceso actual
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, "No active window found."

        _, fgw_pid = win32process.GetWindowThreadProcessId(hwnd)
        if fgw_pid == current_pid:
            # El terminal tiene el foco — buscar la última ventana visible que no sea el shell
            candidate = None
            def _cb2(h, _):
                nonlocal candidate
                if candidate:
                    return
                if not win32gui.IsWindowVisible(h):
                    return
                if not win32gui.GetWindowText(h):
                    return
                _, pid = win32process.GetWindowThreadProcessId(h)
                if pid != current_pid:
                    candidate = h
            win32gui.EnumWindows(_cb2, None)

            if not candidate:
                return None, "No suitable window found — specify --window."
            hwnd = candidate

    try:
        app    = Application(backend="uia").connect(handle=hwnd)
        active = app.window(handle=hwnd)
        return active, None
    except Exception as e:
        return None, f"Could not access window: {e}"