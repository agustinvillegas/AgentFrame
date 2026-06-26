from __future__ import annotations
import uuid
from core.response import AgentResponse
from core.registry import registry, CommandParam
from memory.store import store


@registry.register(
    group="entity",
    name="register",
    description="Save a screen element as a named entity for later use. The LLM can refer to it by llm_name.",
    params=[
        CommandParam("llm_name",    "string", True,  None,   "Name the LLM will use to refer to this element (e.g. 'play button')"),
        CommandParam("bounds",      "string", True,  None,   "JSON bounds: {left, top, right, bottom, center: [x,y]}"),
        CommandParam("window",      "string", False, None,   "Window title this entity belongs to. Omit to auto-detect active window."),
        CommandParam("name",        "string", False, None,   "Canonical element name. Auto-derived from llm_name if omitted."),
        CommandParam("source",      "string", False, "manual","Detection source: 'accessibility', 'ocr', 'locate_anything', 'manual'"),
        CommandParam("confidence",  "float",  False, 1.0,    "Detection confidence (0-1)"),
    ]
)
def register(
    llm_name: str,
    bounds: str,
    window: str | None = None,
    name: str | None = None,
    source: str = "manual",
    confidence: float = 1.0,
) -> AgentResponse:
    try:
        import json as _json
        import win32gui

        parsed_bounds = _json.loads(bounds) if isinstance(bounds, str) else bounds

        if window:
            window_title = window
        else:
            hwnd = win32gui.GetForegroundWindow()
            window_title = win32gui.GetWindowText(hwnd) or "unknown"

        entity_id = str(uuid.uuid4())
        canonical_name = (name or llm_name).strip().lower().replace(" ", "_")

        store.register_screen_entity(
            entity_id=entity_id,
            name=canonical_name,
            llm_name=llm_name.strip(),
            window_title=window_title,
            window_class="",
            bounds=parsed_bounds,
            source=source,
            confidence=confidence,
        )

        return AgentResponse.success({
            "entity_id": entity_id,
            "llm_name":  llm_name,
            "name":      canonical_name,
            "window":    window_title,
            "bounds":    parsed_bounds,
        })
    except Exception as e:
        return AgentResponse.failure(f"Entity register failed: {e}")


@registry.register(
    group="entity",
    name="get",
    description="Retrieve a registered entity by LLM name and optional window. Uses active window for disambiguation.",
    params=[
        CommandParam("llm_name", "string", True,  None,  "Name the LLM used to refer to this element"),
        CommandParam("window",   "string", False, None,  "Window title to disambiguate. Omit to use active window."),
    ]
)
def get(llm_name: str, window: str | None = None) -> AgentResponse:
    try:
        import win32gui

        window_title = window
        if not window_title:
            hwnd = win32gui.GetForegroundWindow()
            window_title = win32gui.GetWindowText(hwnd) or "unknown"

        entity = store.get_screen_entity(llm_name.strip(), window_title)
        if entity:
            store.update_screen_entity_hit(entity["entity_id"])
            return AgentResponse.success({
                "found":   True,
                "entity":  entity,
            })

        candidates = store.find_screen_entities(llm_name.strip())
        if len(candidates) == 1:
            store.update_screen_entity_hit(candidates[0]["entity_id"])
            return AgentResponse.success({
                "found":    True,
                "entity":   candidates[0],
                "note":     f"Matched by partial name in window '{candidates[0]['window_title']}'.",
            })

        if len(candidates) > 1:
            return AgentResponse.success({
                "found":      False,
                "ambiguous":  True,
                "candidates": candidates,
                "count":      len(candidates),
                "note":       f"Found {len(candidates)} entities matching '{llm_name}'. Specify --window or focus the target window.",
            })

        return AgentResponse.success({"found": False, "llm_name": llm_name, "window": window_title})
    except Exception as e:
        return AgentResponse.failure(f"Entity get failed: {e}")


@registry.register(
    group="entity",
    name="find",
    description="Search registered entities by partial LLM name, optionally filtered by window.",
    params=[
        CommandParam("llm_name", "string", True,  None,  "Partial LLM name to search for"),
        CommandParam("window",   "string", False, None,  "Filter by window title"),
    ]
)
def find(llm_name: str, window: str | None = None) -> AgentResponse:
    try:
        entities = store.find_screen_entities(llm_name.strip(), window)
        return AgentResponse.success({
            "entities": entities,
            "count":    len(entities),
            "query":    llm_name,
            "window":   window,
        })
    except Exception as e:
        return AgentResponse.failure(f"Entity find failed: {e}")


@registry.register(
    group="entity",
    name="list",
    description="List all registered screen entities, optionally filtered by window.",
    params=[
        CommandParam("window", "string", False, None, "Filter by window title"),
    ]
)
def list_entities(window: str | None = None) -> AgentResponse:
    try:
        entities = store.list_screen_entities(window)
        return AgentResponse.success({
            "entities": entities,
            "count":    len(entities),
        })
    except Exception as e:
        return AgentResponse.failure(f"Entity list failed: {e}")


@registry.register(
    group="entity",
    name="delete",
    description="Delete a registered screen entity by its entity_id.",
    params=[
        CommandParam("entity_id", "string", True, None, "UUID of the entity to delete"),
    ]
)
def delete(entity_id: str) -> AgentResponse:
    try:
        store.delete_screen_entity(entity_id)
        return AgentResponse.success({"deleted": entity_id})
    except Exception as e:
        return AgentResponse.failure(f"Entity delete failed: {e}")


@registry.register(
    group="entity",
    name="update",
    description="Update a registered entity's bounds or LLM name.",
    params=[
        CommandParam("entity_id", "string", True,  None,  "UUID of the entity to update"),
        CommandParam("bounds",    "string", False, None,  "New JSON bounds: {left, top, right, bottom, center: [x,y]}"),
        CommandParam("llm_name",  "string", False, None,  "New LLM-friendly name"),
    ]
)
def update(entity_id: str, bounds: str | None = None, llm_name: str | None = None) -> AgentResponse:
    try:
        import json as _json

        updated = {}
        if bounds:
            parsed = _json.loads(bounds) if isinstance(bounds, str) else bounds
            store.update_screen_entity_bounds(entity_id, parsed)
            updated["bounds"] = parsed
        if llm_name:
            store.update_screen_entity_llm_name(entity_id, llm_name.strip())
            updated["llm_name"] = llm_name

        if not updated:
            return AgentResponse.failure("Nothing to update. Provide --bounds or --llm_name.")

        return AgentResponse.success({"entity_id": entity_id, **updated})
    except Exception as e:
        return AgentResponse.failure(f"Entity update failed: {e}")
