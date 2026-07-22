"""Integration tests for DomainCore Code Review methods (Issue #11 T3)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.memory_repository import MemoryRepository
from src.domain.models import (
    EditedFile,
    SaveCodeRevisionCommand,
    WorkspaceError,
)


def _workspace(tmp_path: Path):
    root = tmp_path / "team-memory"
    MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-22T00:00:00Z",
    ).bootstrap(root, actor_id="alice")
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "train.py").write_bytes(
        b"def build_estimator(context):\n    return context\n"
    )
    connection = tmp_path / ".mlagent-workspace.json"
    connection.write_text(
        json.dumps({"repository_path": str(root), "actor_id": "alice"})
    )
    return connection, code_root, root


def _core() -> DomainCore:
    return DomainCore(clock=lambda: "2026-07-22T00:00:00Z")


def _save(connection, code_root, code_id="baseline", *, content=None,
          expected=None, change_summary="initial", origin="human"):
    train = code_root / "train.py"
    return _core().save_code_revision(
        SaveCodeRevisionCommand(
            connection_path=connection,
            code_root=code_root,
            code_id=code_id,
            entrypoint_path="train.py",
            edited_files=(EditedFile(path="train.py", content=content or train.read_bytes()),),
            expected_parent_fingerprint=expected,
            change_summary=change_summary,
            created_by="alice",
            origin=origin,
        )
    )


def _seed_instance(root: Path, run_id: str, instance_id: str, code_fingerprint: str) -> None:
    inst_dir = root / "runs" / run_id / "instances" / instance_id
    inst_dir.mkdir(parents=True)
    (inst_dir / "manifest.json").write_text(
        json.dumps(
            {
                "asset_type": "training_instance",
                "run_id": run_id,
                "instance_id": instance_id,
                "code_fingerprint": code_fingerprint,
            }
        )
    )


# --- AC#1: managed file listing + jail -------------------------------------


def test_list_managed_files_returns_only_python_under_root(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    (code_root / "helper.py").write_bytes(b"x = 1\n")
    (code_root / "README.md").write_bytes(b"docs")  # not .py
    (code_root / "__pycache__").mkdir()
    (code_root / "__pycache__" / "junk.py").write_bytes(b"junk")
    files = _core().list_managed_files(connection, code_root)
    paths = {f.path for f in files}
    assert "train.py" in paths
    assert "helper.py" in paths
    assert all(not p.startswith("__pycache__") for p in paths)
    assert all(not p.endswith(".md") for p in paths)


def test_list_managed_files_blocks_paths_outside_managed_root(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    outside = tmp_path.parent / "outside-code-root"
    with pytest.raises(WorkspaceError) as exc:
        _core().list_managed_files(connection, outside)
    assert exc.value.code == "unmanaged_code_root"


def test_read_managed_file_returns_bytes_and_blocks_escape(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core = _core()
    content = core.read_managed_file(connection, code_root, "train.py")
    assert b"build_estimator" in content
    with pytest.raises(WorkspaceError):
        core.read_managed_file(connection, code_root, "../outside.py")


# --- code_id binding -------------------------------------------------------


def test_resolve_code_id_none_then_register_then_resolve(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core = _core()
    assert core.resolve_code_id(connection, code_root) is None
    core.register_code_id(connection, code_root, "baseline")
    assert core.resolve_code_id(connection, code_root) == "baseline"


# --- AC#3: save → new version, never mutate active -------------------------


def test_save_creates_first_revision_and_tracks_history(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    v1 = _save(connection, code_root, expected=None)
    assert v1.version == 1
    assert v1.parent_revision_id is None
    history = _core().list_code_revisions(connection, "baseline")
    assert [r.version for r in history] == [1]


def test_save_creates_new_version_without_mutating_parent(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    v1 = _save(connection, code_root, expected=None)
    v1_manifest_bytes = (root / v1.asset_path).read_bytes()
    v1_fingerprint = v1.revision_fingerprint

    (code_root / "train.py").write_bytes(b"def build_estimator(c):\n    return 2\n")
    v2 = _save(
        connection, code_root,
        content=(code_root / "train.py").read_bytes(),
        expected=v1_fingerprint,
        change_summary="tweak estimator",
        origin="agent",
    )
    assert v2.version == 2
    assert v2.parent_revision_id == v1.asset_id
    assert v2.parent_revision_fingerprint == v1_fingerprint
    # v1 untouched
    assert (root / v1.asset_path).read_bytes() == v1_manifest_bytes


# --- AC#5: auto-refresh + explicit conflict resolve ------------------------


def test_workspace_change_is_detected_at_read_time(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core = _core()
    core.register_code_id(connection, code_root, "baseline")
    _save(connection, code_root, expected=None)
    snap = core.get_code_review(connection, code_root, "baseline")
    assert snap.workspace_changed is False
    # external edit to workspace file
    (code_root / "train.py").write_bytes(b"# external change\n")
    snap2 = core.get_code_review(connection, code_root, "baseline")
    assert snap2.workspace_changed is True


def test_concurrent_save_raises_stale_code_revision(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    v1 = _save(connection, code_root, expected=None)
    f1 = v1.revision_fingerprint
    # first follow-up save succeeds → v2
    (code_root / "train.py").write_bytes(b"v = 2\n")
    _save(connection, code_root, content=(code_root / "train.py").read_bytes(),
          expected=f1, change_summary="v2")
    # second actor still acting on v1 → stale
    (code_root / "train.py").write_bytes(b"v = 3\n")
    with pytest.raises(WorkspaceError) as exc:
        _save(connection, code_root, content=(code_root / "train.py").read_bytes(),
              expected=f1, change_summary="also from v1")
    assert exc.value.code == "stale_code_revision"
    # v1 intact
    assert _core().list_code_revisions(connection, "baseline")[0].version == 2


# --- AC#2: Active/Frozen derived from instance reference -------------------


def test_active_revision_referenced_by_instance_is_marked_frozen(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core = _core()
    core.register_code_id(connection, code_root, "baseline")
    v1 = _save(connection, code_root, expected=None)
    _seed_instance(root, "run-1", "inst-1", v1.revision_fingerprint)
    snap = core.get_code_review(connection, code_root, "baseline")
    assert snap.active_instance_refs == (("run-1", "inst-1"),)
    assert snap.active_revision.version == 1


# --- AC#4: diff / history / origin / author / time / related run -----------


def test_diff_code_revisions_reports_modified_file(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    v1 = _save(connection, code_root, expected=None)
    (code_root / "train.py").write_bytes(b"def build_estimator(c):\n    return 99\n")
    v2 = _save(connection, code_root, content=(code_root / "train.py").read_bytes(),
               expected=v1.revision_fingerprint, change_summary="tweak")
    diff = _core().diff_code_revisions(connection, "baseline", 1, 2)
    assert diff.child_version == 2
    delta = next(d for d in diff.files if d.path == "train.py")
    assert delta.status == "modified"
    assert "build_estimator" in delta.diff_text


def test_history_lists_origin_author_time_and_related_run(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    v1 = _save(connection, code_root, expected=None, origin="human", change_summary="init")
    (code_root / "train.py").write_bytes(b"x = 2\n")
    v2 = _save(connection, code_root, content=(code_root / "train.py").read_bytes(),
               expected=v1.revision_fingerprint, change_summary="agent tweak", origin="agent")
    _seed_instance(root, "run-9", "inst-9", v2.revision_fingerprint)
    history = _core().list_code_revisions(connection, "baseline")
    assert history[0].origin == "agent"
    assert history[0].change_summary == "agent tweak"
    assert history[1].origin == "human"
    snap = _core().get_code_review(connection, code_root, "baseline")
    assert ("run-9", "inst-9") in snap.active_instance_refs


# --- AC#8: diff against older version (rollback view) ----------------------


def test_diff_against_older_version_renders_rollback_view(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    v1 = _save(connection, code_root, expected=None)
    (code_root / "train.py").write_bytes(b"x = 2\n")
    v2 = _save(connection, code_root, content=(code_root / "train.py").read_bytes(),
               expected=v1.revision_fingerprint, change_summary="v2")
    (code_root / "train.py").write_bytes(b"x = 3\n")
    v3 = _save(connection, code_root, content=(code_root / "train.py").read_bytes(),
               expected=v2.revision_fingerprint, change_summary="v3")
    diff = _core().diff_code_revisions(connection, "baseline", 1, 3)
    assert diff.parent_version == 1 and diff.child_version == 3
    delta = next(d for d in diff.files if d.path == "train.py")
    assert delta.status == "modified"
    assert delta.diff_text  # non-empty
