from src.agent.main import main


def test_research_cli_invokes_research_factory_for_target():
    requests = []

    exit_code = main(
        argv=["research", "--target", "https://example.test/paper"],
        research_factory=lambda request: requests.append(request) or 0,
    )

    assert exit_code == 0
    assert requests == [{"mode": "target", "target": "https://example.test/paper"}]
