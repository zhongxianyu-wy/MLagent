from mlagent_memory.io import read_yaml, write_yaml
from mlagent_memory.repo import init_memory_repo
from mlagent_memory.skill_versions import approve_skill_candidate, create_skill_candidate


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
