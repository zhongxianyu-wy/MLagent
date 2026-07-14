from __future__ import annotations

from dataclasses import dataclass

from src.exploration_tools.base import ExplorationTool


@dataclass(frozen=True)
class OrchestratedExplorationResult:
    proposal: dict
    audit_trail: list[dict]


class ExplorationToolOrchestrator:
    def __init__(self, tools: list[ExplorationTool]) -> None:
        self.tools = tools

    def propose_round(self, request: dict) -> OrchestratedExplorationResult:
        audit_trail = []
        for tool in self.tools:
            result = tool.propose(request)
            audit_trail.append(
                {
                    "tool_id": result.tool_id,
                    "status": result.status,
                    "failure_reason": result.failure_reason,
                }
            )
            if result.status == "ok" and result.proposal is not None:
                return OrchestratedExplorationResult(
                    proposal=result.proposal,
                    audit_trail=audit_trail,
                )
        raise RuntimeError("no exploration tool produced a proposal")
