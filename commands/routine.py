from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam
from memory.store import store

SEPARATOR = "|"


@registry.register(
    group="routine",
    name="set",
    description="Save a routine as a sequence of shell commands. Commands separated by '|'.",
    params=[
        CommandParam("name",  "string", True, None, "Routine name (e.g. 'modo gaming')"),
        CommandParam("steps", "string", True, None, "Shell commands separated by '|'. Example: 'audio volume --set 80|app launch --name discord'"),
    ]
)
def set_routine(name: str, steps: str) -> AgentResponse:
    try:
        commands = [s.strip() for s in steps.split(SEPARATOR) if s.strip()]
        if not commands:
            return AgentResponse.failure("No valid steps provided.")

        store.set_user_data("routines", name.lower().strip(), SEPARATOR.join(commands))
        return AgentResponse.success({
            "name":  name,
            "steps": commands,
            "count": len(commands),
        })
    except Exception as e:
        return AgentResponse.failure(f"Routine save failed: {e}")


@registry.register(
    group="routine",
    name="get",
    description="Get the steps of a saved routine.",
    params=[
        CommandParam("name", "string", True, None, "Routine name"),
    ]
)
def get_routine(name: str) -> AgentResponse:
    try:
        raw = store.get_user_data("routines", name.lower().strip())
        if raw is None:
            return AgentResponse.success({"found": False, "name": name})

        commands = [s.strip() for s in raw.split(SEPARATOR) if s.strip()]
        return AgentResponse.success({
            "found":   True,
            "name":    name,
            "steps":   commands,
            "count":   len(commands),
        })
    except Exception as e:
        return AgentResponse.failure(f"Routine fetch failed: {e}")


@registry.register(
    group="routine",
    name="list",
    description="List all saved routines.",
    params=[]
)
def list_routines() -> AgentResponse:
    try:
        entries = store.get_user_category("routines")
        result  = []
        for name, raw in entries.items():
            commands = [s.strip() for s in raw.split(SEPARATOR) if s.strip()]
            result.append({"name": name, "steps": commands, "count": len(commands)})

        return AgentResponse.success({"routines": result, "count": len(result)})
    except Exception as e:
        return AgentResponse.failure(f"Routine list failed: {e}")


@registry.register(
    group="routine",
    name="delete",
    description="Delete a saved routine.",
    params=[
        CommandParam("name", "string", True, None, "Routine name to delete"),
    ]
)
def delete_routine(name: str) -> AgentResponse:
    try:
        existing = store.get_user_data("routines", name.lower().strip())
        if existing is None:
            return AgentResponse.failure(f"Routine '{name}' not found.")

        store.delete_user_data("routines", name.lower().strip())
        return AgentResponse.success({"deleted": name})
    except Exception as e:
        return AgentResponse.failure(f"Routine delete failed: {e}")


@registry.register(
    group="routine",
    name="run",
    description="Execute a saved routine step by step.",
    params=[
        CommandParam("name", "string", True, None, "Routine name to execute"),
    ]
)
def run_routine(name: str) -> AgentResponse:
    try:
        raw = store.get_user_data("routines", name.lower().strip())
        if raw is None:
            return AgentResponse.failure(f"Routine '{name}' not found.")

        commands = [s.strip() for s in raw.split(SEPARATOR) if s.strip()]
        results  = []
        failed   = False

        for cmd in commands:
            tokens = cmd.split()
            if len(tokens) < 2:
                results.append({"command": cmd, "ok": False, "error": "Invalid command format"})
                failed = True
                break

            from core.registry import registry as reg
            from core.response import AgentResponse as AR
            import shlex

            try:
                parts    = shlex.split(cmd)
                group    = parts[0]
                cmd_name = parts[1]
                kwargs   = {}
                i        = 2
                while i < len(parts):
                    tok = parts[i]
                    if tok.startswith("--"):
                        key = tok[2:]
                        if i + 1 < len(parts) and not parts[i+1].startswith("--"):
                            val = parts[i+1]
                            if val.lower() == "true":    val = True
                            elif val.lower() == "false": val = False
                            else:
                                try: val = int(val)
                                except ValueError:
                                    try: val = float(val)
                                    except ValueError: pass
                            kwargs[key] = val
                            i += 2
                        else:
                            kwargs[key] = True
                            i += 1
                    else:
                        i += 1

                command = reg.get(group, cmd_name)
                if not command:
                    results.append({"command": cmd, "ok": False, "error": f"Unknown command: {group} {cmd_name}"})
                    failed = True
                    break

                result = command.fn(**kwargs)
                results.append({"command": cmd, "ok": result.ok, "data": result.data, "error": result.error})

                if not result.ok:
                    failed = True
                    break

            except Exception as e:
                results.append({"command": cmd, "ok": False, "error": str(e)})
                failed = True
                break

        return AgentResponse.success({
            "name":     name,
            "results":  results,
            "complete": not failed,
            "steps":    len(commands),
            "executed": len(results),
        })

    except Exception as e:
        return AgentResponse.failure(f"Routine execution failed: {e}")