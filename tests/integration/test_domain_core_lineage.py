"""Integration tests for DomainCore lineage graph (Issue #14)."""
from __future__ import annotations

import shutil

import pytest

from src.domain.core import DomainCore
from src.domain.models import WorkspaceError
from tests.integration.test_retrain_from_sop import _core_with_sop


def test_lineage_links_dataset_through_run_instance_to_sop_and_model(tmp_path):
    core, connection, workspace = _core_with_sop(tmp_path)
    graph = core.get_lineage(connection)

    node_types = {n.node_type for n in graph.nodes}
    assert {"run", "instance", "sop_candidate", "sop_version", "formal_model"} <= node_types
    edge_kinds = {e.kind for e in graph.edges}
    assert {"produced", "source", "model_registered"} <= edge_kinds

    # Formal Model reaches SOP version + source instance within 3 hops
    fm = next(n for n in graph.nodes if n.node_type == "formal_model")
    by_target = {}
    for e in graph.edges:
        by_target.setdefault(e.target_key, []).append(e.source_key)
    # fm -> sop_version (model_registered back-edge) -> instance (source)
    sop_v_sources = by_target.get(fm.key, [])
    assert sop_v_sources, "formal model must link back to a SOP version"
    # the SOP version has a source edge to an instance
    sv = sop_v_sources[0]
    has_instance_source = any(
        e.kind == "source" and e.target_key.startswith("instance:")
        for e in graph.edges if e.source_key == sv
    )
    assert has_instance_source

    # clean workspace → no broken refs
    assert graph.broken_refs == ()


def test_experience_only_used_never_sop_source(tmp_path):
    """AC#5: Experience must never be a direct/indirect source of a SOP."""
    core, connection, workspace = _core_with_sop(tmp_path)
    graph = core.get_lineage(connection)
    # no edge from an experience node to a sop node of any kind
    for edge in graph.edges:
        if edge.source_key.startswith("experience:"):
            assert not edge.target_key.startswith("sop_"), (
                f"experience must not source a SOP: {edge}"
            )
            assert edge.kind == "used", (
                f"experience edges must be 'used': {edge}"
            )


def test_broken_ref_detected_and_review_blocked(tmp_path):
    """AC#7: broken references are flagged and block approval."""
    core, connection, workspace = _core_with_sop(tmp_path)
    assert core.verify_lineage_integrity(connection) == ()

    # break the lineage: remove the source run directory
    run_dirs = list(workspace.root.glob("**/run-source"))
    assert run_dirs, "source run directory should exist"
    shutil.rmtree(run_dirs[0])

    broken = core.verify_lineage_integrity(connection)
    assert broken, "broken refs must be detected after removing source run"
    cand_refs = [b for b in broken if "sop_candidate:candidate-1" in b]
    assert cand_refs, "the candidate's source link must be among broken refs"

    with pytest.raises(WorkspaceError) as exc:
        core._verify_candidate_lineage(connection, "candidate-1")
    assert exc.value.code == "lineage_broken"


def test_retrain_run_branches_not_merges_into_sop_version(tmp_path):
    """AC#6: a SOP retrain run is a separate branch, not a new SOP version."""
    core, connection, workspace = _core_with_sop(tmp_path)
    from src.domain.models import RetrainFromSopCommand

    runs_before = {
        n.asset_id for n in core.get_lineage(connection).nodes
        if n.node_type == "run"
    }
    core.retrain_from_sop(
        RetrainFromSopCommand(
            connection_path=connection,
            sop_id="baseline",
            sop_version=1,
            dataset_id="ds-1",
            dataset_version=1,
            code_root=workspace.root,
        )
    )
    graph = core.get_lineage(connection)
    # only one SOP version node remains (retrain did not add a version)
    versions = [n for n in graph.nodes if n.node_type == "sop_version"]
    assert len(versions) == 1
    # the retrain run is a separate branch run, not merged as a SOP version predecessor
    runs_after = {n.asset_id for n in graph.nodes if n.node_type == "run"}
    assert runs_after > runs_before
