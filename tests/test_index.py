from mlagent_memory.index import rebuild_index, search_index
from mlagent_memory.io import write_text, write_yaml
from mlagent_memory.repo import init_memory_repo


def test_rebuild_index_and_search_experience(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_yaml(
        root / "experience/pitfalls/exp_001.yaml",
        {
            "id": "exp_001",
            "type": "pitfall",
            "object_type": "experience",
            "summary": "Target leakage from post outcome fields",
            "detail": "Remove post outcome fields before training.",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-06-22T10:00:00+08:00",
        },
    )

    rebuild_index(root)
    hits = search_index(root, "leakage", asset_type="experience")
    assert len(hits) == 1
    assert hits[0]["asset_id"] == "exp_001"


def test_rebuild_index_and_search_knowledge_note(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_text(root / "project_knowledge/notes/know_001.md", "# Transformer\nAttention method note")

    rebuild_index(root)
    hits = search_index(root, "attention", asset_type="knowledge")
    assert len(hits) == 1
    assert hits[0]["asset_type"] == "knowledge"


def test_search_index_returns_empty_when_no_index(tmp_path):
    from mlagent_memory.index import search_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    # No rebuild_index call -> no FTS index exists.
    assert search_index(root, "anything") == []
    assert search_index(root, "leakage", asset_type="experience") == []


def test_search_index_filters_experience_by_confidence(tmp_path):
    from mlagent_memory.experience import add_experience
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    add_experience(root, {"id": "e_high", "type": "pitfall", "summary": "leakage high", "detail": "d", "confidence": "high", "needs_review": False, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    add_experience(root, {"id": "e_low", "type": "pitfall", "summary": "leakage low", "detail": "d", "confidence": "low", "needs_review": False, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    add_experience(root, {"id": "e_review", "type": "pitfall", "summary": "leakage review", "detail": "d", "confidence": "high", "needs_review": True, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    rebuild_index(root)
    hits = search_index(root, "leakage", asset_type="experience", confidence_levels=["high", "medium"], exclude_unreviewed=True, exclude_superseded=True)
    ids = {h["asset_id"] for h in hits}
    assert "e_high" in ids
    assert "e_low" not in ids
    assert "e_review" not in ids


def test_rebuild_index_updates_registry_index_status(tmp_path):
    from mlagent_memory.io import read_yaml
    from mlagent_memory.knowledge import import_knowledge_file
    from mlagent_memory.index import rebuild_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    src = tmp_path / "n.md"
    src.write_text("# AUC\nleakage prevention", encoding="utf-8")
    item = import_knowledge_file(root, src, item_type="method_note", tags=[])
    assert read_yaml(root / "project_knowledge/registry.yaml")["items"][0]["index_status"] == "pending"
    rebuild_index(root)
    assert read_yaml(root / "project_knowledge/registry.yaml")["items"][0]["index_status"] == "indexed"


def test_knowledge_search_returns_chunk_level_hits(tmp_path):
    from mlagent_memory.knowledge import import_knowledge_file
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    src = tmp_path / "paper.md"
    src.write_text("# A\nalpha\n\n# B\nbeta leakage\n", encoding="utf-8")
    import_knowledge_file(root, src, item_type="paper", tags=[])
    rebuild_index(root)
    hits = search_index(root, "leakage", asset_type="knowledge")
    assert hits
    assert "chunk_id" in hits[0]
    assert hits[0]["chunk_id"]  # non-empty chunk_id for imported knowledge
    assert hits[0]["asset_id"].startswith("know_")
    assert "leakage" in hits[0]["content"]
    assert "## Extracted Text" not in hits[0]["content"]


def test_knowledge_search_back_compat_indexes_direct_note(tmp_path):
    """A note written directly (no chunks dir) is still indexed as one doc."""
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.io import write_text
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_text(root / "project_knowledge/notes/know_001.md", "# Transformer\nAttention method note")
    rebuild_index(root)
    hits = search_index(root, "attention", asset_type="knowledge")
    assert len(hits) == 1


def test_knowledge_search_matches_header_keyword(tmp_path):
    """A keyword that appears only in a markdown header must still be searchable,
    because section headers are prepended to chunk content on import."""
    from mlagent_memory.knowledge import import_knowledge_file
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    src = tmp_path / "doc.md"
    src.write_text("# Target Leakage Prevention\n\nbody text without the keyword\n", encoding="utf-8")
    import_knowledge_file(root, src, item_type="paper", tags=[])
    rebuild_index(root)
    hits = search_index(root, "leakage", asset_type="knowledge")
    assert hits, "header keyword 'leakage' should be searchable"


def test_search_multi_word_query_uses_or_recall(tmp_path):
    """A natural-language multi-word query must not require ALL terms (FTS5 implicit AND).
    It should match documents sharing any term (OR recall)."""
    from mlagent_memory.knowledge import import_knowledge_file
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    src = tmp_path / "doc.md"
    src.write_text("# Notes\nThe model overfits on small samples.\n", encoding="utf-8")
    import_knowledge_file(root, src, item_type="method_note", tags=[])
    rebuild_index(root)
    # "reduce overfits quickly" contains no full phrase from the doc, but the token "overfits"
    # matches — verifying a multi-word query OR-matches on any shared token (not implicit AND).
    hits = search_index(root, "reduce overfits quickly", asset_type="knowledge")
    assert hits, "multi-word query should OR-match on a shared token ('overfits')"


def test_generated_artifacts_are_not_indexed(tmp_path):
    """SKILL.md / references/ / snapshot.json are display-only; generating them must not change
    search results or appear as hits (the index only globs experience/**/*.yaml + notes/*.md)."""
    import json

    from mlagent_memory.experience import add_experience
    from mlagent_memory.export import export_memory_snapshot
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.io import write_text
    from mlagent_memory.repo import init_memory_repo
    from mlagent_memory.skill_versions import create_skill_candidate

    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    add_experience(
        root,
        {
            "id": "e1", "type": "pitfall", "summary": "feature leakage pitfall", "detail": "d",
            "confidence": "high", "needs_review": False, "source_raw_records": ["r"],
            "created_at": "2026-06-26T10:00:00+08:00",
        },
    )
    nb = tmp_path / "notebooks" / "train.ipynb"
    nb.parent.mkdir(parents=True)
    nb.write_text(json.dumps({
        "cells": [{"cell_type": "code", "source": "from sklearn.feature_selection import RFE\n".splitlines(keepends=True)}],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
    }), encoding="utf-8")
    rebuild_index(root)
    before = search_index(root, "feature", asset_type="experience")

    # generate the display-only artifacts
    create_skill_candidate(root, version="v1", name="b", source_type="ipynb_import", source_evidence=["notebooks/train.ipynb"])
    (root / "snapshot.json").write_text(json.dumps(export_memory_snapshot(root)), encoding="utf-8")
    assert (root / "skill_versions/.candidates/v1/SKILL.md").exists()
    assert (root / "snapshot.json").exists()
    rebuild_index(root)
    after = search_index(root, "feature", asset_type="experience")

    assert len(before) == len(after) == 1
    # none of the generated artifacts appear as hits under any asset_type
    broad = search_index(root, "feature") + search_index(root, "RFE")
    for hit in broad:
        path = hit.get("source_path", "")
        assert "SKILL.md" not in path and "references/" not in path and "snapshot.json" not in path
        assert hit.get("asset_type") in {"experience", "knowledge"}



