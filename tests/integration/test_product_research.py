from src.frontend_api.research_service import ResearchService
from src.research.muyu_client import MuyuSearchClient


def test_default_muyu_client_reports_unavailable_instead_of_fake_success():
    service = ResearchService(muyu_client=MuyuSearchClient())

    job = service.research_target("https://example.test/paper")

    assert job["status"] == "unavailable"
    assert job["artifacts"] == []
    assert "muyu-search-mcp" in job["error"]


def test_injected_research_result_keeps_structured_artifact_fields():
    class InjectedClient:
        def research_target(self, target):
            return {
                "job_id": "research-1",
                "status": "completed",
                "artifacts": [
                    {
                        "source_url": target,
                        "source_type": "paper",
                        "method_summary": "stability selection with xgboost",
                        "feature_engineering_notes": "stability selection",
                        "model_notes": "xgboost",
                        "evaluation_notes": "auc and target specificity",
                        "reference_code_notes": "sklearn compatible pseudocode",
                        "limitations": "small cohort",
                    }
                ],
            }

        def research_recent(self, topic, months=6):
            return {"job_id": "research-2", "status": "completed", "artifacts": []}

    service = ResearchService(muyu_client=InjectedClient())

    job = service.research_target("https://example.test/paper")

    artifact = job["artifacts"][0]
    assert job["status"] == "completed"
    assert artifact["feature_engineering_notes"] == "stability selection"
    assert artifact["model_notes"] == "xgboost"
    assert artifact["evaluation_notes"] == "auc and target specificity"
    assert artifact["reference_code_notes"] == "sklearn compatible pseudocode"
