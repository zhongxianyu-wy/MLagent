"""Integration tests for notebook import via DomainCore (Issue #9)."""
import hashlib
import json
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.memory_repository import MemoryRepository
from src.domain.models import ImportNotebookCommand

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "notebooks"


def _build_workspace(tmp_path: Path):
    """Bootstrap a minimal team-memory workspace and return (core, connection_path)."""
    repo_path = tmp_path / "team_memory"
    MemoryRepository(
        id_factory=lambda: "tmr_test",
        clock=lambda: "2026-07-20T00:00:00Z",
    ).bootstrap(repo_path, actor_id="tester")
    connection_path = tmp_path / ".mlagent_workspace.json"
    connection_path.write_text(json.dumps({
        "repository_path": str(repo_path),
        "actor_id": "tester",
        "workspace_name": "test",
        "remote_url": None,
    }), encoding="utf-8")
    return DomainCore(), connection_path, repo_path


def _import_cmd(conn: Path, nb: str, repo: Path) -> ImportNotebookCommand:
    return ImportNotebookCommand(
        connection_path=conn,
        notebook_path=FIXTURES / nb,
        source_description="unit test",
        dataset_id="ds1",
        dataset_version="1",
        code_root=repo,
    )


def test_import_clean_notebook_preserves_original_and_fingerprint(tmp_path):
    core, conn, repo = _build_workspace(tmp_path)
    nb_path = FIXTURES / "clean_baseline.ipynb"
    original_bytes = nb_path.read_bytes()
    expected_fp = hashlib.sha256(original_bytes).hexdigest()

    snapshot = core.import_notebook(_import_cmd(conn, "clean_baseline.ipynb", repo))

    assert snapshot.content_fingerprint == expected_fp
    assert snapshot.state == "preserved"
    assert snapshot.importer == "tester"
    stored = repo / "notebooks" / "originals" / f"{expected_fp[:12]}.ipynb"
    assert stored.exists()
    assert stored.read_bytes() == original_bytes
    assert len(list((repo / "notebooks" / "imports").iterdir())) >= 1


def test_import_parse_report_has_components(tmp_path):
    core, conn, repo = _build_workspace(tmp_path)
    snapshot = core.import_notebook(_import_cmd(conn, "clean_baseline.ipynb", repo))
    report = snapshot.parse_report
    assert any("pandas" in d for d in report.detected_dependencies)
    assert report.detected_model is not None
    assert any("roc_auc" in m for m in report.detected_metrics)
    assert report.detected_split is not None


def test_import_blocked_on_missing_deps(tmp_path):
    core, conn, repo = _build_workspace(tmp_path)
    snapshot = core.import_notebook(_import_cmd(conn, "missing_deps.ipynb", repo))
    assert snapshot.state == "parse_blocked"
    blocking = [w for w in snapshot.parse_report.warnings if w.blocking]
    assert any(w.kind == "missing_dependency" for w in blocking)


def test_import_blocked_on_unclear_randomness(tmp_path):
    core, conn, repo = _build_workspace(tmp_path)
    snapshot = core.import_notebook(_import_cmd(conn, "no_seed.ipynb", repo))
    assert snapshot.state == "parse_blocked"
    blocking = [w for w in snapshot.parse_report.warnings if w.blocking]
    assert any(w.kind == "unclear_randomness" for w in blocking)


def test_import_blocked_on_interactive(tmp_path):
    core, conn, repo = _build_workspace(tmp_path)
    snapshot = core.import_notebook(_import_cmd(conn, "interactive.ipynb", repo))
    assert snapshot.state == "parse_blocked"
    blocking = [w for w in snapshot.parse_report.warnings if w.blocking]
    assert any(w.kind == "interactive_step" for w in blocking)


def test_hidden_path_warning_non_blocking(tmp_path):
    core, conn, repo = _build_workspace(tmp_path)
    snapshot = core.import_notebook(_import_cmd(conn, "hidden_paths.ipynb", repo))
    path_warnings = [w for w in snapshot.parse_report.warnings if w.kind == "hidden_path"]
    assert len(path_warnings) >= 1
    assert all(not w.blocking for w in path_warnings)


def test_get_notebook_import(tmp_path):
    core, conn, repo = _build_workspace(tmp_path)
    snapshot = core.import_notebook(_import_cmd(conn, "clean_baseline.ipynb", repo))
    record = core.get_notebook_import(conn, snapshot.asset_id)
    assert record["asset_id"] == snapshot.asset_id
    assert record["content_fingerprint"] == snapshot.content_fingerprint


def test_list_notebook_imports(tmp_path):
    core, conn, repo = _build_workspace(tmp_path)
    core.import_notebook(_import_cmd(conn, "clean_baseline.ipynb", repo))
    core.import_notebook(_import_cmd(conn, "missing_deps.ipynb", repo))
    imports = core.list_notebook_imports(conn)
    assert len(imports) == 2
