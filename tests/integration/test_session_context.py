"""Integration tests for session context restore (Issue #15 T2/T3, AC#2)."""
from __future__ import annotations

from src.domain.core import DomainCore
from tests.integration.test_retrain_from_sop import _core_with_sop


def test_session_context_restores_plan_run_and_pending(tmp_path):
    core, connection, workspace = _core_with_sop(tmp_path)
    ctx = core.get_session_context(connection)
    # the workspace has at least one run (source + reproduction)
    assert ctx.recent_run_id is not None
    assert ctx.recent_run_state is not None
    assert isinstance(ctx.pending_experience_count, int)
    assert isinstance(ctx.pending_experience_ids, tuple)


def test_session_context_empty_workspace(tmp_path):
    from src.domain.memory_repository import MemoryRepository
    import json
    root = tmp_path / "tm"
    MemoryRepository(
        id_factory=lambda: "t", clock=lambda: "2026-07-24T00:00:00Z"
    ).bootstrap(root, actor_id="alice")
    connection = tmp_path / ".mlagent-workspace.json"
    connection.write_text(json.dumps({"repository_path": str(root), "actor_id": "alice"}))
    core = DomainCore(clock=lambda: "2026-07-24T00:00:00Z")
    ctx = core.get_session_context(connection)
    assert ctx.latest_plan_id is None
    assert ctx.recent_run_id is None
    assert ctx.pending_experience_count == 0


def test_session_context_is_read_only(tmp_path):
    import hashlib
    core, connection, workspace = _core_with_sop(tmp_path)
    runs_dir = workspace.root / "raw-records" / "runs"

    def _snap():
        return {
            p.relative_to(runs_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(runs_dir.rglob("*")) if p.is_file()
        }

    before = _snap()
    core.get_session_context(connection)
    core.get_session_context(connection)
    assert _snap() == before
