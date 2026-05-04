from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam
from memory.store import store


@registry.register(
    group="credentials",
    name="set",
    description="Store a credential for a service. Value is encrypted at rest.",
    params=[
        CommandParam("service", "string", True, None, "Service name (e.g. 'spotify', 'github')"),
        CommandParam("key",     "string", True, None, "Credential key (e.g. 'email', 'api_key', 'password')"),
        CommandParam("value",   "string", True, None, "Value to store (will be encrypted)"),
    ]
)
def set_credential(service: str, key: str, value: str) -> AgentResponse:
    try:
        store.set_credential(service, key, value)
        return AgentResponse.success({
            "service":   service,
            "key":       key,
            "encrypted": True,
        })
    except Exception as e:
        return AgentResponse.failure(f"Credential save failed: {e}")


@registry.register(
    group="credentials",
    name="get",
    description="Retrieve a stored credential. Returns decrypted value.",
    params=[
        CommandParam("service", "string", True,  None, "Service name"),
        CommandParam("key",     "string", True,  None, "Credential key"),
    ]
)
def get_credential(service: str, key: str) -> AgentResponse:
    try:
        value = store.get_credential(service, key)
        if value is None:
            return AgentResponse.success({"found": False, "service": service, "key": key})
        return AgentResponse.success({"found": True, "service": service, "key": key, "value": value})
    except Exception as e:
        return AgentResponse.failure(f"Credential fetch failed: {e}")


@registry.register(
    group="credentials",
    name="list",
    description="List all stored services and their keys. Values are never shown.",
    params=[
        CommandParam("service", "string", False, None, "Filter by service name. Omit to list all."),
    ]
)
def list_credentials(service: str | None = None) -> AgentResponse:
    try:
        data = store.list_credentials(service)
        return AgentResponse.success({"services": data, "count": len(data)})
    except Exception as e:
        return AgentResponse.failure(f"Credential list failed: {e}")


@registry.register(
    group="credentials",
    name="delete",
    description="Delete a credential or all credentials for a service.",
    params=[
        CommandParam("service", "string", True,  None, "Service name"),
        CommandParam("key",     "string", False, None, "Specific key to delete. Omit to delete entire service."),
    ]
)
def delete_credential(service: str, key: str | None = None) -> AgentResponse:
    try:
        store.delete_credential(service, key)
        if key:
            return AgentResponse.success({"deleted": {"service": service, "key": key}})
        return AgentResponse.success({"deleted": {"service": service, "all": True}})
    except Exception as e:
        return AgentResponse.failure(f"Credential delete failed: {e}")