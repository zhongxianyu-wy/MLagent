"""Test the SOP lifecycle: candidate → gate → approve → immutable."""
import pytest

from mlagent.errors import MlagentError
from mlagent.io import write_yaml
from mlagent.repo import init_memory_repo
from mlagent.sop import approve_sop, create_candidate, get_sop, list_sops, set_gate_result


def _perf():
    return {"primary_metric": {"name": "auc", "value": 0.91}, "dataset_version": "d1", "validation_protocol": "holdout"}


def test_create_candidate_is_pending_with_gate(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    sv = create_candidate(root, "baseline", "v001", "exploration", ["raw_memory/runs/raw_001.yaml"],
                          background="early baseline", reason="first to hit target")
    assert sv.state == "pending_review"
    cand = root / "skill_library/.candidates/baseline/v001/sop.yaml"
    assert cand.exists()
    assert read_yaml_safe(cand)["gate"]["tests_passed"] is False


def read_yaml_safe(p):
    from mlagent.io import read_yaml
    return read_yaml(p)


def test_approve_rejects_without_gate(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_candidate(root, "baseline", "v001", "exploration", [])
    with pytest.raises(MlagentError, match="Gate not passed"):
        approve_sop(root, "baseline", "v001", "human", "ok", _perf())


def test_full_lifecycle_gate_then_approve(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_candidate(root, "baseline", "v001", "exploration", [], background="b", reason="r")
    set_gate_result(root, "baseline", "v001", tests_passed=True, test_log="all green")
    approved = approve_sop(root, "baseline", "v001", "human", "ok", _perf())
    assert approved.state == "approved"
    assert (root / "skill_library/baseline/v001/sop.yaml").exists()
    assert (root / "skill_library/baseline/v001/performance.yaml").exists()
    reg = read_yaml_safe(root / "skill_library/registry.yaml")
    assert any(v["name"] == "baseline" and v["version"] == "v001" for v in reg["versions"])


def test_approved_is_immutable(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_candidate(root, "baseline", "v001", "exploration", [])
    set_gate_result(root, "baseline", "v001", tests_passed=True)
    approve_sop(root, "baseline", "v001", "h", "ok", _perf())
    with pytest.raises(MlagentError, match="already exists"):
        approve_sop(root, "baseline", "v001", "h2", "again", _perf())


def test_list_sops_approved_and_candidates(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_candidate(root, "baseline", "v001", "exploration", [])
    set_gate_result(root, "baseline", "v001", tests_passed=True)
    approve_sop(root, "baseline", "v001", "h", "ok", _perf())
    create_candidate(root, "baseline", "v002", "exploration", [])
    data = list_sops(root)
    assert len(data["approved"]) == 1
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["version"] == "v002"


def test_get_sop_rejects_draft_without_flag(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_candidate(root, "baseline", "v001", "exploration", [])
    with pytest.raises(MlagentError, match="pending candidate"):
        get_sop(root, "baseline", "v001")
    bundle = get_sop(root, "baseline", "v001", include_draft=True)
    assert bundle["source"] == "candidate"
