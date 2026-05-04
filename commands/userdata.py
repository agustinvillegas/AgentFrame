from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam
from memory.store import store

VALID_CATEGORIES = {"preferences", "environment", "schedule", "identity", "projects", "misc", "routines"}


@registry.register(
    group="user",
    name="set",
    description="Store something learned about the user under a category and key.",
    params=[
        CommandParam("category", "string", True, None, "Category: preferences | environment | schedule | identity | projects | misc"),
        CommandParam("key",      "string", True, None, "Key name (e.g. 'preferred_browser', 'work_dir')"),
        CommandParam("value",    "string", True, None, "Value to store"),
    ]
)
def set_user(category: str, key: str, value: str) -> AgentResponse:
    if category not in VALID_CATEGORIES:
        return AgentResponse.failure(
            f"Invalid category '{category}'. Valid: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    try:
        store.set_user_data(category, key, value)
        return AgentResponse.success({"category": category, "key": key, "value": value})
    except Exception as e:
        return AgentResponse.failure(f"Set failed: {e}")


@registry.register(
    group="user",
    name="get",
    description="Retrieve a specific value stored about the user.",
    params=[
        CommandParam("category", "string", True,  None, "Category to look in"),
        CommandParam("key",      "string", False, None, "Specific key. Omit to get all keys in category."),
    ]
)
def get_user(category: str, key: str | None = None) -> AgentResponse:
    if category not in VALID_CATEGORIES:
        return AgentResponse.failure(
            f"Invalid category '{category}'. Valid: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    try:
        if key:
            value = store.get_user_data(category, key)
            if value is None:
                return AgentResponse.success({"found": False, "category": category, "key": key})
            return AgentResponse.success({"found": True, "category": category, "key": key, "value": value})
        else:
            entries = store.get_user_category(category)
            return AgentResponse.success({"category": category, "entries": entries, "count": len(entries)})
    except Exception as e:
        return AgentResponse.failure(f"Get failed: {e}")


@registry.register(
    group="user",
    name="list",
    description="List all stored user data, optionally filtered by category.",
    params=[
        CommandParam("category", "string", False, None, "Filter by category. Omit to list all."),
    ]
)
def list_user(category: str | None = None) -> AgentResponse:
    if category and category not in VALID_CATEGORIES:
        return AgentResponse.failure(
            f"Invalid category '{category}'. Valid: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    try:
        data = store.get_all_user_data(category)
        return AgentResponse.success({"data": data, "categories": list(data.keys())})
    except Exception as e:
        return AgentResponse.failure(f"List failed: {e}")


@registry.register(
    group="user",
    name="delete",
    description="Delete a specific key or an entire category from user memory.",
    params=[
        CommandParam("category", "string", True,  None, "Category to delete from"),
        CommandParam("key",      "string", False, None, "Specific key to delete. Omit to delete entire category."),
    ]
)
def delete_user(category: str, key: str | None = None) -> AgentResponse:
    if category not in VALID_CATEGORIES:
        return AgentResponse.failure(
            f"Invalid category '{category}'. Valid: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    try:
        store.delete_user_data(category, key)
        if key:
            return AgentResponse.success({"deleted": {"category": category, "key": key}})
        return AgentResponse.success({"deleted": {"category": category, "all": True}})
    except Exception as e:
        return AgentResponse.failure(f"Delete failed: {e}")