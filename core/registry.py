from __future__ import annotations
import inspect
from typing import Callable, Any


class CommandParam:
    def __init__(self, name: str, type_: str, required: bool, default: Any, description: str):
        self.name = name
        self.type_ = type_
        self.required = required
        self.default = default
        self.description = description

    def to_dict(self) -> dict:
        return {
            "type": self.type_,
            "required": self.required,
            "default": self.default,
            "description": self.description,
        }


class Command:
    def __init__(self, name: str, fn: Callable, description: str, params: list[CommandParam]):
        self.name = name
        self.fn = fn
        self.description = description
        self.params = params

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "params": {p.name: p.to_dict() for p in self.params},
        }


class Registry:
    def __init__(self):
        self._groups: dict[str, dict[str, Command]] = {}

    def register(self, group: str, name: str, description: str, params: list[CommandParam]):
        """Decorator factory to register a command."""
        def decorator(fn: Callable) -> Callable:
            if group not in self._groups:
                self._groups[group] = {}
            self._groups[group][name] = Command(name, fn, description, params)
            return fn
        return decorator

    def get(self, group: str, name: str) -> Command | None:
        return self._groups.get(group, {}).get(name)

    def schema(self) -> dict:
        """Full machine-readable schema for all commands."""
        return {
            group: {cmd: command.to_dict() for cmd, command in commands.items()}
            for group, commands in self._groups.items()
        }

    def groups(self) -> list[str]:
        return list(self._groups.keys())

    def commands(self, group: str) -> list[str]:
        return list(self._groups.get(group, {}).keys())


# Global registry instance
registry = Registry()
