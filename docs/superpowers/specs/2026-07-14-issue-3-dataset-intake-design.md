# Issue #3 Dataset Intake Design

> Date: 2026-07-14
> Status: Approved by the existing v0.4 PRD, Spec, and ticket workflow
> Base: `feat/issue-2-memory-bootstrap`

## Goal

Deliver one Domain Core workflow that inspects an explicit feature CSV and label
CSV, exposes uncertain semantics as Pending confirmation, and creates an
immutable Dataset Version only after the researcher confirms the classification
task and evaluation protocol. The same confirmed asset drives the CLI and the
Dataset Overview module.

## Chosen Approach

Build a new v0.4 domain slice beside the legacy `DatasetService` instead of
promoting the prototype or replacing it in place.

- Reusing the prototype would preserve its binary-only assumptions, in-memory
  clarification state, and non-authoritative `experiments/standardized` writes.
- Rewriting the legacy service would broaden the regression surface for old
  commands that are not authoritative in v0.4.
- A Domain Core slice keeps one source of truth, leaves compatibility adapters
  working, and lets later plan/training tickets depend on a stable Dataset
  Version contract.

## Domain Contract

`DomainCore.inspect_dataset` is read-only. It accepts explicit feature and label
paths plus optional column hints and returns:

- inferred sample and label columns;
- Pending confirmation fields;
- sample and feature counts, data types, missing rates, class distribution;
- bounded head-and-tail preview with an omission count;
- structural warnings and blockers.

`DomainCore.confirm_dataset` requires explicit values for sample ID, label,
task type, primary metric, split, target performance, and binary positive class
when applicable. It accepts only binary and multiclass classification.

`DomainCore.get_dataset_overview` reloads a confirmed version from Team Memory,
validates its fingerprints, and returns the same bounded overview contract used
by the UI.

## Authoritative Asset

Each family lives under:

```text
datasets/<dataset_id>/v0001/
  manifest.json
  features.csv
  labels.csv
  split.csv
```

The manifest is a Local Index-compatible `dataset_version` asset. It records a
stable dataset ID, monotonically increasing version, content and version
fingerprints, source filenames and hashes, actor/time, task semantics, metric,
target, split policy, schema summary, missingness, distribution, and relative
file references.

Feature and label content is normalized deterministically before hashing and
writing. A change to standardized content, labels, split, or confirmed semantics
creates the next version. Repeating an identical confirmation is idempotent.
Existing version directories are never overwritten.

Absolute local source paths are not copied into Team Memory. The manifest keeps
source filenames and SHA-256 hashes, which preserve origin evidence without
publishing machine-specific paths.

## Validation

- CSV is the v0.4 intake format for this ticket.
- Sample IDs and labels must be present, non-empty, and unique.
- Feature and label sample sets must match exactly; label order is normalized to
  feature order.
- Binary requires exactly two classes and an explicit positive class.
- Multiclass requires at least three classes and has no positive-class field.
- Metrics are constrained by task type.
- Stratified random split requires a valid test ratio and enough samples in
  every class; train-only remains available.
- Target performance is in `[0, 1]`.
- Every generated file must remain below the repository file ceiling, and the
  projected repository size must remain below its configured hard limit.
- Dataset IDs are validated before being used as paths.

Validation failures use stable `WorkspaceError` codes and actionable next
steps. Inspection may return unresolved fields, but confirmation never writes a
partial version. Version files are assembled in a temporary sibling directory
and atomically renamed into place.

## Adapters

Add `intake-data` without removing legacy `intake`:

- without `--confirm`, it prints a Pending confirmation inspection;
- with `--confirm` and complete semantics, it creates or reuses a Dataset
  Version and prints its snapshot;
- invalid input prints actionable JSON and exits non-zero.

The Dataset Overview module loads the latest confirmed Dataset Version and
renders compact structure metrics, task/evaluation facts, class distribution,
warnings, field types/missingness, and a Pandas-style bounded preview. With no
confirmed version it remains explicitly Not started.

## Testing

Tests use the Domain Core against temporary Team Memory repositories and real
CSV files. Coverage includes binary and multiclass confirmation, pending
semantics, mismatched samples, duplicate IDs, missing labels, unsupported task,
immutable version increments, idempotence, fingerprint tampering, capacity
guards, CLI pending/confirmed/error output, Local Index compatibility, bounded
preview, Dataset Overview rendering, and a non-flaky local first-view budget.

The full existing suite remains the completion gate. Issue #3 is reviewed as a
stacked diff against `feat/issue-2-memory-bootstrap`.
