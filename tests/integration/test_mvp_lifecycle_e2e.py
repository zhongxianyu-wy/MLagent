"""End-to-end MVP lifecycle demonstration (Issue #16 AC#8).

Drives the full v0.4 pipeline through DomainCore in one test:
bootstrap → dataset → plan → training instance → SOP candidate →
reproduction gate → approved SOP version + formal model.
Reuses build_sop_workspace (which sets up dataset + source run/instance) and
the approval chain from test_domain_core_sop.
"""
from __future__ import annotations

from tests.integration.test_retrain_from_sop import _core_with_sop


def test_mvp_lifecycle_bootstrap_to_formal_model(tmp_path):
    """A single accepted training instance reaches an approved SOP + formal model."""
    core, connection, workspace = _core_with_sop(tmp_path)

    # 1. an approved SOP version + formal model exist
    versions = core.list_sop_versions(connection)
    assert versions, "lifecycle must reach an approved SOP version"
    version = versions[0]
    assert version.version == 1

    # 2. the SOP traces back to a training instance + run
    assert version.source_run_id
    assert version.source_instance_id
    runs = {r.run_id: r for r in core.list_run_statuses(connection)}
    assert version.source_run_id in runs

    # 3. the formal model is registered and links back
    assert version.formal_model_id
    formal_model = core.get_formal_model(connection, version.formal_model_id)
    assert formal_model.sop_version_id == version.asset_id

    # 4. lineage graph connects them (Issue #14)
    graph = core.get_lineage(connection)
    node_types = {n.node_type for n in graph.nodes}
    assert {"run", "instance", "sop_version", "formal_model"} <= node_types
    assert graph.broken_refs == ()

    # 5. run replay + session context are readable (Issues #13/#15)
    replay = core.get_run_replay(connection, version.source_run_id)
    assert replay.run.run_id == version.source_run_id
    context = core.get_session_context(connection)
    assert context.recent_run_id is not None
