from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam
from memory.store import store


@registry.register(
    group="index",
    name="query",
    description=(
        "Query the activity index. Returns matching chunk summaries. "
        "Use this to retrieve past context on demand — only call when you need it."
    ),
    params=[
        CommandParam("last",   "int",    False, None, "Return the last N entries"),
        CommandParam("tags",   "string", False, None, "Comma-separated tags to filter by (e.g. 'github,research')"),
        CommandParam("since",  "string", False, None, "Return entries since this time. Format: HH:MM or ISO datetime"),
        CommandParam("window", "string", False, None, "Filter by partial window title"),
    ]
)
def query(
    last:   int | None = None,
    tags:   str | None = None,
    since:  str | None = None,
    window: str | None = None,
) -> AgentResponse:
    try:
        if last is not None:
            entries = store.query_last(last)
        elif tags is not None:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            entries = store.query_tags(tag_list)
        elif since is not None:
            entries = store.query_since(since)
        elif window is not None:
            entries = store.query_window(window)
        else:
            entries = store.query_last(20)

        return AgentResponse.success({
            "entries": entries,
            "count":   len(entries),
        })
    except Exception as e:
        return AgentResponse.failure(f"Index query failed: {e}")


@registry.register(
    group="index",
    name="summary",
    description="Get a count of all indexed entries and the most recent 3 summaries.",
    params=[]
)
def summary() -> AgentResponse:
    try:
        total   = store.chunk_count()
        recent  = store.query_last(3)
        return AgentResponse.success({
            "total_entries": total,
            "recent":        recent,
        })
    except Exception as e:
        return AgentResponse.failure(f"Index summary failed: {e}")


@registry.register(
    group="context",
    name="get",
    description=(
        "Get the current mandatory context — active window, last action, result, state, session goal. "
        "This is automatically injected into every prompt, but you can query it explicitly."
    ),
    params=[]
)
def get_context() -> AgentResponse:
    try:
        ctx = store.get_context()
        if not ctx:
            return AgentResponse.success({
                "context": {},
                "note": "No context yet. Context is populated after the first activity chunk is processed."
            })
        return AgentResponse.success({"context": ctx})
    except Exception as e:
        return AgentResponse.failure(f"Context fetch failed: {e}")


@registry.register(
    group="context",
    name="set",
    description="Manually update a field in the mandatory context. Use sparingly — context is normally managed by the Indexer.",
    params=[
        CommandParam("key",   "string", True, None, "Field to update: active_window | last_action | result | state | session_goal"),
        CommandParam("value", "string", True, None, "New value"),
    ]
)
def set_context(key: str, value: str) -> AgentResponse:
    ALLOWED = {"active_window", "last_action", "result", "state", "session_goal"}
    if key not in ALLOWED:
        return AgentResponse.failure(
            f"Invalid key '{key}'. Allowed: {', '.join(sorted(ALLOWED))}"
        )
    try:
        store.update_context({key: value})
        return AgentResponse.success({"updated": {key: value}})
    except Exception as e:
        return AgentResponse.failure(f"Context update failed: {e}")
