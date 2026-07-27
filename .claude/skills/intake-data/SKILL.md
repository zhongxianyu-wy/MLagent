---
name: intake-data
description: Inspect feature/label matrices and confirm an immutable Dataset Version. Use when a researcher provides CSV feature and label files and wants to lock a reproducible dataset for exploration/training.
---

# Intake Data

Use when feature/label CSV files are provided and a confirmed Dataset Version is needed before planning or training.

## Boundary
Never mutate a confirmed Dataset Version in place. Never train or plan against an unconfirmed dataset. Validation must pass before confirmation.

## Preconditions
- A features CSV and a labels CSV (with a shared sample id column).
- A confirmed label column, task type (binary/multiclass), positive class, primary metric, and target.
- A bootstrapped workspace connection.

## Workflow
1. Inspect (read-only preview):
   ```bash
   python -m src.agent.main intake-data <features.csv> <labels.csv> \
       --workspace-config .mlagent-workspace.json
   ```
2. Review the inspection (schema, dtypes, missing rates, class balance).
3. Confirm the immutable version:
   ```bash
   python -m src.agent.main intake-data <features.csv> <labels.csv> \
       --confirm sample_id=<col>,label=<col>,task=binary,positive=<cls>,metric=roc_auc,target=0.9 \
       --workspace-config .mlagent-workspace.json
   ```

## Outputs
- `DatasetInspection` preview (pre-confirm).
- Immutable `DatasetVersionSnapshot` (state `confirmed`) under `datasets/<id>/v####/`.

## Failure and next step
- `invalid_dataset_file` / `invalid_split`: fix the CSV schema or split config.
- `dataset_fingerprint_mismatch`: restore the immutable version from Git; create a new version for changes.
- `dataset_not_confirmed`: confirm before planning/training.
