from src.exploration_tools.aide_tool import AIDEExplorationTool
from src.exploration_tools.orchestrator import ExplorationToolOrchestrator


class FakeAIDEProvider:
    def __init__(self):
        self.request = None

    def propose(self, request):
        self.request = request
        return {
            "direction": "standardize then low variance filter",
            "preprocessing": "standardize",
            "feature_subset": "low_variance",
            "model": "xgboost",
            "rationale": "bounded AIDE proposal",
        }


def test_aide_tool_is_bounded_candidate_in_exploration_orchestrator():
    provider = FakeAIDEProvider()
    tool = AIDEExplorationTool(provider=provider)
    orchestrator = ExplorationToolOrchestrator(tools=[tool])

    result = orchestrator.propose_round(
        {
            "dataset_summary": {"samples": 20, "features": 200},
            "objective": "auc",
            "budget": {"max_rounds": 1},
            "context_ids": ["mem-1"],
            "raw_matrix": [[1, 2, 3]],
        }
    )

    assert provider.request == {
        "dataset_summary": {"samples": 20, "features": 200},
        "objective": "auc",
        "budget": {"max_rounds": 1},
        "context_ids": ["mem-1"],
    }
    assert result.proposal == {
        "exploration_direction": "standardize then low variance filter",
        "preprocessing_strategy": "standardize",
        "feature_subset_strategy": "low_variance",
        "model_type": "xgboost",
        "llm_rationale_summary": "bounded AIDE proposal",
    }
