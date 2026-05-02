from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class AgentResponse:
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    state_delta: dict[str, Any] = field(default_factory=dict)

    def dump(self) -> str:
        out: dict = {"ok": self.ok}
        if self.data is not None:
            out["data"] = self.data
        if self.error is not None:
            out["error"] = self.error
        if self.state_delta:
            out["state_delta"] = self.state_delta
        return json.dumps(out, ensure_ascii=False)

    @staticmethod
    def success(data: dict[str, Any] | None = None, state_delta: dict[str, Any] | None = None) -> "AgentResponse":
        return AgentResponse(ok=True, data=data, state_delta=state_delta or {})

    @staticmethod
    def failure(error: str, state_delta: dict[str, Any] | None = None) -> "AgentResponse":
        return AgentResponse(ok=False, error=error, state_delta=state_delta or {})
