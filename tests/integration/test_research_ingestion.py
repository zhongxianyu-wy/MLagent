from src.frontend_api.research_service import ResearchService
from src.research.knowledge_ingest import ResearchKnowledgeIngestor


class FakeMuyuClient:
    def research_target(self, target):
        return {
            "job_id": "research-1",
            "artifacts": [
                {
                    "source_url": target,
                    "source_type": "paper",
                    "method_summary": "XGBoost with stability feature selection",
                    "feature_engineering_notes": "stability selection",
                    "model_notes": "xgboost",
                    "evaluation_notes": "auc",
                    "reference_code_notes": "sklearn compatible",
                    "limitations": "small cohort",
                }
            ],
        }

    def research_recent(self, topic, months):
        return {"job_id": "research-2", "artifacts": []}


class FakeMemoryService:
    def __init__(self):
        self.experiences = []

    def add_experience(self, round_id, summary, confidence):
        self.experiences.append((round_id, summary, confidence))


def test_research_artifact_ingestion_with_mocked_muyu_search():
    memory = FakeMemoryService()
    service = ResearchService(
        muyu_client=FakeMuyuClient(),
        ingestor=ResearchKnowledgeIngestor(memory_service=memory, clock=lambda: 123),
    )
    job = service.research_target("https://example.test/paper")

    artifacts = service.ingest_research(job["job_id"])

    assert len(artifacts) == 1
    assert artifacts[0].research_job_id == "research-1"
    assert artifacts[0].method_summary == "XGBoost with stability feature selection"
    assert memory.experiences == [
        (
            "research-1",
            "XGBoost with stability feature selection",
            "medium",
        )
    ]
