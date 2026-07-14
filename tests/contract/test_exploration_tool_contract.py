from src.exploration_tools.base import ExplorationToolResult
from src.exploration_tools.orchestrator import ExplorationToolOrchestrator


class FailingTool:
    tool_id = "aide_tree_search"

    def propose(self, request):
        return ExplorationToolResult(
            tool_id=self.tool_id,
            status="timeout",
            proposal=None,
            failure_reason="timeout",
        )


class SuccessfulTool:
    tool_id = "memory_guided_search"

    def propose(self, request):
        return ExplorationToolResult(
            tool_id=self.tool_id,
            status="ok",
            proposal={"direction": "variance filter"},
            failure_reason=None,
        )


def test_exploration_tool_orchestrator_falls_back_after_timeout():
    orchestrator = ExplorationToolOrchestrator(
        tools=[FailingTool(), SuccessfulTool()]
    )

    result = orchestrator.propose_round({"dataset_summary": {"features": 100}})

    assert result.proposal == {"direction": "variance filter"}
    assert result.audit_trail == [
        {"tool_id": "aide_tree_search", "status": "timeout", "failure_reason": "timeout"},
        {"tool_id": "memory_guided_search", "status": "ok", "failure_reason": None},
    ]
