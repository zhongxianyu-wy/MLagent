"""Integration tests for DomainCore Claude session methods (Issue #12 T4)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domain.claude_cli_executor import DeterministicClaudeExecutor
from src.domain.core import DomainCore
from src.domain.memory_repository import MemoryRepository
from src.domain.models import (
    CaptureClaudeChangesCommand,
    ClaudeCliResult,
    ClaudeStreamEvent,
    EditedFile,
    SaveCodeRevisionCommand,
    StartClaudeSessionCommand,
    WorkspaceError,
)
from src.scheduler.lease import IdleSchedulerLeaseStore


_SHA = "a" * 64


def _workspace(tmp_path: Path):
    root = tmp_path / "team-memory"
    MemoryRepository(
        id_factory=lambda: "tmr-1", clock=lambda: "2026-07-22T00:00:00Z"
    ).bootstrap(root, actor_id="alice")
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "train.py").write_bytes(b"def build_estimator(c):\n    return c\n")
    connection = tmp_path / ".mlagent-workspace.json"
    connection.write_text(
        json.dumps({"repository_path": str(root), "actor_id": "alice"})
    )
    return connection, code_root, root


def _result(**over) -> ClaudeCliResult:
    base = dict(
        state="completed",
        tool_action_summary="Edited train.py",
        touched_files=("train.py",),
        started_at="2026-07-22T00:00:00Z",
        ended_at="2026-07-22T00:01:00Z",
    )
    base.update(over)
    return ClaudeCliResult(**base)


def _core(tmp_path, *, executor=None, epoch=1000):
    holder = [epoch]
    store = IdleSchedulerLeaseStore(str(tmp_path / "lease.db"))
    core = DomainCore(
        clock=lambda: "2026-07-22T00:00:00Z",
        claude_executor_factory=executor
        or (lambda: DeterministicClaudeExecutor(events=(), result=_result())),
        claude_lease_store_factory=lambda repo_path: store,
        claude_epoch_clock=lambda: holder[0],
        claude_lease_ttl_seconds=100,
    )
    return core, holder


def _seed_instance(root: Path, run_id: str, instance_id: str, code_fingerprint: str):
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


def _save_v1(core, connection, code_root):
    return core.save_code_revision(
        SaveCodeRevisionCommand(
            connection_path=connection,
            code_root=code_root,
            code_id="baseline",
            entrypoint_path="train.py",
            edited_files=(EditedFile(path="train.py", content=(code_root / "train.py").read_bytes()),),
            expected_parent_fingerprint=None,
            change_summary="initial",
            created_by="alice",
        )
    )


# --- AC#5: single writer + handoff ----------------------------------------


def test_start_session_acquires_lease(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    handle = core.start_claude_session(
        StartClaudeSessionCommand(
            connection_path=connection, code_root=code_root, operator="alice"
        )
    )
    assert handle.state == "connected"
    assert handle.lease_id


def test_second_write_session_for_same_code_id_rejected(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="alice")
    )
    with pytest.raises(WorkspaceError) as exc:
        core.start_claude_session(
            StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="bob")
        )
    assert exc.value.code == "claude_session_busy"


def test_read_only_viewer_unaffected_by_lease(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="alice")
    )
    # another operator reads while alice holds the write lease
    snap = core.get_code_review(connection, code_root, "baseline")
    assert snap.managed_root_ok is True
    content = core.read_managed_file(connection, code_root, "train.py")
    assert b"build_estimator" in content


def test_handoff_release_then_acquire_succeeds(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="alice")
    )
    core.release_claude_session(connection, "baseline")
    handle = core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="bob")
    )
    assert handle.operator == "bob"


# --- AC#6: reconnect / idempotent release / stale -------------------------


def test_reconnect_after_lease_expiry(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, holder = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="alice")
    )
    holder[0] += 10_000  # past TTL
    assert core.claude_session_status(connection, "baseline") == "stale"
    handle = core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="bob")
    )
    assert handle.state == "connected"


def test_release_is_idempotent(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    core.release_claude_session(connection, "baseline")  # no active lease yet
    core.release_claude_session(connection, "baseline")  # again


# --- AC#3: capture creates agent revision ---------------------------------


def test_capture_changes_creates_agent_origin_revision(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    v1 = _save_v1(core, connection, code_root)
    # Claude edits the workspace file
    (code_root / "train.py").write_bytes(b"def build_estimator(c):\n    return 99\n")
    handle = core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="alice")
    )
    revision = core.capture_claude_changes(
        CaptureClaudeChangesCommand(
            connection_path=connection,
            code_root=code_root,
            code_id="baseline",
            handle_id=handle.handle_id,
            change_summary="agent: tune estimator",
            touched_files=("train.py",),
            entrypoint_path="train.py",
            expected_parent_fingerprint=v1.revision_fingerprint,
            prompt_hash=_SHA,
            operator="alice",
        )
    )
    assert revision.version == 2
    assert revision.origin == "agent"
    assert revision.parent_revision_id == v1.asset_id


# --- AC#7: audit fields, no conversation text -----------------------------


def test_capture_records_prompt_hash_and_tool_summary(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    v1 = _save_v1(core, connection, code_root)
    (code_root / "train.py").write_bytes(b"def build_estimator(c):\n    return 7\n")
    handle = core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="alice")
    )
    revision = core.capture_claude_changes(
        CaptureClaudeChangesCommand(
            connection_path=connection,
            code_root=code_root,
            code_id="baseline",
            handle_id=handle.handle_id,
            change_summary="agent: tune estimator",
            touched_files=("train.py",),
            entrypoint_path="train.py",
            expected_parent_fingerprint=v1.revision_fingerprint,
            prompt_hash=_SHA,
            operator="alice",
        )
    )
    assert revision.agent_prompt_hash == _SHA
    assert revision.agent_tool_summary == "agent: tune estimator"
    # the conversation prompt body must not appear in the manifest
    manifest = json.loads((root / revision.asset_path).read_text())
    assert "def build_estimator" not in json.dumps(manifest)
    assert "prompt" not in {k for k in manifest if "prompt" in k.lower() and k != "agent_prompt_hash"}


# --- AC#6: stale capture rejected, sealed instance safe --------------------


def test_capture_stale_parent_rejected(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    v1 = _save_v1(core, connection, code_root)
    # a concurrent save bumps the active revision to v2
    (code_root / "train.py").write_bytes(b"x = 1\n")
    core.save_code_revision(
        SaveCodeRevisionCommand(
            connection_path=connection, code_root=code_root, code_id="baseline",
            entrypoint_path="train.py",
            edited_files=(EditedFile(path="train.py", content=b"x = 2\n"),),
            expected_parent_fingerprint=v1.revision_fingerprint,
            change_summary="concurrent human edit", created_by="alice",
        )
    )
    handle = core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="alice")
    )
    with pytest.raises(WorkspaceError) as exc:
        core.capture_claude_changes(
            CaptureClaudeChangesCommand(
                connection_path=connection, code_root=code_root, code_id="baseline",
                handle_id=handle.handle_id, change_summary="stale",
                touched_files=("train.py",), entrypoint_path="train.py",
                expected_parent_fingerprint=v1.revision_fingerprint,
                prompt_hash=_SHA, operator="alice",
            )
        )
    assert exc.value.code == "stale_code_revision"


def test_sealed_instance_not_mutated_by_agent_edit(tmp_path):
    connection, code_root, root = _workspace(tmp_path)
    core, _ = _core(tmp_path)
    core.register_code_id(connection, code_root, "baseline")
    v1 = _save_v1(core, connection, code_root)
    _seed_instance(root, "run-1", "inst-1", v1.revision_fingerprint)
    frozen_dir = root / "runs" / "run-1"  # placeholder; real frozen dir is separate
    (code_root / "train.py").write_bytes(b"def build_estimator(c):\n    return 99\n")
    handle = core.start_claude_session(
        StartClaudeSessionCommand(connection_path=connection, code_root=code_root, operator="alice")
    )
    core.capture_claude_changes(
        CaptureClaudeChangesCommand(
            connection_path=connection, code_root=code_root, code_id="baseline",
            handle_id=handle.handle_id, change_summary="agent edit",
            touched_files=("train.py",), entrypoint_path="train.py",
            expected_parent_fingerprint=v1.revision_fingerprint,
            prompt_hash=_SHA, operator="alice",
        )
    )
    # the sealed instance still references the original frozen fingerprint (v1)
    inst_manifest = json.loads(
        (root / "runs" / "run-1" / "instances" / "inst-1" / "manifest.json").read_text()
    )
    assert inst_manifest["code_fingerprint"] == v1.revision_fingerprint
