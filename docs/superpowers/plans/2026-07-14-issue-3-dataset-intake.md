# Issue #3 Dataset Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inspect explicit feature and label CSVs, require human-confirmed classification semantics, save immutable Dataset Versions in Team Memory, and show the latest confirmed version through the CLI and Dataset Overview UI.

**Architecture:** Add a v0.4 dataset slice behind `DomainCore` while preserving the legacy `DatasetService`. `DatasetInspector` owns read-only profiling and strict normalization; `DatasetRepository` owns capacity-checked immutable version assets under `datasets/`; CLI and Streamlit adapters only serialize or render Domain Core results.

**Tech Stack:** Python 3.11+, frozen dataclasses, pandas, scikit-learn stratified splitting, SHA-256, ordinary filesystem/Git assets, Streamlit, and pytest.

---

## File Map

- Modify `src/domain/models.py`: dataset commands, inspection, preview, and version snapshots.
- Create `src/domain/dataset_intake.py`: CSV inference, validation, profiling, canonicalization, splitting, and bounded previews.
- Create `src/domain/dataset_repository.py`: immutable Dataset Version persistence, reload validation, versioning, and capacity guards.
- Modify `src/domain/core.py`: public inspect, confirm, and overview methods.
- Modify `src/agent/main.py`: `intake-data` adapter with pending and confirmed JSON output.
- Modify `src/agent/slash_commands.py`: register the v0.4 workflow command.
- Modify `src/ui/shell.py`: dataset-aware context and module status.
- Modify `src/ui/app.py`: render the latest Dataset Version overview.
- Add focused unit, contract, and integration tests under `tests/`.

### Task 1: Define the Dataset Intake domain contract

**Files:**
- Modify: `src/domain/models.py`
- Create: `tests/unit/test_dataset_intake_models.py`

- [ ] **Step 1: Write failing serialization and immutability tests**

```python
def test_dataset_inspection_serializes_bounded_preview():
    inspection = DatasetInspection(
        status="Pending confirmation",
        feature_path=Path("features.csv"),
        label_path=Path("labels.csv"),
        inferred_sample_id_col="sample_id",
        inferred_label_col="group",
        inferred_task_type="binary",
        class_labels=("case", "control"),
        sample_count=12,
        feature_count=3,
        dtypes={"f1": "float64"},
        missing_rates={"f1": 0.0},
        class_distribution={"case": 6, "control": 6},
        preview=DatasetPreview(columns=("sample_id", "f1", "group"), rows=(), omitted_count=2),
        unresolved_fields=("positive_class", "primary_metric", "split", "target_metric"),
        warnings=(),
        blockers=(),
        elapsed_ms=4,
    )

    assert inspection.to_dict()["preview"]["omitted_count"] == 2
    assert inspection.to_dict()["class_labels"] == ["case", "control"]
```

- [ ] **Step 2: Run the model test and confirm RED**

Run: `.venv/bin/pytest tests/unit/test_dataset_intake_models.py -q`

Expected: FAIL because the dataset domain models do not exist.

- [ ] **Step 3: Add frozen commands and snapshots using the existing `_to_jsonable` helper**

```python
@dataclass(frozen=True)
class InspectDatasetCommand:
    feature_path: Path
    label_path: Path
    sample_id_col: str | None = None
    label_col: str | None = None


@dataclass(frozen=True)
class ConfirmDatasetCommand:
    connection_path: Path
    feature_path: Path
    label_path: Path
    sample_id_col: str
    label_col: str
    task_type: str
    primary_metric: str
    split_strategy: str
    target_metric: float
    positive_class: str | None = None
    test_ratio: float | None = None
    random_seed: int = 42
    dataset_id: str | None = None
```

Add `DatasetPreview`, `DatasetInspection`, and `DatasetVersionSnapshot` with only JSON-safe, adapter-facing fields.

- [ ] **Step 4: Run the model tests and confirm GREEN**

Run: `.venv/bin/pytest tests/unit/test_dataset_intake_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the contract**

```bash
git add src/domain/models.py tests/unit/test_dataset_intake_models.py
git commit -m "feat(dataset): define intake domain contract"
```

### Task 2: Inspect and validate classification data without writing

**Files:**
- Create: `src/domain/dataset_intake.py`
- Create: `tests/integration/test_dataset_inspection.py`

- [ ] **Step 1: Write failing inspection tests**

Create temporary CSV pairs and assert:

```python
inspection = DatasetInspector().inspect(
    InspectDatasetCommand(feature_path=features, label_path=labels)
)

assert inspection.status == "Pending confirmation"
assert inspection.inferred_task_type == "binary"
assert inspection.unresolved_fields == (
    "positive_class",
    "primary_metric",
    "split_strategy",
    "target_metric",
)
assert len(inspection.preview.rows) <= 10
```

Add cases for multiclass inference, an omission count for more than ten rows,
missing feature values, ambiguous columns, mismatched samples, duplicate IDs,
and missing labels.

- [ ] **Step 2: Run inspection tests and confirm RED**

Run: `.venv/bin/pytest tests/integration/test_dataset_inspection.py -q`

Expected: FAIL because `DatasetInspector` does not exist.

- [ ] **Step 3: Implement bounded inspection and strict confirmation normalization**

`DatasetInspector.inspect` reads explicit CSV files, infers conventional
`sample_id`/`id` and `label`/`group`/`status` columns, profiles the selected
columns, and returns blockers instead of writing assets. Add
`DatasetInspector.normalize(command)` returning an internal `NormalizedDataset`
containing canonical feature, label, and split DataFrames plus all hashes and
summary values required by the repository.

Use `train_test_split(..., stratify=labels, random_state=random_seed)` for
`stratified_random`; use an all-train assignment for `train_only`. Raise stable
`WorkspaceError` codes such as `duplicate_sample_id`, `sample_mismatch`,
`missing_label`, `unsupported_task`, `invalid_metric`, and `invalid_split`.

- [ ] **Step 4: Pass inspection and normalization tests**

Run: `.venv/bin/pytest tests/integration/test_dataset_inspection.py -q`

Expected: PASS for binary, multiclass, pending, structural failures, and bounded preview.

- [ ] **Step 5: Commit the inspector**

```bash
git add src/domain/dataset_intake.py tests/integration/test_dataset_inspection.py
git commit -m "feat(dataset): inspect classification inputs"
```

### Task 3: Persist and reload immutable Dataset Versions

**Files:**
- Create: `src/domain/dataset_repository.py`
- Create: `tests/integration/test_dataset_version_repository.py`

- [ ] **Step 1: Write failing repository tests against a temporary Team Memory workspace**

```python
created = repository.create_version(
    normalized,
    actor_id="alice",
    capacity=workspace.capacity,
)
repeated = repository.create_version(
    normalized,
    actor_id="alice",
    capacity=workspace.capacity,
)

assert created.version == repeated.version == 1
assert created.asset_path == "datasets/ds-1/v0001/manifest.json"
assert repository.load("ds-1", 1).version_fingerprint == created.version_fingerprint
```

Add tests proving changed labels, split, or schema create `v0002`; existing
version bytes remain unchanged; path traversal IDs are rejected; a tampered file
fails reload; and projected single-file/repository capacity is rejected before a
version directory appears.

- [ ] **Step 2: Run repository tests and confirm RED**

Run: `.venv/bin/pytest tests/integration/test_dataset_version_repository.py -q`

Expected: FAIL because `DatasetRepository` does not exist.

- [ ] **Step 3: Implement atomic, append-only version storage**

Write deterministic `features.csv`, `labels.csv`, `split.csv`, and
`manifest.json` into a temporary sibling directory. Validate all encoded file
sizes and projected repository size, then rename to `vNNNN`. Never replace an
existing version. Scan existing manifests to return an identical fingerprint
idempotently or allocate the next integer version.

The manifest must include Local Index fields:

```json
{
  "asset_type": "dataset_version",
  "asset_id": "ds-1-v0001",
  "dataset_id": "ds-1",
  "version": 1,
  "state": "confirmed"
}
```

Reload must recompute file and version fingerprints before returning a snapshot.

- [ ] **Step 4: Pass repository and Local Index compatibility tests**

Run: `.venv/bin/pytest tests/integration/test_dataset_version_repository.py tests/integration/test_local_index_rebuild.py -q`

Expected: PASS; after a test commit and index rebuild, the Dataset Version is listed as a `dataset_version` asset.

- [ ] **Step 5: Commit immutable persistence**

```bash
git add src/domain/dataset_repository.py tests/integration/test_dataset_version_repository.py
git commit -m "feat(dataset): persist immutable dataset versions"
```

### Task 4: Expose intake through Domain Core and `intake-data`

**Files:**
- Modify: `src/domain/core.py`
- Modify: `src/agent/main.py`
- Modify: `src/agent/slash_commands.py`
- Create: `tests/contract/test_domain_core_dataset_intake.py`
- Create: `tests/integration/test_intake_data_cli.py`

- [ ] **Step 1: Write failing Domain Core and CLI tests**

```python
inspection = core.inspect_dataset(
    InspectDatasetCommand(feature_path=features, label_path=labels)
)
version = core.confirm_dataset(
    ConfirmDatasetCommand(
        connection_path=connection,
        feature_path=features,
        label_path=labels,
        sample_id_col="sample_id",
        label_col="group",
        task_type="binary",
        positive_class="case",
        primary_metric="roc_auc",
        split_strategy="train_only",
        target_metric=0.9,
    )
)

assert inspection.status == "Pending confirmation"
assert core.get_dataset_overview(connection).asset_id == version.asset_id
```

CLI tests call `intake-data` once without `--confirm` and once with complete
confirmation options. Assert actionable JSON and exit `2` for unsupported task or
missing confirmation fields.

- [ ] **Step 2: Run adapter tests and confirm RED**

Run: `.venv/bin/pytest tests/contract/test_domain_core_dataset_intake.py tests/integration/test_intake_data_cli.py -q`

Expected: FAIL because the Domain Core methods and command are absent.

- [ ] **Step 3: Implement the single application seam and thin CLI adapter**

`confirm_dataset` loads the workspace connection, opens Team Memory for actor
and capacity state, normalizes the data, creates the immutable version, and
returns it. `get_dataset_overview` returns the latest version when no ID/version
is supplied. Register `intake-data` while preserving legacy `intake`.

- [ ] **Step 4: Pass Domain Core, CLI, and regression tests**

Run: `.venv/bin/pytest tests/contract/test_domain_core_dataset_intake.py tests/integration/test_intake_data_cli.py tests/integration/test_intake_cli.py tests/contract/test_slash_commands.py -q`

Expected: PASS with JSON-safe pending, confirmed, and error output.

- [ ] **Step 5: Commit the public workflow**

```bash
git add src/domain/core.py src/agent/main.py src/agent/slash_commands.py tests/contract/test_domain_core_dataset_intake.py tests/integration/test_intake_data_cli.py
git commit -m "feat(cli): add authoritative intake-data workflow"
```

### Task 5: Render Dataset Overview from the confirmed asset

**Files:**
- Modify: `src/ui/shell.py`
- Modify: `src/ui/app.py`
- Modify: `tests/contract/test_ui_shell.py`
- Create: `tests/integration/test_dataset_overview_ui.py`

- [ ] **Step 1: Write failing shell and Streamlit tests**

```python
shell = build_shell_state(workspace_snapshot(), dataset_version())

assert shell.context["dataset"] == "ds-1 v1"
assert shell.module_status["Dataset Overview"] == "Success"
```

The AppTest confirms Dataset Overview shows version, task, metric, sample/feature
counts, class distribution, field summary, warnings, and the omission marker.
Also assert no dataset leaves context and module state as `Not started`.

- [ ] **Step 2: Run UI tests and confirm RED**

Run: `.venv/bin/pytest tests/contract/test_ui_shell.py tests/integration/test_dataset_overview_ui.py -q`

Expected: FAIL because the shell and app do not load Dataset Version state.

- [ ] **Step 3: Implement the dataset-aware shell and compact overview**

Load the latest overview through `DomainCore`; do not read Team Memory files in
the UI. Render fixed-size metrics, task/evaluation facts, a Pandas-style
head/omission/tail dataframe, class distribution, and field type/missingness.
Keep every other module and the six-item navigation unchanged.

- [ ] **Step 4: Pass UI and performance tests**

Run: `.venv/bin/pytest tests/contract/test_ui_shell.py tests/integration/test_streamlit_workspace_shell.py tests/integration/test_dataset_overview_ui.py -q`

Expected: PASS and the local inspection performance case completes under three seconds.

- [ ] **Step 5: Commit Dataset Overview**

```bash
git add src/ui/shell.py src/ui/app.py tests/contract/test_ui_shell.py tests/integration/test_dataset_overview_ui.py
git commit -m "feat(ui): render confirmed dataset overview"
```

### Task 6: Review, verify, and publish Issue #3

**Files:**
- Modify only files required by review findings.

- [ ] **Step 1: Run the focused Issue #3 suite**

Run: `.venv/bin/pytest tests/unit/test_dataset_intake_models.py tests/integration/test_dataset_inspection.py tests/integration/test_dataset_version_repository.py tests/contract/test_domain_core_dataset_intake.py tests/integration/test_intake_data_cli.py tests/contract/test_ui_shell.py tests/integration/test_dataset_overview_ui.py -q`

Expected: all Issue #3 tests pass.

- [ ] **Step 2: Run the full suite and compile check**

Run: `.venv/bin/pytest -q`

Run: `.venv/bin/python -m compileall -q src tests`

Expected: all tests and compilation pass.

- [ ] **Step 3: Review the stacked diff**

Run the code-review skill against `feat/issue-2-memory-bootstrap`, checking PRD
semantics, immutable versioning, path and capacity safety, adapter delegation,
performance, UI states, and missing acceptance tests. Resolve every actionable
P1/P2 finding and rerun affected tests.

- [ ] **Step 4: Verify branch state**

Run: `git status --short`

Run: `git log --oneline feat/issue-2-memory-bootstrap..HEAD`

Run: `git diff --check feat/issue-2-memory-bootstrap...HEAD`

Expected: clean worktree, intentional commits only, and no whitespace errors.

- [ ] **Step 5: Publish for human review**

Push `feat/issue-3-dataset-intake`, post verification evidence to GitHub #3,
and change only #3 from `ready-for-agent` to `ready-for-human`. Preserve the
stacked worktree for review follow-up.
