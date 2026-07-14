from __future__ import annotations

import uuid

from src.models import ResearchArtifact


class ResearchKnowledgeIngestor:
    def __init__(self, memory_service, clock=None, id_factory=None) -> None:
        self.memory_service = memory_service
        self.clock = clock or (lambda: 0)
        self.id_factory = id_factory or (lambda: str(uuid.uuid4()))

    def ingest(self, job_id: str, artifacts: list[dict]) -> list[ResearchArtifact]:
        ingested = []
        for item in artifacts:
            artifact = ResearchArtifact(
                artifact_id=self.id_factory(),
                research_job_id=job_id,
                source_url=item["source_url"],
                source_type=item["source_type"],
                method_summary=item["method_summary"],
                feature_engineering_notes=item.get("feature_engineering_notes", ""),
                model_notes=item.get("model_notes", ""),
                evaluation_notes=item.get("evaluation_notes", ""),
                reference_code_notes=item.get("reference_code_notes", ""),
                limitations=item.get("limitations", ""),
                created_at=self.clock(),
            )
            self.memory_service.add_experience(
                round_id=job_id,
                summary=artifact.method_summary,
                confidence="medium",
            )
            ingested.append(artifact)
        return ingested
