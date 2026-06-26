"""Parse .ipynb/.py training sources and extract a skill-creator-format skill.

Focus: the feature-subset / feature-selection process, plus the model + data + metrics.
The full source is always preserved (references/source.py) so the recipe is reproducible
even when heuristic detection misses something. Stdlib only (json + ast + re).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from mlagent_memory.io import read_text

_CODE_SUFFIXES = {".ipynb", ".py"}

# (technique label, compiled regex). Matched over non-comment source lines.
_FEATURE_SELECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SelectKBest", re.compile(r"\bSelectKBest\b")),
    ("SelectPercentile", re.compile(r"\bSelectPercentile\b")),
    ("f_classif", re.compile(r"\bf_classif\b")),
    ("f_regression", re.compile(r"\bf_regression\b")),
    ("mutual_info_classif", re.compile(r"\bmutual_info_classif\b")),
    ("mutual_info_regression", re.compile(r"\bmutual_info_regression\b")),
    ("chi2", re.compile(r"\bchi2\s*\(")),
    ("VarianceThreshold", re.compile(r"\bVarianceThreshold\b")),
    ("GenericUnivariateSelect", re.compile(r"\bGenericUnivariateSelect\b")),
    ("RFECV", re.compile(r"\bRFECV\s*\(")),
    ("RFE", re.compile(r"\bRFE\s*\(")),
    ("SelectFromModel", re.compile(r"\bSelectFromModel\b")),
    ("SequentialFeatureSelector", re.compile(r"\bSequentialFeatureSelector\b")),
    ("feature_importances_", re.compile(r"\.feature_importances_")),
    ("coef_", re.compile(r"\.coef_\b")),
    ("permutation_importance", re.compile(r"\bpermutation_importance\b")),
    ("correlation", re.compile(r"\.corr\s*\(")),
    ("drop_columns", re.compile(r"\.drop\s*\(\s*(?:columns|labels)\s*=")),
    ("column_subset", re.compile(r"\[\s*\[")),
    ("filter_items", re.compile(r"\.filter\s*\(\s*items\s*=")),
    ("loc_columns", re.compile(r"\.loc\s*:\s*,\s")),
]

_DATA_INPUT_RE = re.compile(
    r"(?:read_csv|read_excel|read_parquet|read_fwf|read_table|load|read_hdf|read_pickle)\s*\(\s*['\"]([^'\"]+)['\"]"
)
_METRIC_PATTERNS = [
    "roc_auc_score", "accuracy_score", "f1_score", "precision_score", "recall_score",
    "average_precision_score", "brier_score_loss", "log_loss", "mean_squared_error",
    "mean_absolute_error", "root_mean_squared_error", "r2_score", "max_error",
    "classification_report", "confusion_matrix", "roc_curve", "precision_recall_curve",
]
_METRIC_RE = re.compile(r"\b(" + "|".join(_METRIC_PATTERNS) + r")\s*\(")
_FIT_RE = re.compile(r"\.fit\s*\(")
_CV_RE = re.compile(r"\b(cross_val_score|cross_validate|cross_val_predict|GridSearchCV|RandomizedSearchCV|KFold|StratifiedKFold|RepeatedStratifiedKFold|RepeatedKFold)\b")
# Estimator class names (last segment of a call's func) — used to pull hyperparameters.
_ESTIMATOR_RE = re.compile(r"^[A-Z]\w*(?:Classifier|Regressor|Regression|Forest|Boosting|SVC|SVR)$")
# Same shape, regex form — finds estimator instantiations even when ast cannot parse (notebook magics).
_MODEL_INSTANTIATION_RE = re.compile(r"\b([A-Z]\w*(?:Classifier|Regressor|Regression|Forest|Boosting|SVC|SVR))\s*\(")


def parse_source(path: Path) -> dict[str, Any]:
    """Parse a .ipynb or .py source into {code, markdown, language, n_cells}."""
    suffix = path.suffix.lower()
    if suffix == ".py":
        return {"code": read_text(path), "markdown": "", "language": "python", "n_cells": None}
    if suffix == ".ipynb":
        nb = json.loads(read_text(path))
        if not isinstance(nb, dict) or "cells" not in nb:
            raise ValueError(f"Not a valid Jupyter notebook (missing 'cells'): {path}")
        code_parts: list[str] = []
        md_parts: list[str] = []
        for cell in nb["cells"]:
            src = cell.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            if cell.get("cell_type") == "markdown":
                md_parts.append(str(src))
            else:
                code_parts.append(str(src))
        return {
            "code": "\n".join(code_parts),
            "markdown": "\n".join(md_parts),
            "language": "python",
            "n_cells": len(nb["cells"]),
        }
    raise ValueError(f"Unsupported source file type: {path.suffix}")


def _regex_pass(code: str) -> dict[str, Any]:
    feature_selection: list[dict[str, Any]] = []
    data_inputs: list[str] = []
    metrics: list[dict[str, Any]] = []
    metric_lines: set[tuple[str, int]] = set()
    model_names_regex: set[str] = set()
    for idx, raw in enumerate(code.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        is_import = bool(re.match(r"^\s*(?:import|from)\s+", raw))
        for technique, pattern in _FEATURE_SELECTION_PATTERNS:
            if not is_import and pattern.search(raw):
                feature_selection.append(
                    {"technique": technique, "line": idx, "snippet": stripped[:120]}
                )
        for match in _DATA_INPUT_RE.finditer(raw):
            data_inputs.append(match.group(1))
        if not is_import:
            for match in _MODEL_INSTANTIATION_RE.finditer(raw):
                model_names_regex.add(match.group(1))
        m = _METRIC_RE.search(raw)
        if m and not is_import and (m.group(1), idx) not in metric_lines:
            metric_lines.add((m.group(1), idx))
            metrics.append({"name": m.group(1), "line": idx, "snippet": stripped[:120]})
    return {
        "feature_selection": feature_selection,
        "data_inputs": list(dict.fromkeys(data_inputs)),
        "metrics": metrics,
        "model_names_regex": sorted(model_names_regex),
        "has_fit": bool(_FIT_RE.search(code)),
        "has_cv": bool(_CV_RE.search(code)),
    }


def _ast_pass(code: str) -> dict[str, Any]:
    """Enrich with imports / function names / model estimator hyperparameters when the code parses."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"imports": [], "functions": [], "model_names": [], "model_params": []}
    imports: set[str] = set()
    functions: list[str] = []
    model_names: set[str] = set()
    model_params: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.Call):
            func_name = ast.unparse(node.func)
            last_segment = func_name.split(".")[-1]
            if _ESTIMATOR_RE.match(last_segment):
                model_names.add(last_segment)
                for kw in node.keywords:
                    if kw.arg:
                        model_params.add(kw.arg)
    return {
        "imports": sorted(imports),
        "functions": functions,
        "model_names": sorted(model_names),
        "model_params": sorted(model_params),
    }


def analyze_training_logic(code: str) -> dict[str, Any]:
    """Heuristically analyze training code. Feature selection / data / metrics via regex
    (robust to notebook magics); imports / functions / model hyperparameters via ast when parseable."""
    base = _regex_pass(code)
    enriched = _ast_pass(code)
    model_names = sorted(set(base["model_names_regex"]) | set(enriched["model_names"]))
    return {
        "imports": enriched["imports"],
        "functions": enriched["functions"],
        "data_inputs": base["data_inputs"],
        "feature_selection": base["feature_selection"],
        "metrics": base["metrics"],
        "model": {
            "names": model_names,
            "params": enriched["model_params"],
            "has_fit": base["has_fit"],
        },
        "has_cv": base["has_cv"],
    }


def render_skill_md(
    version: str,
    name: str,
    source_type: str,
    analysis: dict[str, Any],
    source_rel: str,
) -> str:
    """Render a skill-creator-paradigm SKILL.md from the analysis."""
    slug = re.sub(r"[^a-z0-9]+", "-", f"{version}-{name}".lower()).strip("-") or "skill"
    feats = analysis.get("feature_selection") or []
    primary = feats[0]["technique"] if feats else "modeling"
    model = analysis.get("model") or {}
    metrics = analysis.get("metrics") or []
    inputs = analysis.get("data_inputs") or []

    description = (
        f"Reproduces the feature-selection + training recipe for {name}. "
        f"Use this skill when the user wants to retrain or reproduce {name}, reuse its "
        f"{primary} feature-selection pipeline, or apply the same selection to new data. "
        f'Trigger on phrases like "reproduce {name}", "retrain using {name}", '
        f'"apply {name} feature selection", or any request to recreate this modeling pipeline.'
    )

    lines = [
        "---",
        f"name: {slug}",
        f"description: {description}",
        "---",
        "",
        f"# Skill: {name} (from `{source_rel}`)",
        "",
        f"> Heuristically extracted from `{source_rel}`. The authoritative runnable source is "
        f"`references/source.py`; this SKILL.md is a guide — verify against it. Full structured "
        f"detection lives in `references/analysis.yaml`.",
        "",
        "## When to use",
        f"- Reproduce `{name}`'s feature-selection + training pipeline.",
        "- Adapt the same selection strategy to a new dataset or model.",
        f"- Onboard to how `{name}` was built.",
        "",
        "## Feature-selection strategy",
    ]
    if feats:
        lines.append("Detected techniques (line numbers refer to `references/source.py`):")
        lines.append("")
        for hit in feats:
            lines.append(f"- **L{hit['line']} — {hit['technique']}**: `{hit['snippet']}`")
    else:
        funcs = analysis.get("functions") or []
        lines.append(
            "No explicit feature-selection call detected. Inspect the function definitions in "
            f"`references/source.py`: {', '.join(funcs) if funcs else '(none found)'}."
        )

    lines += ["", "## Training procedure"]
    names = model.get("names") or []
    if names:
        lines.append(f"- **Model**: {', '.join(names)}.")
        params = model.get("params") or []
        if params:
            lines.append(f"- **Hyperparameters seen**: {', '.join(params)}.")
    else:
        lines.append("- No standard estimator instantiation detected; see `references/source.py`.")
    if inputs:
        lines.append(f"- **Inputs**: {', '.join(str(x) for x in inputs)}.")
    fit_note = "present" if model.get("has_fit") else "not found"
    cv_note = "cross-validation detected" if analysis.get("has_cv") else "no cross-validation detected (single holdout)"
    lines.append(f"- **`.fit()`**: {fit_note}.  | **{cv_note}**.")

    lines += ["", "## Reproduce", "1. Run `python references/source.py`."]
    if inputs:
        lines.append(f"2. Expected inputs: {', '.join(str(x) for x in inputs)}.")
    if metrics:
        lines.append(f"3. Expected output metric(s): {', '.join(str(m.get('name')) for m in metrics)}.")

    lines += ["", "## Gotchas"]
    techniques = {h["technique"] for h in feats}
    if "feature_importances_" in techniques:
        lines.append("- `feature_importances_` was used — importance is model-specific; do not generalize across model families.")
    if "coef_" in techniques:
        lines.append("- `coef_` was used — sign/magnitude depend on regularization and solver.")
    if not analysis.get("has_cv"):
        lines.append("- No cross-validation detected — the reported metric is a point estimate, not a CV mean.")
    lines.append("- Detection is heuristic: selection inside `def` bodies or custom non-sklearn code may be missed — cross-check `references/source.py`.")
    lines.append("- Full structured detection (imports, calls, metrics, line refs): `references/analysis.yaml`.")
    lines.append("")
    return "\n".join(lines)


def resolve_source_evidence(root: Path, source_evidence: list[str]) -> Path | None:
    """Return the first resolvable .ipynb/.py path in source_evidence, else None.

    Evidence strings are opaque, so each is resolved against several bases: absolute path,
    the repo root (root.parent), the memory root, and the cwd. The first existing code file wins.
    """
    root = Path(root)
    bases = [root.parent, root, Path.cwd()]
    for entry in source_evidence or []:
        path = Path(entry)
        candidates = [path] if path.is_absolute() else [base / entry for base in bases]
        for candidate in candidates:
            if candidate.exists() and candidate.suffix.lower() in _CODE_SUFFIXES:
                return candidate
    return None
