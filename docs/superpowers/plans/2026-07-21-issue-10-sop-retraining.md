# Issue #10 — Implementation Plan

> Design: [2026-07-21-issue-10-sop-retraining-design.md](../specs/2026-07-21-issue-10-sop-retraining-design.md)

## Tasks (TDD order)

### T1: Models — `RetrainFromSopCommand`, `RetrainFromSopResult`, `SopRetrainCompatibilityReport`
Add to `src/domain/models.py`. Unit tests for field validation.

### T2: Compatibility checker — `src/domain/sop_retrain.py`
Pure function `check_retrain_compatibility(sop_version, new_dataset) -> SopRetrainCompatibilityReport`.
Checks: metric name, task type, feature schema, label column.
Unit tests with compatible/incompatible fixtures.

### T3: DomainCore — `retrain_from_sop(command)`
1. Load SOP Version + new Dataset Version
2. Run compatibility check → reject if incompatible
3. Lock SOP steps/config
4. Execute training via existing TrainingRunCoordinator
5. Record raw record with SOP provenance
6. Return RetrainFromSopResult

### T4: Retrain provenance in Run
Tag the Run with `source_sop_id` + `source_sop_version` in its metadata so the UI and lineage can identify retrain runs.

### T5: UI — Run Status SOP retrain badge + SOP Overview retrain history
- Run Status: show "🔄 SOP 重训" badge + baseline comparison
- SOP Overview: show retrain history section

### T6: Full verification + commit + push + Issue comment

## File ownership

| File | Change |
|---|---|
| `src/domain/models.py` | Add 3 new dataclasses |
| `src/domain/sop_retrain.py` | **New** — compatibility checker |
| `src/domain/core.py` | Add `retrain_from_sop()` method |
| `src/ui/app.py` | Run Status + SOP Overview UI |
| `tests/unit/test_sop_retrain_compat.py` | **New** |
| `tests/integration/test_retrain_from_sop.py` | **New** |
