from pathlib import Path

from src.agent.main import main


def test_product_cli_smoke_intake_then_explore(tmp_path):
    standardized = tmp_path / "standardized"
    outputs = tmp_path / "outputs"

    assert main(
        [
            "intake",
            "tests/fixtures/data_intake/clear",
            "--output-root",
            str(standardized),
            "--split-strategy",
            "train_only",
        ]
    ) == 0
    manifest_path = standardized / "clear" / "manifest.json"
    assert manifest_path.exists()

    assert main(
        [
            "explore",
            "--manifest-path",
            str(manifest_path),
            "--max-rounds",
            "1",
            "--output-root",
            str(outputs),
        ]
    ) == 0

    run_dir = outputs / "explore-clear"
    assert (run_dir / "run_summary.json").exists()
    assert (run_dir / "rounds.jsonl").exists()
    assert (run_dir / "best_config.json").exists()
    assert (run_dir / "metrics.json").exists()


def test_quickstart_documents_product_cli_commands_and_outputs():
    quickstart = Path("specs/001-ngs-ml-agent/quickstart.md").read_text()

    assert "--output-root" in quickstart
    assert "--manifest-path" in quickstart
    assert "run_summary.json" in quickstart
    assert "rounds.jsonl" in quickstart
    assert "best_config.json" in quickstart
