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


def test_approve_skill_is_immutable(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(root, version="v1", name="b", source_type="best_run", source_evidence=["r"])
    perf = tmp_path / "p.yaml"
    write_yaml(perf, {"primary_metric": {"name": "auc", "value": 0.91}, "dataset_version": "d1", "validation_protocol": "holdout"})
    approve_skill_candidate(root, version="v1", reviewer="h1", approval_note="first", performance_path=perf)
    with pytest.raises(SkillVersionAlreadyExists):
        approve_skill_candidate(root, version="v1", reviewer="h2", approval_note="second", performance_path=perf)


def test_create_skill_candidate_rejects_duplicate_by_default(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(root, version="v1", name="baseline", source_type="best_run", source_evidence=["raw"])
    with pytest.raises(SkillVersionAlreadyExists):
        create_skill_candidate(root, version="v1", name="baseline", source_type="best_run", source_evidence=["raw"])


def test_create_skill_candidate_preserves_human_draft_without_replace(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(root, version="v1", name="baseline", source_type="best_run", source_evidence=["raw"])
    reproduce = root / "skill_versions/.candidates/v1/reproduce.md"
    reproduce.write_text("HUMAN DRAFT\n", encoding="utf-8")
    with pytest.raises(SkillVersionAlreadyExists):
        create_skill_candidate(root, version="v1", name="baseline", source_type="best_run", source_evidence=["raw"])
    assert reproduce.read_text(encoding="utf-8") == "HUMAN DRAFT\n"


def test_create_skill_candidate_replace_archives_old(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(root, version="v1", name="baseline", source_type="best_run", source_evidence=["raw"])
    create_skill_candidate(root, version="v1", name="baseline", source_type="best_run", source_evidence=["raw"], replace=True)
    archives = list((root / "skill_versions/.archive/candidates").glob("v1_*"))
    assert len(archives) == 1
    # new candidate still exists and is usable
    assert (root / "skill_versions/.candidates/v1/skill.yaml").exists()


import json


def _write_nb(path, code):
    nb = {
        "cells": [
            {"cell_type": "markdown", "source": ["# nb"]},
            {"cell_type": "code", "source": code.splitlines(keepends=True)},
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(nb), encoding="utf-8")


_NB_CODE = (
    "import pandas as pd\n"
    "from sklearn.feature_selection import RFE, SelectKBest, f_classif\n"
    "from lightgbm import LGBMClassifier\n"
    "from sklearn.metrics import roc_auc_score\n"
    'df = pd.read_csv("data/train.csv")\n'
    "def select_features(X, y):\n"
    "    skb = SelectKBest(f_classif, k=20)\n"
    "    rfe = RFE(LGBMClassifier(n_estimators=50), n_features_to_select=10)\n"
    "    return rfe.fit_transform(skb.fit_transform(X, y), y)\n"
    "model = LGBMClassifier(n_estimators=200, learning_rate=0.05)\n"
    "model.fit(X_train, y_train)\n"
    "auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])\n"
)


def test_create_skill_candidate_parses_ipynb_into_skill(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    nb = tmp_path / "notebooks" / "train.ipynb"
    nb.parent.mkdir(parents=True)
    _write_nb(nb, _NB_CODE)
    candidate = create_skill_candidate(
        root, version="v001_lgbm", name="lgbm_baseline",
        source_type="ipynb_import", source_evidence=["notebooks/train.ipynb"],
    )
    cdir = root / "skill_versions/.candidates/v001_lgbm"
    assert (cdir / "SKILL.md").exists()
    source_py = cdir / "references/source.py"
    assert source_py.exists() and "RFE" in source_py.read_text(encoding="utf-8")
    analysis = read_yaml(cdir / "references/analysis.yaml")
    assert analysis["feature_selection"]
    skill_yaml = read_yaml(cdir / "skill.yaml")
    assert len(skill_yaml["artifacts"]) == 3
    assert all(isinstance(a, dict) and all(isinstance(v, str) for v in a.values()) for a in skill_yaml["artifacts"])
    assert skill_yaml["reproducibility"]["entrypoint"] == "references/source.py"
    assert "sklearn" in skill_yaml["requirements"]["python_imports"]
    assert candidate.state == "pending_review"


def test_create_skill_candidate_falls_back_when_source_missing(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    candidate = create_skill_candidate(
        root, version="v_fallback", name="b",
        source_type="ipynb_import", source_evidence=["does/not/exist.ipynb"],
    )
    cdir = root / "skill_versions/.candidates/v_fallback"
    assert not (cdir / "SKILL.md").exists()
    assert not (cdir / "references").exists()
    assert (cdir / "reproduce.md").exists()
    assert candidate.artifacts == []


def test_get_skill_surfaces_skill_md_and_references(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    nb = tmp_path / "notebooks" / "train.ipynb"
    nb.parent.mkdir(parents=True)
    _write_nb(nb, _NB_CODE)
    create_skill_candidate(
        root, version="v_bundle", name="lgbm",
        source_type="ipynb_import", source_evidence=["notebooks/train.ipynb"],
    )
    bundle = get_skill(root, "v_bundle", include_draft=True)
    assert "SKILL.md" in bundle["files"]
    assert "references/source.py" in bundle["files"]
    assert "references/analysis.yaml" in bundle["files"]
