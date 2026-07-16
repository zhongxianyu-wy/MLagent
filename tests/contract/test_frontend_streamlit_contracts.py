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


def test_run_status_uses_two_second_domain_projection_fragment():
    source = Path("src/ui/app.py").read_text(encoding="utf-8")

    assert "@st.fragment(run_every=2.0)" in source
    assert "core.get_run_status" in source
    assert "core.request_run_stop" in source
    assert "st.line_chart" in source


def test_git_status_uses_two_second_domain_projection_fragment():
    source = Path("src/ui/app.py").read_text(encoding="utf-8")

    assert "@st.fragment(run_every=2.0)\ndef _render_live_sync_status" in source
    assert "core.get_sync_status" in source
