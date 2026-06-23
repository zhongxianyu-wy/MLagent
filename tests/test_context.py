from mlagent_memory.context import create_context_pack
from mlagent_memory.experience import add_experience
from mlagent_memory.index import rebuild_index
from mlagent_memory.io import write_text
from mlagent_memory.repo import init_memory_repo


def test_exploration_pack_orders_sections_by_confirmed_priority(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_text(root / "data_understanding/dataset_card.md", "Fields include age and tumor_stage.")
    add_experience(
        root,
        {
            "id": "exp_001",
            "type": "pitfall",
            "summary": "Leakage risk",
            "detail": "Do not keep post outcome fields.",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-06-22T10:30:00+08:00",
        },
    )
    write_text(root / "project_knowledge/notes/know_001.md", "AUC optimization knowledge")
    rebuild_index(root)

    pack = create_context_pack(root, pack_type="exploration", prompt="Improve AUC")
    names = [section["name"] for section in pack.sections]
    assert names[:5] == [
        "current_prompt",
        "data_understanding",
        "experience",
        "project_knowledge",
        "skill_versions",
    ]


def test_retraining_pack_requires_skill_version(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    from mlagent_memory.errors import SkillVersionNotFound
    try:
        create_context_pack(root, pack_type="retraining", prompt="Retrain", skill_version="v999")
    except SkillVersionNotFound as exc:
        assert "SkillVersion not found" in str(exc) or "not approved" in str(exc).lower() or "v999" in str(exc)
    else:
        raise AssertionError("Expected missing SkillVersion failure")


def test_exploration_pack_on_fresh_repo_without_index(tmp_path):
    from mlagent_memory.context import create_context_pack
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    pack = create_context_pack(root, pack_type="exploration", prompt="Improve AUC")
    names = [s["name"] for s in pack.sections]
    assert names[:5] == ["current_prompt", "data_understanding", "experience", "project_knowledge", "skill_versions"]
    # experience and project_knowledge came from search_index on a missing index -> empty
    assert pack.sections[2]["content"] == []
    assert pack.sections[3]["content"] == []
    assert pack.sections[4]["content"] == []   # empty SkillVersion registry


def test_exploration_pack_excludes_low_confidence_and_unreviewed(tmp_path):
    from mlagent_memory.experience import add_experience
    from mlagent_memory.index import rebuild_index
    from mlagent_memory.io import write_text
    from mlagent_memory.context import create_context_pack
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    add_experience(root, {"id": "e_high", "type": "pitfall", "summary": "leakage", "detail": "d", "confidence": "high", "needs_review": False, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    add_experience(root, {"id": "e_low", "type": "pitfall", "summary": "leakage", "detail": "d", "confidence": "low", "needs_review": False, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    add_experience(root, {"id": "e_review", "type": "pitfall", "summary": "leakage", "detail": "d", "confidence": "high", "needs_review": True, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    rebuild_index(root)
    pack = create_context_pack(root, pack_type="exploration", prompt="leakage")
    exp_ids = {h["asset_id"] for h in pack.sections[2]["content"]}
    assert "e_high" in exp_ids
    assert "e_low" not in exp_ids
    assert "e_review" not in exp_ids


def test_retraining_pack_requires_approved_skill(tmp_path):
    from mlagent_memory.context import create_context_pack
    from mlagent_memory.errors import SkillVersionNotFound
    from mlagent_memory.skill_versions import create_skill_candidate
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(root, version="v_draft", name="b", source_type="best_run", source_evidence=["r"])
    # candidate only -> not approved -> retraining must reject
    import pytest
    with pytest.raises(SkillVersionNotFound):
        create_context_pack(root, pack_type="retraining", prompt="retrain", skill_version="v_draft")
