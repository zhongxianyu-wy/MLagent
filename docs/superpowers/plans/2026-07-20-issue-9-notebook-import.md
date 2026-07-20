# Issue #9 — Implementation Plan

> Design: [2026-07-20-issue-9-notebook-import-design.md](../specs/2026-07-20-issue-9-notebook-import-design.md)

## Tasks (TDD order)

### T1: Models — `ImportNotebookCommand`, `NotebookParseReport`, `NotebookImportSnapshot`
Add frozen dataclasses to `src/domain/models.py`. Write unit tests verifying field types and defaults.

### T2: Notebook parser — `src/domain/notebook_parser.py`
Pure functions: `parse_notebook(path) -> NotebookParseReport`. Uses stdlib `json` (no nbformat dep).
Tests with fixture `.ipynb` covering: clean notebook, missing deps, hidden paths, unclear randomness, interactive steps.

### T3: Notebook repository — `src/domain/notebook_repository.py`
`store_import()`, `link_instance()`, `get_import()`. Follows existing repo pattern (e.g., `dataset_repository.py`).
Integration tests with real tmp Git repo.

### T4: DomainCore — `import_notebook(command)`
Wire parser + repository + existing training execution. The method:
1. Read + fingerprint .ipynb
2. Parse
3. Store import asset
4. Gate on blocking warnings
5. Extract code → execute → TI or failure
6. Link + return snapshot

### T5: SOP candidate — `notebook_origin` field
Add optional `notebook_origin: NotebookOriginInfo | None` to `SopCandidateSnapshot`.
Populated when the source instance has a notebook import provenance edge.

### T6: UI — SOP Overview notebook badge
Show "📓 Notebook 来源" in SOP candidate detail when `notebook_origin` is present.

### T7: End-to-end + provenance tests
Full flow: import notebook → parse → execute → TI → create SOP candidate → verify lineage reference.

### T8: Verification gate
```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
```

## File ownership

| File | Change type |
|---|---|
| `src/domain/models.py` | Add new dataclasses |
| `src/domain/notebook_parser.py` | **New** |
| `src/domain/notebook_repository.py` | **New** |
| `src/domain/core.py` | Add `import_notebook` method |
| `src/domain/__init__.py` | Export new types if needed |
| `src/domain/sop_repository.py` | Add notebook_origin lookup |
| `src/ui/shell.py` | Add notebook badge to SOP view |
| `tests/unit/test_notebook_parser.py` | **New** |
| `tests/integration/test_notebook_import.py` | **New** |
| `tests/fixtures/notebooks/clean_baseline.ipynb` | **New** fixture |
| `tests/fixtures/notebooks/missing_deps.ipynb` | **New** fixture |
| `tests/fixtures/notebooks/no_seed.ipynb` | **New** fixture |
