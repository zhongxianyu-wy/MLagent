# Issue #10 — SOP Retraining Design

> Date: 2026-07-21 · Branch: `feat/issue-10-sop-retraining` · Baseline: `feat/issue-9-notebook-import`
> Parent: [v0.4 PRD](../../../specs/002-mlagent-plugin-memory-sop/prd.md) FR-071, AC-12
> Constraints: [HANDOFF](../../../HANDOFF.md) §3 boundaries #8, #13

## 1. Goal

Select an approved SOP Version + a new compatible Dataset Version → lock the SOP's steps/config → execute training → produce a new Run with Training Instance, Raw Record and candidate model. The result **never** auto-overwrites the SOP Version or Formal Model registry. The user may separately submit the candidate through the normal SOP approval flow.

## 2. Flow

```text
User selects: SOP Version (sop_id, version) + new Dataset Version
  │
  ▼
DomainCore.retrain_from_sop(command)
  │
  ├─ 1. VALIDATE: load approved SOP Version from SopRepository
  │     load new Dataset Version from DatasetRepository
  │     check compatibility (features, labels, task, metric, deps)
  │     → incompatible → WorkspaceError(code="sop_retrain_incompatible")
  │
  ├─ 2. LOCK: freeze SOP steps + config + entrypoint + env as the "retrain context"
  │     create a synthetic ExplorationPlan-like spec from the SOP (not stored as
  │     a permanent plan — it's a transient execution context)
  │
  ├─ 3. EXECUTE: delegate to TrainingRunCoordinator via a dedicated RunRepository
  │     (same run/instance infrastructure as exploration, but tagged with
  │      `sop_retrain` provenance: sop_id, sop_version, source_dataset_version)
  │     → produces: Run + Training Instance + metrics + candidate model
  │
  ├─ 4. RECORD: write a Raw Record referencing the SOP + new dataset + result
  │     write provenance edge: sop_version → retrain_run → instance
  │
  └─ 5. RETURN: RetrainFromSopResult snapshot
        (run_id, instance_id, metric_value, sop_baseline, delta,
         candidate_model_id, formal_model_unchanged=True)
```

## 3. New Models

```python
@dataclass(frozen=True)
class RetrainFromSopCommand:
    connection_path: Path
    sop_id: str
    sop_version: int
    dataset_id: str           # new dataset (may be same ID, different version)
    dataset_version: int      # new version
    code_root: Path
    entrypoint_path: str | None = None
    human_marked_rounds: tuple[int, ...] = ()

@dataclass(frozen=True)
class RetrainFromSopResult:
    run_id: str
    instance_id: str
    primary_metric_name: str
    primary_metric_value: float | None
    sop_primary_metric_value: float
    delta: float | None         # new_value - sop_value (positive = improvement)
    candidate_model_id: str | None
    sop_version_unchanged: bool  # always True — SOP is never mutated
    formal_model_unchanged: bool # always True
    error_code: str | None
    error_summary: str | None

@dataclass(frozen=True)
class SopRetrainCompatibilityReport:
    compatible: bool
    checks: tuple[tuple[str, str, bool], ...]  # (check_name, detail, passed)
    # e.g. ("primary_metric", "roc_auc == roc_auc", True)
```

## 4. Compatibility Checks

Before execution, verify the new dataset is compatible with the SOP:

| Check | Rule |
|---|---|
| Primary metric | SOP's `primary_metric_name` must be computable on new dataset |
| Task type | Dataset's task type must match SOP's original task |
| Feature schema | New dataset must have ≥ the SOP's original features (extra OK, missing = fail) |
| Label semantics | Label column must exist with same positive class definition |
| Entrypoint | SOP's frozen code must be available and executable |

Incompatibility → `WorkspaceError(code="sop_retrain_incompatible")` with the specific check that failed.

## 5. Provenance

The retrain Run, Instance and Raw Record all carry:
- `source_sop_id` + `source_sop_version` — which SOP was retrained
- `source_dataset_version` — the SOP's original dataset version
- `new_dataset_version` — the new data version used

This allows the UI and lineage to distinguish:
- Original SOP training runs (exploration)
- SOP reproduction runs (gate)
- SOP retraining runs (new data) ← **new**

## 6. UI Changes

**Run Status module:** When a run is tagged as `sop_retrain`, show:
- "🔄 SOP 重训" badge with SOP name + version
- Side-by-side: SOP baseline metric vs new metric vs delta (↑/↓ colored)

**SOP Overview module:** When viewing an approved SOP version, show:
- "重训历史" section listing all retrain runs on different datasets
- Each entry: dataset version, metric, delta, candidate model status

## 7. Boundary Compliance

| Boundary | How satisfied |
|---|---|
| New data result ≠ auto-overwrite SOP | `sop_version_unchanged=True` always; SOP files never written |
| New data result ≠ auto Formal Model | `formal_model_unchanged=True` always; Formal Model registry never touched |
| Result enters standard SOP flow if user chooses | The candidate instance can be used in `create_sop_candidate` like any other |
| Steps locked from SOP | Config extracted from SOP Version's `steps` + `environment`; no deviation allowed |
| Deviation → new exploration | If user wants different steps, they go through `design-and-explore` normally |
| All writes via DomainCore | `retrain_from_sop` is the sole entry |

## 8. Test Plan

| Test | AC |
|---|---|
| `test_retrain_compatible_dataset_produces_run` | AC-1,3 |
| `test_retrain_incompatible_metric_rejected` | AC-1 |
| `test_retrain_incompatible_task_type_rejected` | AC-1 |
| `test_retrain_incompatible_missing_features_rejected` | AC-1 |
| `test_retrain_does_not_mutate_sop_version` | AC-4 |
| `test_retrain_does_not_mutate_formal_model` | AC-4 |
| `test_retrain_performance_improvement_shows_positive_delta` | AC-5 |
| `test_retrain_performance_decline_shows_negative_delta` | AC-5 |
| `test_retrain_result_can_enter_sop_candidate_flow` | AC-6 |
| `test_retrain_raw_record_references_sop_and_dataset` | AC-3 |
