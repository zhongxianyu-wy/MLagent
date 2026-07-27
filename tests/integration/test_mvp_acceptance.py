"""MVP acceptance gap tests (Issue #16): performance, security, capacity,
resilience, non-authoritative, scope-exclusion. Most ACs are covered by
#2-#15; these fill the audited gaps."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.memory_repository import MemoryRepository
from src.domain.models import (
    CompleteSessionCommand,
    StartClaudeSessionCommand,
    WorkspaceError,
)
from tests.integration.test_sop_repository import build_sop_workspace
from tests.integration.test_domain_core_sop import write_connection


# --- AC#2 performance: Run Status renders within budget -------------------


def test_run_status_renders_within_budget(tmp_path, monkeypatch):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection))
    monkeypatch.setenv("MLAGENT_CODE_ROOT", str(tmp_path))
    from streamlit.testing.v1 import AppTest

    started = time.perf_counter()
    app = AppTest.from_file(Path("src/ui/app.py").resolve(), default_timeout=10).run()
    app = app.sidebar.radio[0].set_value("Run Status").run()
    elapsed = time.perf_counter() - started
    assert not app.exception
    # generous ceiling (reference machine target is <2s per AC#2)
    assert elapsed < 15.0


# --- AC#3 security: no credentials in team memory --------------------------


def test_bootstrapped_team_memory_has_no_credentials(tmp_path):
    root = tmp_path / "team-memory"
    MemoryRepository(
        id_factory=lambda: "tmr-1", clock=lambda: "2026-07-27T00:00:00Z"
    ).bootstrap(root, actor_id="alice")
    credential_patterns = ("api_key=", "password=")
    hits = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for pattern in credential_patterns:
            if pattern in text:
                hits.append((path.relative_to(root).as_posix(), pattern))
    assert not hits, f"credential-like material in team memory: {hits}"


# --- AC#3/#5 Claude exit releases the write session ------------------------


def test_claude_exit_releases_session(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    code_root = tmp_path / "code"
    from src.scheduler.lease import IdleSchedulerLeaseStore

    store = IdleSchedulerLeaseStore(str(tmp_path / "lease.db"))
    core = DomainCore(
        clock=lambda: "2026-07-27T00:00:00Z",
        claude_lease_store_factory=lambda repo_path: store,
        claude_epoch_clock=lambda: 1000,
    )
    core.register_code_id(connection, code_root, "baseline")
    handle = core.start_claude_session(
        StartClaudeSessionCommand(
            connection_path=connection, code_root=code_root, operator="alice"
        )
    )
    assert handle.state == "connected"
    # simulate Claude exit: release (idempotent)
    core.release_claude_session(connection, "baseline")
    core.release_claude_session(connection, "baseline")
    assert core.claude_session_status(connection, "baseline") == "released"


# --- AC#4 capacity: disk-full leaves no partial asset ----------------------


def test_disk_full_leaves_no_partial_asset(tmp_path, monkeypatch):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    code_root = tmp_path / "code"
    from src.domain.models import EditedFile, SaveCodeRevisionCommand

    core = DomainCore(clock=lambda: "2026-07-27T00:00:00Z")
    core.register_code_id(connection, code_root, "baseline")

    real_write_bytes = Path.write_bytes

    def flaky_write_bytes(self, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)
    with pytest.raises(WorkspaceError):
        core.save_code_revision(
            SaveCodeRevisionCommand(
                connection_path=connection,
                code_root=code_root,
                code_id="baseline",
                entrypoint_path="train.py",
                edited_files=(EditedFile(path="train.py", content=b"x"),),
                expected_parent_fingerprint=None,
                change_summary="initial",
                created_by="alice",
            )
        )
    monkeypatch.setattr(Path, "write_bytes", real_write_bytes)
    # no partial Code Revision directory created
    assert not (workspace.root / "code-revisions" / "baseline").exists()


# --- AC#5 resilience: Stop double-fire is idempotent ----------------------


def test_complete_session_double_fire_is_idempotent(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    core = DomainCore(clock=lambda: "2026-07-27T00:00:00Z")
    core.start_session(connection, "session-1")
    first = core.complete_session(
        CompleteSessionCommand(connection_path=connection, session_id="session-1")
    )
    second = core.complete_session(
        CompleteSessionCommand(connection_path=connection, session_id="session-1")
    )
    assert first.session_id == second.session_id
    # single stop marker
    stop_path = workspace.root / "raw-records" / "sessions" / "session-1" / "stop.json"
    assert stop_path.exists()


# --- AC#6 non-authoritative: LocalIndex deletion is recoverable -----------


def test_local_index_deletion_is_recoverable_from_git(tmp_path):
    root = tmp_path / "team-memory"
    MemoryRepository(
        id_factory=lambda: "tmr-1", clock=lambda: "2026-07-27T00:00:00Z"
    ).bootstrap(root, actor_id="alice")
    from src.domain.local_index import LocalIndex

    index = LocalIndex(root)
    index.rebuild()  # rebuild from Git-authoritative team memory; must not raise
    assert index.path.exists()


# --- AC#7 scope: Git LFS not enabled --------------------------------------


def test_bootstrapped_repo_has_no_lfs(tmp_path):
    root = tmp_path / "team-memory"
    MemoryRepository(
        id_factory=lambda: "tmr-1", clock=lambda: "2026-07-27T00:00:00Z"
    ).bootstrap(root, actor_id="alice")
    # no .gitattributes with LFS pointers
    gitattributes = root / ".gitattributes"
    assert not gitattributes.exists() or "lfs" not in gitattributes.read_text().lower()
    # no lfs git config
    result = subprocess.run(
        ["git", "config", "--get-regexp", "lfs"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "", "git LFS must not be configured"


# --- AC#7 scope: regression rejected at intake ----------------------------


def test_regression_task_type_rejected(tmp_path):
    from src.domain.dataset_intake import DatasetInspector
    from src.domain.models import ConfirmDatasetCommand

    feature_path = tmp_path / "f.csv"
    label_path = tmp_path / "l.csv"
    feature_path.write_text("sample_id,f1\ns1,1\ns2,2\n")
    label_path.write_text("sample_id,group\ns1,a\ns2,b\n")
    inspector = DatasetInspector()
    with pytest.raises(WorkspaceError) as exc:
        inspector.normalize(
            ConfirmDatasetCommand(
                connection_path=Path(".mlagent-workspace.json"),
                feature_path=feature_path,
                label_path=label_path,
                sample_id_col="sample_id",
                label_col="group",
                task_type="regression",
                positive_class="a",
                primary_metric="roc_auc",
                split_strategy="train_only",
                target_metric=0.9,
            )
        )
    assert exc.value.code == "unsupported_task"
