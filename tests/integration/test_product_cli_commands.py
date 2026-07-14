from pathlib import Path

from src.agent.main import main


def test_research_without_service_returns_actionable_error():
    assert main(["research", "--target", "paper"]) != 0


def test_unknown_command_returns_nonzero():
    assert main(["not-a-command"]) != 0


def test_explore_command_runs_real_service_after_intake(tmp_path):
    intake_code = main(
        [
            "intake",
            "tests/fixtures/data_intake/clear",
            "--output-root",
            str(tmp_path / "standardized"),
            "--split-strategy",
            "train_only",
        ]
    )
    assert intake_code == 0
    manifest_path = tmp_path / "standardized" / "clear" / "manifest.json"
    assert manifest_path.exists()

    explore_code = main(
        [
            "explore",
            "--manifest-path",
            str(manifest_path),
            "--max-rounds",
            "1",
            "--output-root",
            str(tmp_path / "outputs"),
        ]
    )

    assert explore_code == 0
    assert Path(tmp_path, "outputs", "explore-clear", "rounds.jsonl").exists()


def test_explore_command_returns_nonzero_when_kfold_is_impossible_after_split(tmp_path):
    intake_code = main(
        [
            "intake",
            "tests/fixtures/data_intake/clear",
            "--output-root",
            str(tmp_path / "standardized"),
            "--split-strategy",
            "random",
            "--split-ratio",
            "0.4",
        ]
    )
    assert intake_code == 0
    manifest_path = tmp_path / "standardized" / "clear" / "manifest.json"

    exit_code = main(
        [
            "explore",
            "--manifest-path",
            str(manifest_path),
            "--max-rounds",
            "1",
            "--output-root",
            str(tmp_path / "outputs"),
        ]
    )

    assert exit_code == 2
