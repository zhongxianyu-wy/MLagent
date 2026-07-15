from pathlib import Path

from src.agent.main import main


def test_quickstart_cli_paths_are_callable(tmp_path, confirmed_domain_core):
    standardized = tmp_path / "standardized"
    requests = []

    assert main(
        [
            "intake",
            "tests/fixtures/data_intake/clear",
            "--output-root",
            str(standardized),
        ]
    ) == 0
    assert main(
        [
            "explore",
            "--dataset-id",
            "ds-clear",
            "--dataset-version",
            "1",
            "--max-rounds",
            "1",
        ],
        explore_factory=lambda request: requests.append(("explore", request)) or 0,
        domain_core_factory=lambda: confirmed_domain_core,
    ) == 0
    assert main(
        [
            "reproduce",
            "--skill-id",
            "ngs-xgboost-baseline",
            "--dataset-id",
            "ds-clear",
            "--dataset-version",
            "1",
        ],
        reproduce_factory=lambda request: requests.append(("reproduce", request)) or 0,
        domain_core_factory=lambda: confirmed_domain_core,
    ) == 0

    assert Path(standardized / "clear" / "train_features.csv").exists()
    assert [name for name, _ in requests] == ["explore", "reproduce"]


def test_root_spec_documents_are_synced_with_canonical_files():
    assert Path("specs/plan.md").read_text() == Path(
        "specs/001-ngs-ml-agent/plan.md"
    ).read_text()
    assert Path("specs/tasks.md").read_text() == Path(
        "specs/001-ngs-ml-agent/tasks.md"
    ).read_text()
