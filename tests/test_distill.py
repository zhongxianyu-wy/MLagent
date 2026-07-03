"""Test the deterministic distill Curator (insert/update/link/supersede/noop)."""
from mlagent.distill import apply_distill_plan
from mlagent.experience import add_experience
from mlagent.io import read_yaml, write_yaml
from mlagent.repo import init_memory_repo


def _seed(root):
    """Seed an existing experience to test update/link/supersede against."""
    add_experience(
        root,
        {
            "id": "exp_old",
            "type": "pitfall",
            "summary": "old pitfall",
            "detail": "original",
            "confidence": "medium",
            "needs_review": True,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-07-03T10:00:00+08:00",
        },
    )


def _new_exp(**overrides):
    base = {
        "id": "exp_new",
        "type": "pitfall",
        "summary": "new pitfall",
        "detail": "refined",
        "confidence": "high",
        "needs_review": False,
        "source_raw_records": ["raw_memory/runs/raw_002.yaml"],
        "created_at": "2026-07-03T11:00:00+08:00",
    }
    base.update(overrides)
    return base


def test_distill_insert_and_noop(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    ops = [
        {"decision": "noop"},
        {"decision": "insert", "experience": _new_exp()},
    ]
    summary = apply_distill_plan(root, ops)
    assert summary["insert"] == 1
    assert summary["noop"] == 1
    assert (root / "experience/pitfalls/exp_new.yaml").exists()


def test_distill_update(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    _seed(root)
    ops = [{"decision": "update", "target_id": "exp_old", "patch": {"confidence": "high", "needs_review": False}}]
    summary = apply_distill_plan(root, ops)
    assert summary["update"] == 1
    data = read_yaml(root / "experience/pitfalls/exp_old.yaml")
    assert data["confidence"] == "high"
    assert data["needs_review"] is False


def test_distill_supersede_marks_old(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    _seed(root)
    ops = [{"decision": "supersede", "target_id": "exp_old", "experience": _new_exp(id="exp_replacement")}]
    summary = apply_distill_plan(root, ops)
    assert summary["supersede"] == 1
    old = read_yaml(root / "experience/pitfalls/exp_old.yaml")
    assert old["superseded_by"] == "exp_replacement"
    assert old["verified"] == "rolled_back"
    assert (root / "experience/pitfalls/exp_replacement.yaml").exists()


def test_distill_link_adds_related_backlink(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    _seed(root)
    ops = [{"decision": "link", "target_id": "exp_old", "experience": _new_exp(id="exp_linked")}]
    summary = apply_distill_plan(root, ops)
    assert summary["link"] == 1
    old = read_yaml(root / "experience/pitfalls/exp_old.yaml")
    assert "exp_linked" in old.get("related", [])
