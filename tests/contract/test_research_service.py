from src.frontend_api.research_service import ResearchService


class FakeMuyuClient:
    def __init__(self):
        self.targets = []
        self.recent = []

    def research_target(self, target):
        self.targets.append(target)
        return {
            "job_id": "research-1",
            "artifacts": [
                {
                    "source_url": target,
                    "source_type": "paper",
                    "method_summary": "feature selection with xgboost",
                }
            ],
        }

    def research_recent(self, topic, months):
        self.recent.append((topic, months))
        return {"job_id": "research-2", "artifacts": []}


def test_research_service_researches_target_and_recent_methods():
    client = FakeMuyuClient()
    service = ResearchService(muyu_client=client)

    target_job = service.research_target("https://example.test/paper")
    recent_job = service.research_recent("feature engineering", months=6)

    assert target_job["job_id"] == "research-1"
    assert recent_job["job_id"] == "research-2"
    assert client.targets == ["https://example.test/paper"]
    assert client.recent == [("feature engineering", 6)]
