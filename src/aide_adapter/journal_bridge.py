from __future__ import annotations


class AIDEJournalBridge:
    def to_trace_payload(self, journal: dict) -> dict:
        return {
            "exploration_direction": journal["direction"],
            "preprocessing_strategy": journal["preprocessing"],
            "feature_subset_strategy": journal["feature_subset"],
            "model_type": journal["model"],
            "llm_rationale_summary": journal["rationale"],
        }
