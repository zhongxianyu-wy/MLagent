from src.aide_adapter.journal_bridge import AIDEJournalBridge
from src.aide_adapter.routing import AIDERoutingAdapter


class FakeAIDEProvider:
    def __init__(self):
        self.received_request = None

    def propose(self, request):
        self.received_request = request
        return {
            "direction": "standardize then variance filter",
            "model_type": "xgboost",
            "rationale": "AIDE tree search found a compact branch",
        }


def test_aide_routing_adapter_only_passes_bounded_exploration_context():
    provider = FakeAIDEProvider()
    adapter = AIDERoutingAdapter(provider=provider)

    proposal = adapter.propose(
        {
            "dataset_summary": {"samples": 10, "features": 100},
            "objective": "auc",
            "budget": {"max_rounds": 3},
            "context_ids": ["mem-1", "skill-1"],
            "conversation_history": "do not send",
            "raw_matrix": [[1, 2, 3]],
        }
    )

    assert provider.received_request == {
        "dataset_summary": {"samples": 10, "features": 100},
        "objective": "auc",
        "budget": {"max_rounds": 3},
        "context_ids": ["mem-1", "skill-1"],
    }
    assert proposal["direction"] == "standardize then variance filter"


def test_aide_journal_bridge_converts_journal_to_trace_payload():
    payload = AIDEJournalBridge().to_trace_payload(
        {
            "direction": "variance filter",
            "preprocessing": "standardize",
            "feature_subset": "low_variance",
            "model": "xgboost",
            "rationale": "best AIDE branch",
            "internal_tree": {"hidden": "not exported"},
        }
    )

    assert payload == {
        "exploration_direction": "variance filter",
        "preprocessing_strategy": "standardize",
        "feature_subset_strategy": "low_variance",
        "model_type": "xgboost",
        "llm_rationale_summary": "best AIDE branch",
    }
