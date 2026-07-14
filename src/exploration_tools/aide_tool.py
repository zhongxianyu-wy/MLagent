from __future__ import annotations

from src.aide_adapter.journal_bridge import AIDEJournalBridge
from src.aide_adapter.routing import AIDERoutingAdapter
from src.exploration_tools.base import ExplorationToolResult


class AIDEExplorationTool:
    tool_id = "aide_tree_search"

    def __init__(self, provider) -> None:
        self.routing = AIDERoutingAdapter(provider)
        self.journal_bridge = AIDEJournalBridge()

    def propose(self, request: dict) -> ExplorationToolResult:
        journal = self.routing.propose(request)
        return ExplorationToolResult(
            tool_id=self.tool_id,
            status="ok",
            proposal=self.journal_bridge.to_trace_payload(journal),
            failure_reason=None,
        )
