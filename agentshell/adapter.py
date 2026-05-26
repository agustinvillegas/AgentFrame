from __future__ import annotations
from typing import Any
from .client import AgentShellClient


# Mapeo de tipos del schema de AgentShell a tipos JSON Schema (Anthropic tool use)
_TYPE_MAP = {
    "string": "string",
    "int":    "integer",
    "float":  "number",
    "bool":   "boolean",
}


class AnthropicAdapter:
    """
    Traduce entre Anthropic tool use y AgentShell.

    Uso:
        adapter = AnthropicAdapter()
        tools   = adapter.get_tools()          # pasar a la API de Anthropic
        result  = adapter.call("screen_elements", {"window": "Brave"})  # desde tool_use block
    """

    def __init__(self, client: AgentShellClient | None = None, shell_path=None):
        self._client = client or AgentShellClient(shell_path)
        self._schema: dict | None = None

    # ------------------------------------------------------------------ #
    #  Schema                                                              #
    # ------------------------------------------------------------------ #

    def _get_schema(self) -> dict:
        if self._schema is None:
            self._schema = self._client.schema()
        return self._schema

    def get_tools(self) -> list[dict]:
        """
        Devuelve la lista de tools en formato Anthropic tool use.
        Pasar directamente al parámetro `tools` de la API.
        """
        schema = self._get_schema()
        tools  = []

        for group, commands in schema.items():
            for cmd_name, cmd_def in commands.items():
                tool = self._build_tool(group, cmd_name, cmd_def)
                tools.append(tool)

        return tools

    def _build_tool(self, group: str, cmd_name: str, cmd_def: dict) -> dict:
        tool_name   = f"{group}_{cmd_name}"   # ej: screen_elements, audio_volume
        description = cmd_def.get("description", "")
        params      = cmd_def.get("params", {})

        properties = {}
        required   = []

        for param_name, param_def in params.items():
            prop: dict[str, Any] = {
                "type":        _TYPE_MAP.get(param_def.get("type", "string"), "string"),
                "description": param_def.get("description", ""),
            }

            default = param_def.get("default")
            if default is not None:
                prop["default"] = default

            properties[param_name] = prop

            if param_def.get("required", False):
                required.append(param_name)

        input_schema: dict[str, Any] = {
            "type":       "object",
            "properties": properties,
        }
        if required:
            input_schema["required"] = required

        return {
            "name":         tool_name,
            "description":  description,
            "input_schema": input_schema,
        }

    def call(self, tool_name: str, params: dict) -> dict:
        """
        Ejecuta una tool call de Anthropic en el shell.

        Args:
            tool_name: nombre en formato "group_command" (ej: "screen_elements")
            params:    dict de parámetros del bloque tool_use de Anthropic

        Returns:
            dict con ok, data/error — el resultado directo del shell
        """
        command = self._build_command(tool_name, params)
        if command is None:
            return {"ok": False, "error": f"Unknown tool: {tool_name}"}
        return self._client.run(command)

    def call_block(self, block: dict) -> dict:
        """
        Ejecuta directamente un bloque tool_use de la respuesta de Anthropic.

            for block in response.content:
                if block.type == "tool_use":
                    result = adapter.call_block(block)

        Args:
            block: objeto con .name y .input (o dict con "name" e "input")
        """
        if isinstance(block, dict):
            name   = block["name"]
            params = block.get("input", {})
        else:
            name   = block.name
            params = block.input

        return self.call(name, params)

    def _build_command(self, tool_name: str, params: dict) -> str | None:
        """Convierte tool_name + params al string de comando del shell."""
        # tool_name = "screen_elements" → group="screen", cmd="elements"
        parts = tool_name.split("_", 1)
        if len(parts) != 2:
            return None

        group, cmd = parts

        # Verificar que existe en el schema
        schema = self._get_schema()
        if group not in schema or cmd not in schema[group]:
            return None

        # Construir el string: "screen elements --window Brave --filter button"
        tokens = [group, cmd]
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, bool):
                tokens.append(f"--{key} {str(value).lower()}")
            else:
                # Strings con espacios van entre comillas
                str_val = str(value)
                if " " in str_val:
                    tokens.append(f'--{key} "{str_val}"')
                else:
                    tokens.append(f"--{key} {str_val}")

        return " ".join(tokens)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def context(self) -> dict:
        """Devuelve el contexto actual del shell."""
        return self._client.context()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()