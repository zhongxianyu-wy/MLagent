"""Unit tests for Code Revision domain models (Issue #11 T1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.models import (
    CandidateCodeFile,
    CodeFileDelta,
    CodeRevisionDiff,
    CodeRevisionSnapshot,
    CodeReviewSnapshot,
    EditedFile,
    ManagedFileEntry,
    SaveCodeRevisionCommand,
)


_SHA = "a" * 64
_SHA_B = "b" * 64


def _file(path: str = "train.py", sha: str = _SHA, size: int = 10) -> CandidateCodeFile:
    return CandidateCodeFile(path=path, sha256=sha, size_bytes=size)


def _revision(**overrides) -> CodeRevisionSnapshot:
    version = overrides.get("version", 1)
    base: dict = dict(
        asset_id=f"baseline-v{version}",
        asset_path=f"code-revisions/baseline/v{version:04d}/manifest.json",
        code_id="baseline",
        version=version,
        revision_fingerprint=_SHA,
        parent_revision_id=None,
        parent_revision_fingerprint=None,
        code_fingerprint=_SHA,
        entrypoint_path="train.py",
        files=(_file(),),
        origin="human",
        source_run_id=None,
        source_instance_id=None,
        change_summary="",
        created_at="2026-07-22T00:00:00Z",
        created_by="alice",
    )
    base.update(overrides)
    return CodeRevisionSnapshot(**base)


# --- CodeRevisionSnapshot: valid construction -------------------------------


def test_version_one_constructs_without_parent():
    rev = _revision()
    assert rev.version == 1
    assert rev.parent_revision_id is None
    assert rev.asset_type == "code_revision"
    assert rev.code_fingerprint == rev.revision_fingerprint


def test_higher_version_constructs_with_parent_and_change_summary():
    rev = _revision(
        version=2,
        asset_id="baseline-v2",
        asset_path="code-revisions/baseline/v0002/manifest.json",
        parent_revision_id="baseline-v1",
        parent_revision_fingerprint=_SHA,
        revision_fingerprint=_SHA_B,
        code_fingerprint=_SHA_B,
        change_summary="switched to RF",
    )
    assert rev.version == 2
    assert rev.parent_revision_id == "baseline-v1"


def test_to_dict_round_trips_core_fields():
    rev = _revision()
    payload = rev.to_dict()
    assert payload["asset_type"] == "code_revision"
    assert payload["code_id"] == "baseline"
    assert payload["files"] == [{"path": "train.py", "sha256": _SHA, "size_bytes": 10}]


# --- CodeRevisionSnapshot: validation gates --------------------------------


def test_version_one_rejects_parent_id():
    with pytest.raises(ValueError, match="version 1 cannot have parent_revision_id"):
        _revision(parent_revision_id="baseline-v1")


def test_version_one_rejects_parent_fingerprint():
    with pytest.raises(ValueError, match="version 1 cannot have parent_revision_fingerprint"):
        _revision(parent_revision_fingerprint=_SHA)


def test_higher_version_requires_change_summary():
    with pytest.raises(ValueError, match="change_summary"):
        _revision(
            version=2,
            parent_revision_id="baseline-v1",
            parent_revision_fingerprint=_SHA,
            change_summary="",
        )


def test_higher_version_requires_parent_chain():
    with pytest.raises(ValueError, match="parent_revision_id"):
        _revision(version=2, change_summary="x")


def test_origin_must_be_human_agent_or_system():  # AC#7
    with pytest.raises(ValueError, match="origin"):
        _revision(origin="robot")


def test_entrypoint_must_be_a_listed_python_file():
    with pytest.raises(ValueError, match="entrypoint"):
        _revision(entrypoint_path="missing.py")
    with pytest.raises(ValueError, match="entrypoint"):
        _revision(entrypoint_path="README.md", files=(_file("README.md"),))


def test_revision_requires_at_least_one_file():
    with pytest.raises(ValueError, match="at least one file"):
        _revision(files=())


def test_code_fingerprint_must_mirror_revision_fingerprint():
    with pytest.raises(ValueError, match="code_fingerprint"):
        _revision(revision_fingerprint=_SHA, code_fingerprint=_SHA_B)


def test_revision_rejects_tampered_asset_type():
    with pytest.raises(ValueError, match="asset_type"):
        _revision(asset_type="not_code_revision")


# --- Read models + command --------------------------------------------------


def test_managed_file_entry_constructs():
    entry = ManagedFileEntry(path="train.py", size_bytes=10, sha256=_SHA, is_entrypoint=True)
    assert entry.is_entrypoint is True


def test_code_file_delta_constructs():
    delta = CodeFileDelta(path="train.py", status="modified", diff_text="--- a\n+++ b\n")
    assert delta.status == "modified"


def test_code_review_snapshot_constructs():
    active = _revision()
    snap = CodeReviewSnapshot(
        code_id="baseline",
        code_root="workspace/code",
        managed_root_ok=True,
        files=(ManagedFileEntry(path="train.py", size_bytes=10, sha256=_SHA, is_entrypoint=True),),
        active_revision=active,
        history=(active,),
        workspace_changed=False,
        active_instance_refs=(("run-1", "inst-1"),),
    )
    assert snap.active_revision.version == 1
    assert snap.active_instance_refs == (("run-1", "inst-1"),)


def test_code_revision_diff_constructs():
    diff = CodeRevisionDiff(
        code_id="baseline",
        parent_version=1,
        child_version=2,
        files=(CodeFileDelta(path="train.py", status="modified", diff_text=""),),
    )
    assert diff.child_version == 2


def test_save_code_revision_command_constructs():
    cmd = SaveCodeRevisionCommand(
        connection_path=Path(".mlagent-workspace.json"),
        code_root=Path("code"),
        code_id="baseline",
        entrypoint_path="train.py",
        edited_files=(EditedFile(path="train.py", content=b"print('hi')\n"),),
        expected_parent_fingerprint=None,
        change_summary="initial",
        created_by="alice",
        origin="human",
    )
    assert cmd.origin == "human"
    assert cmd.edited_files[0].content == b"print('hi')\n"


def test_save_command_origin_defaults_to_human():
    cmd = SaveCodeRevisionCommand(
        connection_path=Path(".mlagent-workspace.json"),
        code_root=Path("code"),
        code_id="baseline",
        entrypoint_path="train.py",
        edited_files=(EditedFile(path="train.py", content=b"x"),),
        expected_parent_fingerprint=None,
        change_summary="initial",
        created_by="alice",
    )
    assert cmd.origin == "human"
