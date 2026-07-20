"""Unit tests for the notebook parser (Issue #9)."""
from pathlib import Path

from src.domain.notebook_parser import parse_notebook
from src.domain.models import NotebookParseWarning

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "notebooks"


def test_clean_baseline_parses_all_components():
    report = parse_notebook(FIXTURES / "clean_baseline.ipynb")
    assert report.content_fingerprint  # SHA-256
    assert len(report.cells) >= 1
    assert any("pandas" in d for d in report.detected_dependencies)
    assert any("sklearn.ensemble" in d or "RandomForest" in d for d in report.detected_dependencies)
    assert report.detected_model is not None
    assert any("random_state" in r for r in report.detected_randomness)
    assert report.detected_split is not None
    assert any("roc_auc" in m for m in report.detected_metrics)
    assert any("data/train.csv" in p for p in report.detected_data_paths)


def test_missing_deps_produces_blocking_warning():
    report = parse_notebook(FIXTURES / "missing_deps.ipynb")
    blocking = [w for w in report.warnings if w.blocking]
    assert any(w.kind == "missing_dependency" for w in blocking)


def test_no_seed_produces_randomness_warning():
    report = parse_notebook(FIXTURES / "no_seed.ipynb")
    randomness_warnings = [w for w in report.warnings if w.kind == "unclear_randomness"]
    assert len(randomness_warnings) >= 1
    assert all(w.blocking for w in randomness_warnings)


def test_hidden_paths_produces_warning():
    report = parse_notebook(FIXTURES / "hidden_paths.ipynb")
    path_warnings = [w for w in report.warnings if w.kind in ("hidden_path", "non_portable_path")]
    assert len(path_warnings) >= 1


def test_interactive_steps_produce_warning():
    report = parse_notebook(FIXTURES / "interactive.ipynb")
    interactive = [w for w in report.warnings if w.kind == "interactive_step"]
    assert len(interactive) >= 1
    assert all(w.blocking for w in interactive)


def test_fingerprint_is_stable():
    r1 = parse_notebook(FIXTURES / "clean_baseline.ipynb")
    r2 = parse_notebook(FIXTURES / "clean_baseline.ipynb")
    assert r1.content_fingerprint == r2.content_fingerprint
    assert len(r1.content_fingerprint) == 64  # SHA-256 hex
