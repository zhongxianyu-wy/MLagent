from __future__ import annotations


class SkillService:
    def __init__(
        self,
        registry,
        reproduction_adapter=None,
        candidate_generator=None,
        publisher=None,
    ) -> None:
        self.registry = registry
        self.reproduction_adapter = reproduction_adapter
        self.candidate_generator = candidate_generator
        self.publisher = publisher

    def list_skills(self):
        return self.registry.list_skills()

    def reproduce(self, skill_id: str, dataset: dict) -> dict:
        if self.reproduction_adapter is None:
            raise ValueError("reproduction_adapter is required")
        return self.reproduction_adapter.reproduce(skill_id, dataset)

    def create_candidate_from_notebook(self, path: str):
        if self.candidate_generator is None:
            raise ValueError("candidate_generator is required")
        return self.candidate_generator.from_notebook(path)

    def create_candidate_from_best_run(self, experiment_id: str, trace_summary: dict):
        if self.candidate_generator is None:
            raise ValueError("candidate_generator is required")
        return self.candidate_generator.from_best_run(experiment_id, trace_summary)

    def approve_candidate(self, candidate_id: str):
        if self.publisher is None:
            raise ValueError("publisher is required")
        return self.publisher.publish(candidate_id, approved=True)
