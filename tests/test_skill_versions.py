from mlagent_memory.io import read_yaml, write_yaml
from mlagent_memory.repo import init_memory_repo
from mlagent_memory.skill_versions import approve_skill_candidate, create_skill_candidate


def _candidate(root, version="v_perf"):
    create_skill_candidate(
        root,
        version=version,
        name="baseline",
        source_type="best_run",
        source_evidence=["raw_memory/runs/r.yaml"],
    )


def test_create_skill_candidate_is_not_approved(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")

    candidate = create_skill_candidate(
        root,
        version="v001_baseline",
        name="baseline",
        source_type="best_run",
        source_evidence=["raw_memory/runs/raw_001.yaml"],
    )

    assert candidate.state == "pending_review"
    path = root / "skill_versions/.candidates/v001_baseline/skill.yaml"
    assert path.exists()
    assert read_yaml(path)["human_review"]["reviewed"] is False


def test_approve_skill_candidate_requires_performance(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(
        root,
        version="v001_baseline",
        name="baseline",
        source_type="ipynb_import",
        source_evidence=["evidence/notebooks/baseline.ipynb"],
    )
    performance_path = tmp_path / "performance.yaml"
    write_yaml(
        performance_path,
        {
            "primary_metric": {"name": "auc", "value": 0.91},
            "benchmark_metric": {"name": "baseline_auc", "value": 0.86},
            "dataset_version": "data_v001",
            "validation_protocol": "holdout",
        },
    )

    approved = approve_skill_candidate(
        root,
        version="v001_baseline",
        reviewer="human",
        approval_note="Performance meets target.",
        performance_path=performance_path,
    )

    assert approved.state == "approved"
    assert (root / "skill_versions/v001_baseline/skill.yaml").exists()
    registry = read_yaml(root / "skill_versions/registry.yaml")
    assert registry["versions"][0]["version"] == "v001_baseline"


import pytest

from mlagent_memory.errors import InvalidSkillPerformance, SkillVersionAlreadyExists, SkillVersionNotFound
from mlagent_memory.skill_versions import get_skill, list_skills


def test_approve_rejects_empty_performance(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    _candidate(root)
    perf = tmp_path / "perf.yaml"
    write_yaml(perf, {})
    with pytest.raises(InvalidSkillPerformance):
        approve_skill_candidate(
            root,
            version="v_perf",
            reviewer="human",
            approval_note="ok",
            performance_path=perf,
        )


def test_approve_rejects_incomplete_performance(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    _candidate(root)
    perf = tmp_path / "perf.yaml"
    write_yaml(perf, {"primary_metric": {"name": "auc", "value": 0.9}})  # missing dataset_version, validation_protocol
    with pytest.raises(InvalidSkillPerformance):
        approve_skill_candidate(
            root,
            version="v_perf",
            reviewer="human",
            approval_note="ok",
            performance_path=perf,
        )


def test_list_skills_returns_approved_and_empty(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    assert list_skills(root) == []
    _candidate(root, "v_list")
    perf = tmp_path / "perf.yaml"
    write_yaml(
        perf,
        {
            "primary_metric": {"name": "auc", "value": 0.91},
            "dataset_version": "d1",
            "validation_protocol": "holdout",
        },
    )
    approve_skill_candidate(
        root,
        version="v_list",
        reviewer="human",
        approval_note="ok",
        performance_path=perf,
    )
    versions = list_skills(root)
    assert len(versions) == 1
    assert versions[0]["version"] == "v_list"
    assert versions[0]["state"] == "approved"


def test_get_skill_approved_and_candidate_and_missing(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    _candidate(root, "v_get")
    perf = tmp_path / "perf.yaml"
    write_yaml(
        perf,
        {
            "primary_metric": {"name": "auc", "value": 0.91},
            "dataset_version": "d1",
            "validation_protocol": "holdout",
        },
    )
    approve_skill_candidate(
        root,
        version="v_get",
        reviewer="human",
        approval_note="ok",
        performance_path=perf,
    )
    bundle = get_skill(root, "v_get")
    assert bundle["source"] == "approved"
    assert bundle["state"] == "approved"
    assert "performance.yaml" in bundle["files"]
    # candidate-only
    _candidate(root, "v_draft")
    with pytest.raises(SkillVersionNotFound):
        get_skill(root, "v_draft")
    draft_bundle = get_skill(root, "v_draft", include_draft=True)
    assert draft_bundle["source"] == "candidate"
    assert draft_bundle["state"] == "pending_review"
    # missing
    with pytest.raises(SkillVersionNotFound):
        get_skill(root, "nope")


def test_approve_rejects_duplicate_unless_replace(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(root, version="v1", name="b", source_type="best_run", source_evidence=["r"])
    perf = tmp_path / "p.yaml"
    write_yaml(perf, {"primary_metric": {"name": "auc", "value": 0.91}, "dataset_version": "d1", "validation_protocol": "holdout"})
    approve_skill_candidate(root, version="v1", reviewer="h1", approval_note="first", performance_path=perf)
    with pytest.raises(SkillVersionAlreadyExists):
        approve_skill_candidate(root, version="v1", reviewer="h2", approval_note="second", performance_path=perf)
    # replace archives the old and approves the new
    approve_skill_candidate(root, version="v1", reviewer="h2", approval_note="second", performance_path=perf, replace=True)
    from mlagent_memory.io import read_yaml
    assert read_yaml(root / "skill_versions/v1/skill.yaml")["human_review"]["reviewer"] == "h2"
    archives = list((root / "skill_versions/.archive").glob("v1_*"))
    assert len(archives) == 1
