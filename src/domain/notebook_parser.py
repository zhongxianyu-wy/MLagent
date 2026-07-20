"""Notebook parser — pure functions to analyse .ipynb training logic.

No side effects, no I/O beyond reading the file. Produces a structured
``NotebookParseReport`` with detected components and warnings.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from src.domain.models import NotebookCellInfo, NotebookParseReport, NotebookParseWarning

# ── detection patterns ────────────────────────────────────────────────

_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([\w.]+)")
_DATA_PATH_RE = re.compile(
    r"(?:read_csv|read_excel|read_parquet|read_table|load|open|read_hdf)"
    r"\s*\(\s*['\"]([^'\"]+)['\"]"
)
_RANDOMNESS_RE = re.compile(
    r"\b(random_state|seed|np\.random|torch\.manual_seed|tf\.random)"
)
_SPLIT_RE = re.compile(
    r"\b(train_test_split|KFold|StratifiedKFold|StratifiedShuffleSplit|RepeatedKFold)"
)
_METRIC_RE = re.compile(
    r"\b(roc_auc_score|accuracy_score|f1_score|precision_score|recall_score|"
    r"average_precision_score|log_loss|brier_score_loss|classification_report)"
    r"\s*\("
)
_MODEL_RE = re.compile(
    r"\b([A-Z]\w*(?:Classifier|Regressor|Regression))"
)
_ABSOLUTE_PATH_RE = re.compile(r"['\"](/[^'\"]+)['\"]")
_HOME_PATH_RE = re.compile(r"['\"](~[^'\"]*)['\"]")
_MAGIC_RE = re.compile(r"^\s*(%|!)")
_MISSING_DEP_PACKAGES = {
    "torch", "tensorflow", "keras", "transformers",
    "lightgbm", "xgboost", "catboost", "fastai",
}


def parse_notebook(path: Path) -> NotebookParseReport:
    """Parse a .ipynb file and return a structured report."""
    raw = path.read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    nb = json.loads(raw)
    cells_raw = nb.get("cells", [])

    cells: list[NotebookCellInfo] = []
    code_lines: list[str] = []

    for idx, cell in enumerate(cells_raw):
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        cell_type = cell.get("cell_type", "code")
        line_count = source.count("\n") + 1 if source.strip() else 0
        has_outputs = bool(cell.get("outputs"))
        cells.append(NotebookCellInfo(
            index=idx,
            cell_type=cell_type,
            source_lines=line_count,
            has_outputs=has_outputs,
        ))
        if cell_type == "code":
            code_lines.append(source)

    code = "\n".join(code_lines)

    return NotebookParseReport(
        cells=tuple(cells),
        detected_dependencies=tuple(_detect_imports(code)),
        detected_data_paths=tuple(_detect_data_paths(code)),
        detected_randomness=tuple(_detect_randomness(code)),
        detected_split=_detect_split(code),
        detected_metrics=tuple(_detect_metrics(code)),
        detected_model=_detect_model(code),
        warnings=tuple(_detect_warnings(code, cells_raw)),
        content_fingerprint=fingerprint,
    )


def _detect_imports(code: str) -> list[str]:
    seen: list[str] = []
    for line in code.splitlines():
        m = _IMPORT_RE.match(line)
        if m:
            mod = m.group(1)
            if mod not in seen:
                seen.append(mod)
    return seen


def _detect_data_paths(code: str) -> list[str]:
    paths: list[str] = []
    for m in _DATA_PATH_RE.finditer(code):
        p = m.group(1)
        if p not in paths:
            paths.append(p)
    return paths


def _detect_randomness(code: str) -> list[str]:
    found: list[str] = []
    for m in _RANDOMNESS_RE.finditer(code):
        token = m.group(1) if m.group(1) else m.group(0)
        if token not in found:
            found.append(token)
    return found


def _detect_split(code: str) -> str | None:
    m = _SPLIT_RE.search(code)
    return m.group(1) if m else None


def _detect_metrics(code: str) -> list[str]:
    found: list[str] = []
    for m in _METRIC_RE.finditer(code):
        if m.group(1) not in found:
            found.append(m.group(1))
    return found


def _detect_model(code: str) -> str | None:
    m = _MODEL_RE.search(code)
    return m.group(1) if m else None


def _detect_warnings(
    code: str, cells_raw: list[dict],
) -> list[NotebookParseWarning]:
    warnings: list[NotebookParseWarning] = []
    lines = code.splitlines()

    # missing dependencies (blocking)
    for line in lines:
        m = _IMPORT_RE.match(line)
        if m and m.group(1).split(".")[0] in _MISSING_DEP_PACKAGES:
            warnings.append(NotebookParseWarning(
                kind="missing_dependency",
                detail=f"Import of '{m.group(1)}' may not be available.",
                blocking=True,
            ))

    # interactive steps (blocking)
    for line in lines:
        if _MAGIC_RE.match(line):
            warnings.append(NotebookParseWarning(
                kind="interactive_step",
                detail=f"Magic or shell command: '{line.strip()[:80]}'",
                blocking=True,
            ))

    # unclear randomness (blocking) — uses split/model but no random_state/seed
    has_split = _SPLIT_RE.search(code) is not None
    has_model = _MODEL_RE.search(code) is not None
    has_randomness = bool(_RANDOMNESS_RE.search(code))
    if (has_split or has_model) and not has_randomness:
        warnings.append(NotebookParseWarning(
            kind="unclear_randomness",
            detail="Training/split code found without explicit random_state or seed.",
            blocking=True,
        ))

    # hidden / non-portable paths (non-blocking)
    for m in _ABSOLUTE_PATH_RE.finditer(code):
        warnings.append(NotebookParseWarning(
            kind="hidden_path",
            detail=f"Absolute path detected: '{m.group(1)}'",
            blocking=False,
        ))
    for m in _HOME_PATH_RE.finditer(code):
        warnings.append(NotebookParseWarning(
            kind="non_portable_path",
            detail=f"Home-relative path detected: '{m.group(1)}'",
            blocking=False,
        ))

    return warnings


def extract_notebook_code(path: Path) -> str:
    """Extract code cells from a .ipynb and return them as a single Python script."""
    raw = path.read_bytes()
    nb = json.loads(raw)
    parts: list[str] = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        stripped = source.strip()
        if not stripped:
            continue
        # skip magic/shell lines
        lines = [ln for ln in stripped.splitlines() if not _MAGIC_RE.match(ln)]
        if lines:
            parts.append("\n".join(lines))
    return "\n\n".join(parts)
