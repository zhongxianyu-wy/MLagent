from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExplorationToolResult:
    tool_id: str
    status: str
    proposal: dict | None
    failure_reason: str | None


class ExplorationTool(Protocol):
    tool_id: str

    def propose(self, request: dict) -> ExplorationToolResult:
        ...
