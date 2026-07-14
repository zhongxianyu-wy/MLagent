from src.agent.main import main


def test_distill_cli_invokes_distill_factory_for_notebook():
    requests = []

    exit_code = main(
        argv=[
            "distill",
            "--notebook",
            "tests/fixtures/notebooks/skill_source.ipynb",
        ],
        distill_factory=lambda request: requests.append(request) or 0,
    )

    assert exit_code == 0
    assert requests == [
        {
            "source_type": "notebook",
            "source": "tests/fixtures/notebooks/skill_source.ipynb",
        }
    ]
