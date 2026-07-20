# Issue #9 — Notebook Import & Reproduction Design

> Date: 2026-07-20 · Branch: `feat/issue-9-notebook-import` · Baseline: `5dcfa89`
> Parent: [v0.4 PRD](../../../specs/002-mlagent-plugin-memory-sop/prd.md) FR-062, AC-09
> Constraints: [HANDOFF](../../../HANDOFF.md) §3, §5, §8

## 1. Goal

Import a researcher-authored `.ipynb`, preserve it immutably, parse its training logic, execute it in a controlled environment, and—if successful—seal the result as a Training Instance that enters the **existing** SOP promotion flow. On any failure, save only the import record, parse report and evidence; never create a SOP Candidate or Formal Model.

## 2. Flow

```text
User provides .ipynb path + confirmed Dataset Version
  │
  ▼
DomainCore.import_notebook(command)
  │
  ├─ 1. PRESERVE: copy original .ipynb to Team Memory; compute SHA-256 fingerprint
  │     → NotebookImport asset (id, fingerprint, source_path, importer, timestamp)
  │
  ├─ 2. PARSE: NotebookParser reads .ipynb JSON
  │     → NotebookParseReport (cells, deps, data_paths, randomness, split, metrics, warnings)
  │     → warnings: missing_deps, hidden_paths, implicit_state, unclear_randomness, interactive
  │
  ├─ 3. GATE: if blocking warnings (missing_deps, interactive, unclear_randomness)
  │     → return NotebookImportSnapshot(state="parse_blocked"); no execution
  │
  ├─ 4. EXECUTE: extract code cells → frozen Code Revision → controlled execution
  │     → uses existing TrainingRunCoordinator with a notebook-derived plan
  │     → if failure: return NotebookImportSnapshot(state="execution_failed"); no SOP
  │
  ├─ 5. SEAL: success → Training Instance (same schema as any TI)
  │     → provenance edge: notebook_import → training_instance
  │
  └─ 6. RETURN: NotebookImportSnapshot with parse_report + instance reference (or error)
```

## 3. New Models (`src/domain/models.py`)

```python
@dataclass(frozen=True)
class ImportNotebookCommand:
    connection_path: Path
    notebook_path: Path          # local .ipynb to import
    source_description: str      # human-readable source provenance
    dataset_id: str              # confirmed dataset to bind
    dataset_version: str
    code_root: Path              # where to place extracted code

@dataclass(frozen=True)
class NotebookCellInfo:
    index: int
    cell_type: str               # code | markdown
    source_lines: int
    has_outputs: bool

@dataclass(frozen=True)
class NotebookParseWarning:
    kind: str                    # missing_dependency | hidden_path | implicit_state | unclear_randomness | interactive_step | non_portable_path
    detail: str
    blocking: bool               # True = cannot proceed to execution

@dataclass(frozen=True)
class NotebookParseReport:
    cells: tuple[NotebookCellInfo, ...]
    detected_dependencies: tuple[str, ...]     # import statements
    detected_data_paths: tuple[str, ...]       # file paths referenced
    detected_randomness: tuple[str, ...]       # random_state, seed, etc.
    detected_split: str | None                 # train_test_split, KFold, etc.
    detected_metrics: tuple[str, ...]          # roc_auc_score, accuracy_score, etc.
    detected_model: str | None                # RandomForest, XGBoost, etc.
    warnings: tuple[NotebookParseWarning, ...]
    content_fingerprint: str

@dataclass(frozen=True)
class NotebookImportSnapshot:
    asset_id: str
    asset_path: str              # team-memory path to the import record
    original_path: str           # source .ipynb path
    content_fingerprint: str
    importer: str
    imported_at: str
    source_description: str
    parse_report: NotebookParseReport
    state: str                   # preserved | parse_blocked | execution_failed | reproduced
    training_instance_id: str | None
    training_run_id: str | None
    error_code: str | None
    error_summary: str | None
```

## 4. New Module: `src/domain/notebook_parser.py`

Pure-function module (no side effects, no I/O except reading the .ipynb):

- `parse_notebook(path: Path) -> NotebookParseReport`
- Internally uses `json` to read .ipynb v4 format (no `nbformat` dependency required for parsing; `nbformat` is only needed if we execute via nbclient, which we don't — we extract code and execute via the existing `SubprocessTrainingExecutor`)
- Extracts: cell metadata, code source, import statements, file-path references, randomness patterns, split patterns, metric patterns, model class names
- Produces warnings for: undeclared dependencies, absolute/local paths, missing random_state, `%matplotlib inline` / `!` shell magics, undefined variables from interactive sessions

## 5. New Repository: `src/domain/notebook_repository.py`

Follows the existing repository pattern (`dataset_repository.py`, `sop_repository.py`):

- `store_import(repo_path, original_bytes, fingerprint, importer, source, parse_report, actor_id, capacity) -> NotebookImportSnapshot`
  - Copies the original `.ipynb` bytes to `notebooks/originals/<fingerprint[:12]>.ipynb`
  - Writes `notebooks/imports/<asset_id>.json` (the import record with parse report)
  - Returns the snapshot
- `link_instance(repo_path, import_id, instance_id, run_id) -> None`
  - Updates the import record with the reproduced instance reference
  - Adds provenance edge
- `get_import(repo_path, asset_id) -> NotebookImportSnapshot`

## 6. DomainCore Extension (`src/domain/core.py`)

```python
def import_notebook(self, command: ImportNotebookCommand) -> NotebookImportSnapshot:
    # 1. open connection + repository
    # 2. read + fingerprint the .ipynb
    # 3. parse → NotebookParseReport
    # 4. store import asset (original + record) via NotebookRepository
    # 5. check blocking warnings → if any, return state="parse_blocked"
    # 6. extract code → write frozen script to code_root
    # 7. execute via existing training infrastructure (TrainingRunCoordinator or similar)
    # 8. on success: link instance; on failure: record error
    # 9. rebuild local index
    # 10. return NotebookImportSnapshot
```

## 7. Provenance

The import record carries:
- `source_path` → the original .ipynb location
- `content_fingerprint` → SHA-256 of the original bytes
- `training_instance_id` → the sealed instance (if successful)

The lineage system (Issue #14, not yet built) will consume these typed edges. For now, the import record JSON is the provenance source.

## 8. UI Changes

Minimal: the SOP Overview module shows a "Notebook Source" badge when a SOP candidate's source instance originated from a notebook import. The lineage module (Issue #14) will add full graph navigation.

For this issue: add a `notebook_origin` field to `SopCandidateSnapshot` (optional, None for regular instances).

## 9. Boundary Compliance

| Boundary | How satisfied |
|---|---|
| Original preserved immutably | Copied to `notebooks/originals/`; SHA-256 fingerprint; never modified |
| Parse before execute | Step 2 (parse) precedes Step 4 (execute); blocking warnings halt |
| Failure → no SOP | On parse_blocked or execution_failed, no instance is created; `create_sop_candidate` requires a real instance_id |
| Success → existing SOP flow | The TI is a regular `TrainingInstanceSnapshot`; `create_sop_candidate` works unchanged |
| Experience ≠ SOP source | Not touched; notebook import creates a TI, not an experience |
| All writes via DomainCore | `import_notebook` is the sole entry; UI/CLI/Hook call it |
| Team Memory authoritative | Original + import record stored in Git; Local Index rebuildable |
| No scope creep | No refactoring of existing modules; new code in new files + minimal additions to `models.py` and `core.py` |

## 10. Test Plan

| Test | AC coverage |
|---|---|
| `test_import_preserves_original_and_fingerprint` | AC-1 |
| `test_parse_report_identifies_data_model_randomness_metrics` | AC-2 |
| `test_parse_warnings_for_missing_deps_and_hidden_paths` | AC-3 |
| `test_parse_warnings_for_unclear_randomness` | AC-3 |
| `test_successful_execution_creates_training_instance` | AC-4 |
| `test_execution_failure_preserves_report_without_sop` | AC-5 |
| `test_reproduced_instance_enters_sop_candidate_flow` | AC-6 |
| `test_notebook_origin_visible_in_sop_overview` | AC-7 |
| `test_notebook_import_provenance_edges` | AC-7 |
| `test_blocking_warning_prevents_execution` | AC-3, AC-5 |
