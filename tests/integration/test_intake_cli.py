from pathlib import Path

from src.agent.main import main


def test_intake_cli_builds_manifest(tmp_path):
    output_root = tmp_path / "standardized"

    exit_code = main(
        argv=[
            "intake",
            "tests/fixtures/data_intake/clear",
            "--output-root",
            str(output_root),
        ]
    )

    assert exit_code == 0
    assert Path(output_root / "clear" / "train_features.csv").exists()
    assert Path(output_root / "clear" / "train_labels.csv").exists()
