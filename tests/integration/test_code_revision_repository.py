"""Integration tests for CodeRevisionRepository (Issue #11 T2)."""
from __future__ import annotations

import hashlib
import json

import pytest

from src.domain.code_revision_repository import (
    CodeRevisionRepository,
    compute_code_fingerprint,
)
from src.domain.models import (
    CapacityStatus,
    CandidateCodeFile,
    WorkspaceError,
)


def _capacity() -> CapacityStatus:
    return CapacityStatus(
        state="ok",
        bytes_used=0,
        largest_file_bytes=0,
        max_file_bytes=10_000_000,
        max_repository_bytes=100_000_000,
    )


def _files_bytes(**overrides) -> dict[str, bytes]:
    base = {"train.py": b"import os\nprint('train')\n"}
    base.update(overrides)
    return base


def _candidate_files(files_bytes: dict[str, bytes]) -> tuple[CandidateCodeFile, ...]:
    return tuple(
        CandidateCodeFile(
            path=path,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )
        for path, content in sorted(files_bytes.items())
    )


def _fingerprint(files_bytes: dict[str, bytes]) -> str:
    return compute_code_fingerprint(_candidate_files(files_bytes))


def _repo(tmp_path) -> CodeRevisionRepository:
    return CodeRevisionRepository(
        repository_path=tmp_path,
        clock=lambda: "2026-07-22T00:00:00Z",
    )


def _create_kwargs(files_bytes, **overrides):
    kwargs = dict(
        code_id="baseline",
        code_fingerprint=_fingerprint(files_bytes),
        entrypoint_path="train.py",
        files=_candidate_files(files_bytes),
        files_bytes=files_bytes,
        parent_revision_id=None,
        parent_revision_fingerprint=None,
        change_summary="",
        origin="human",
        source_run_id=None,
        source_instance_id=None,
        created_by="alice",
        capacity=_capacity(),
    )
    kwargs.update(overrides)
    return kwargs


def test_create_first_version_writes_manifest_and_files(tmp_path):
    repo = _repo(tmp_path)
    fb = _files_bytes()
    snap = repo.create(**_create_kwargs(fb))
    assert snap.version == 1
    assert snap.asset_path == "code-revisions/baseline/v0001/manifest.json"
    assert (tmp_path / "code-revisions/baseline/v0001/manifest.json").exists()
    assert (
        (tmp_path / "code-revisions/baseline/v0001/files/train.py").read_bytes()
        == fb["train.py"]
    )


def test_repeated_save_with_same_fingerprint_returns_existing_v1(tmp_path):
    repo = _repo(tmp_path)
    fb = _files_bytes()
    first = repo.create(**_create_kwargs(fb))
    second = repo.create(**_create_kwargs(fb))
    assert second.version == 1
    assert second.asset_id == first.asset_id
    assert not (tmp_path / "code-revisions/baseline/v0002").exists()


def test_changed_inputs_append_version_without_rewriting_v1(tmp_path):
    repo = _repo(tmp_path)
    fb1 = _files_bytes()
    v1 = repo.create(**_create_kwargs(fb1))
    v1_bytes = (tmp_path / v1.asset_path).read_bytes()

    fb2 = _files_bytes(**{"train.py": b"import os\nprint('v2')\n"})
    v2 = repo.create(
        **_create_kwargs(
            fb2,
            parent_revision_id=v1.asset_id,
            parent_revision_fingerprint=v1.revision_fingerprint,
            change_summary="tweak",
            origin="agent",
            created_by="bob",
        )
    )
    assert v2.version == 2
    assert v2.parent_revision_id == v1.asset_id
    assert (tmp_path / v1.asset_path).read_bytes() == v1_bytes  # v1 untouched


def test_tampered_code_revision_file_is_rejected_on_reload(tmp_path):
    repo = _repo(tmp_path)
    repo.create(**_create_kwargs(_files_bytes()))
    (tmp_path / "code-revisions/baseline/v0001/files/train.py").write_bytes(b"TAMPERED")
    with pytest.raises(WorkspaceError) as exc:
        repo.load("baseline", 1)
    assert exc.value.code == "code_revision_fingerprint_mismatch"


def test_load_rejects_tampered_manifest_fingerprint(tmp_path):
    repo = _repo(tmp_path)
    snap = repo.create(**_create_kwargs(_files_bytes()))
    path = tmp_path / snap.asset_path
    manifest = json.loads(path.read_text())
    manifest["change_summary"] = "sneaky edit"
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    with pytest.raises(WorkspaceError) as exc:
        repo.load("baseline", 1)
    assert exc.value.code == "code_revision_fingerprint_mismatch"


def test_capacity_failure_leaves_no_partial_code_revision(tmp_path):
    repo = _repo(tmp_path)
    fb = _files_bytes()
    tiny = CapacityStatus(
        state="ok",
        bytes_used=0,
        largest_file_bytes=0,
        max_file_bytes=5,  # train.py is larger
        max_repository_bytes=100_000_000,
    )
    with pytest.raises(WorkspaceError) as exc:
        repo.create(**_create_kwargs(fb, capacity=tiny))
    assert exc.value.code == "file_too_large"
    assert not (tmp_path / "code-revisions/baseline").exists()


def test_manifest_records_origin_human_agent_system(tmp_path):
    repo = _repo(tmp_path)
    for origin in ("human", "agent", "system"):
        fb = _files_bytes(**{"train.py": f"# {origin}\nprint('x')\n".encode()})
        snap = repo.create(**_create_kwargs(fb, code_id=f"fam-{origin}", origin=origin))
        manifest = json.loads((tmp_path / snap.asset_path).read_text())
        assert manifest["origin"] == origin


def test_manifest_does_not_store_editor_input_content(tmp_path):
    repo = _repo(tmp_path)
    snap = repo.create(**_create_kwargs(_files_bytes(), change_summary="initial"))
    manifest = json.loads((tmp_path / snap.asset_path).read_text())
    allowed = {
        "asset_type", "asset_id", "schema_version", "code_id", "version",
        "revision_fingerprint", "code_fingerprint", "parent_revision_id",
        "parent_revision_fingerprint", "entrypoint_path", "origin",
        "source_run_id", "source_instance_id", "change_summary",
        "files", "created_at", "created_by", "manifest_fingerprint",
        "agent_prompt_hash", "agent_tool_summary",
    }
    assert set(manifest.keys()) <= allowed
    assert not any(
        key in manifest for key in ("content", "text", "body", "editor_input", "draft")
    )


def test_list_revisions_returns_versions_sorted_descending(tmp_path):
    repo = _repo(tmp_path)
    fb1 = _files_bytes()
    v1 = repo.create(**_create_kwargs(fb1))
    fb2 = _files_bytes(**{"train.py": b"# v2\nprint('v2')\n"})
    repo.create(
        **_create_kwargs(
            fb2,
            parent_revision_id=v1.asset_id,
            parent_revision_fingerprint=v1.revision_fingerprint,
            change_summary="tweak",
        )
    )
    history = repo.list_revisions("baseline")
    assert [r.version for r in history] == [2, 1]


def test_latest_returns_none_when_family_absent(tmp_path):
    repo = _repo(tmp_path)
    assert repo.latest("baseline") is None
