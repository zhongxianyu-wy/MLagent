import json
from pathlib import Path

import pytest

from mlagent_memory.skill_extraction import (
    analyze_training_logic,
    parse_source,
    render_skill_md,
    resolve_source_evidence,
)

# Reused source body exercising data input, feature selection, model, fit, metric, a function.
_CODE = """\
import pandas as pd
from sklearn.feature_selection import RFE, SelectKBest, f_classif
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score

df = pd.read_csv("data/train.csv")
test_df = pd.read_csv("data/test.csv")


def select_features(X, y):
    skb = SelectKBest(f_classif, k=20)
    X_skb = skb.fit_transform(X, y)
    rfe = RFE(LGBMClassifier(n_estimators=50), n_features_to_select=10)
    return rfe.fit_transform(X_skb, y)


X_sel = select_features(X, y)
model = LGBMClassifier(n_estimators=200, learning_rate=0.05)
model.fit(X_train, y_train)
auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
"""


def _write_ipynb(path: Path, code: str) -> None:
    nb = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Training notebook\n", "Feature selection + LGBM."]},
            {"cell_type": "code", "source": code.splitlines(keepends=True)},
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(nb), encoding="utf-8")


def test_parse_source_ipynb(tmp_path):
    nb = tmp_path / "train.ipynb"
    _write_ipynb(nb, _CODE)
    parsed = parse_source(nb)
    assert parsed["language"] == "python"
    assert "LGBMClassifier" in parsed["code"]
    assert "Feature selection + LGBM." in parsed["markdown"]
    assert parsed["n_cells"] == 2


def test_parse_source_py(tmp_path):
    py = tmp_path / "train.py"
    py.write_text(_CODE, encoding="utf-8")
    parsed = parse_source(py)
    assert parsed["language"] == "python"
    assert "LGBMClassifier" in parsed["code"]
    assert parsed["markdown"] == ""


def test_parse_source_rejects_unsupported(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("not code", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_source(bad)


def test_parse_source_rejects_malformed_ipynb(tmp_path):
    bad = tmp_path / "bad.ipynb"
    bad.write_text(json.dumps({"nope": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        parse_source(bad)


def test_analyze_training_logic_detects_feature_selection_and_model():
    analysis = analyze_training_logic(_CODE)
    techniques = {hit["technique"] for hit in analysis["feature_selection"]}
    assert {"SelectKBest", "f_classif", "RFE"} <= techniques
    for hit in analysis["feature_selection"]:
        assert isinstance(hit["line"], int) and hit["line"] >= 1
        assert hit["snippet"].strip()
    # data inputs
    inputs = {str(x) for x in analysis["data_inputs"]}
    assert "data/train.csv" in inputs and "data/test.csv" in inputs
    # model
    assert "LGBMClassifier" in analysis["model"]["names"]
    assert analysis["model"]["has_fit"] is True
    assert "n_estimators" in analysis["model"]["params"]
    # metrics
    assert any("roc_auc_score" in str(m.get("name", "")) for m in analysis["metrics"])
    # imports (top-level modules)
    assert "pandas" in analysis["imports"]
    assert "sklearn" in analysis["imports"]
    assert "lightgbm" in analysis["imports"]
    # functions
    assert "select_features" in analysis["functions"]
    # CV flag
    assert analysis["has_cv"] is False


def test_analyze_training_logic_survives_magics():
    code_with_magic = "%matplotlib inline\n" + _CODE
    analysis = analyze_training_logic(code_with_magic)
    # still detects core items even though the magic line breaks ast
    assert {"SelectKBest", "RFE"} <= {h["technique"] for h in analysis["feature_selection"]}
    assert "LGBMClassifier" in analysis["model"]["names"]


def test_render_skill_md_follows_skill_creator_format():
    analysis = analyze_training_logic(_CODE)
    md = render_skill_md("v001_baseline", "baseline_lgbm", "ipynb_import", analysis, "notebooks/train.ipynb")
    # frontmatter
    assert md.startswith("---\n")
    header = md.split("---\n", 2)[1]
    assert "name:" in header and "description:" in header
    # pushy description with trigger phrasing
    assert "baseline_lgbm" in md
    # body sections (skill-creator body)
    for section in ["## When to use", "## Feature-selection strategy", "## Training procedure", "## Reproduce", "## Gotchas"]:
        assert section in md
    # references the authoritative source + analysis
    assert "references/source.py" in md
    assert "references/analysis.yaml" in md
    # surfaces a detected technique
    assert "RFE" in md or "SelectKBest" in md
    # keep within progressive-disclosure budget
    assert md.count("\n") < 500


def test_resolve_source_evidence(tmp_path):
    root = tmp_path / "project_memory"
    root.mkdir()
    nb = tmp_path / "notebooks" / "train.ipynb"
    nb.parent.mkdir(parents=True)
    _write_ipynb(nb, _CODE)
    # absolute path resolves
    assert resolve_source_evidence(root, [str(nb)]) == nb
    # relative to repo root (root.parent) resolves
    assert resolve_source_evidence(root, ["notebooks/train.ipynb"]) == nb
    # nothing resolvable -> None
    assert resolve_source_evidence(root, ["does/not/exist.ipynb"]) is None
    # non-code evidence ignored
    assert resolve_source_evidence(root, ["README.md"]) is None
