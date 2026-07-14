from pathlib import Path


def test_service_contracts_include_streamlit_readiness_review():
    contracts = Path("specs/001-ngs-ml-agent/contracts/service-contracts.md").read_text()

    assert "## Streamlit Readiness Review" in contracts
    assert "ConversationService" in contracts
    assert "DatasetService" in contracts
    assert "RunService" in contracts
    assert "MemoryService" in contracts
    assert "SkillService" in contracts
    assert "ResearchService" in contracts
    assert "direct Python service calls" in contracts
    assert "HTTP/SSE" in contracts
    assert "must not call AIDE, MLflow, ChromaDB, or local file adapters directly" in contracts
