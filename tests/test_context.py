"""Test assemble-context: experience filtering (confidence/verified/superseded) + conventions."""
from mlagent.context import assemble_context
from mlagent.experience import add_experience
from mlagent.io import write_yaml
from mlagent.repo import init_memory_repo


def test_assemble_context_filters_and_separates_conventions(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")

    # high-confidence pitfall (included)
    add_experience(root, {"id": "e_high", "type": "pitfall", "summary": "leakage", "detail": "d",
                          "confidence": "high", "needs_review": False, "source_raw_records": [],
                          "created_at": "2026-07-03T10:00:00+08:00"})
    # medium lesson (included)
    add_experience(root, {"id": "e_med", "type": "lesson", "summary": "use cv", "detail": "d",
                          "confidence": "medium", "needs_review": True, "source_raw_records": [],
                          "created_at": "2026-07-03T10:00:00+08:00"})
    # low (excluded)
    add_experience(root, {"id": "e_low", "type": "pitfall", "summary": "guess", "detail": "d",
                          "confidence": "low", "needs_review": True, "source_raw_records": [],
                          "created_at": "2026-07-03T10:00:00+08:00"})
    # superseded (excluded)
    add_experience(root, {"id": "e_old", "type": "lesson", "summary": "old", "detail": "d",
                          "confidence": "high", "needs_review": False, "source_raw_records": [],
                          "created_at": "2026-07-03T10:00:00+08:00", "superseded_by": "e_new"})
    # convention (goes to conventions[], not experience[])
    add_experience(root, {"id": "e_conv", "type": "convention", "summary": "10-fold CV", "detail": "stratified",
                          "confidence": "high", "needs_review": False, "source_raw_records": [],
                          "created_at": "2026-07-03T10:00:00+08:00"})

    pack = assemble_context(root, "Improve AUC")
    exp_ids = {e["id"] for e in pack["experience"]}
    conv_ids = {c["id"] for c in pack["conventions"]}

    assert "e_high" in exp_ids
    assert "e_med" in exp_ids
    assert "e_low" not in exp_ids
    assert "e_old" not in exp_ids
    assert "e_conv" in conv_ids
    assert "e_conv" not in exp_ids
    assert pack["current_prompt"] == "Improve AUC"


def test_assemble_context_empty_repo(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    pack = assemble_context(root, "test")
    assert pack["experience"] == []
    assert pack["conventions"] == []
    assert pack["skill_versions"] == []
