# Training Instance To SOP Promotion Design

## 1. Scope

Issue #8 adds the first complete path from one specified successful Training Instance to an approved,
immutable SOP Version and its Formal Model. The path includes source-evidence validation, an independent
reproduction execution, a six-decimal metric gate, authorized human approval, version publication, and
the SOP Overview UI.

This issue does not import Notebooks, retrain an SOP on a different Dataset Version, add graph lineage,
or wire every Skill and Hook. Those remain in Issues #9, #10, #14, and #15.

## 2. Invariants

1. An SOP Candidate has exactly one specified successful Training Instance as its source.
2. Experience, chat text, standalone scripts, and standalone model files are never valid SOP sources.
3. Candidate creation reads and validates existing immutable evidence; it does not reconstruct missing
   facts from filenames or conversation history.
4. The source and reproduction are different Run and Training Instance records.
5. Reproduction uses the same Dataset, code, configuration, environment, split, and random-seed
   fingerprints as the source.
6. The primary metric must match after decimal quantization to six places. Model binary hashes may differ.
7. Candidate creation and failed reproduction never create an SOP Version or Formal Model.
8. Only a repository-configured authorized reviewer can approve a gate-passed candidate.
9. Approved SOP Versions and Formal Models are append-only and cannot be edited in place.
10. A Formal Model defaults to the retained model produced by the independent reproduction.

## 3. Architecture

Use a dedicated `SopRepository` as the authority for SOP Candidate, reproduction gate, approval, SOP
Version, reviewer policy, and Formal Model records. `DomainCore` coordinates it with the existing
`DatasetRepository`, `RunRepository`, and training executor. This keeps SOP governance separate from
ordinary Run lifecycle logic while reusing the same frozen training package and worker contract.

`SopPromotionCoordinator` performs the independent execution. It opens the source instance, freezes the
same code revision into a new reproduction Run, prepares one new Training Instance with the exact source
input values, executes it through `TrainingExecutor`, seals it through `RunRepository`, and asks
`SopRepository` to record the gate result.

The local UI calls `DomainCore` only. It never writes SOP, approval, or model files directly.

## 4. Authoritative Assets

All paths are inside the existing Team Memory repository.

```text
approvals/
  reviewer-policy.json
  sop-reproductions/<candidate-id>/<gate-id>.json
  sops/<sop-id>/v0001/<approval-id>.json
sops/
  candidates/<candidate-id>/manifest.json
  <sop-id>/v0001/manifest.json
models/
  formal/<model-id>/manifest.json
  formal/<model-id>/model.joblib
runs/
  <reproduction-run-id>/...
raw-records/
  runs/<reproduction-run-id>/...
```

### 4.1 Reviewer Policy

New repositories receive `approvals/reviewer-policy.json` with the repository creator as the first
authorized reviewer. The policy has a schema version, stable reviewer IDs, creation actor/time, and a
content fingerprint. Existing schema-1 repositories without the policy treat `repository.created_by` as
the sole reviewer until the policy is materialized. Issue #8 reads this policy but does not add member
administration UI.

### 4.2 SOP Candidate

The immutable candidate manifest contains:

- stable candidate ID and target SOP family ID;
- the one source Run and Training Instance IDs;
- exact Dataset Version identity and content/version fingerprints;
- source instance manifest, frozen input, environment, split, code revision, metrics, predictions, and
  retained model evidence references with SHA-256 values;
- configuration, environment, split, seed, code, plan, approval, and instance fingerprints;
- primary metric name and source value;
- user-reviewed SOP name, strategy summary, optimization background, ordered steps, and change summary;
- candidate fingerprint, creator, and creation time.

Candidate creation fails with a structured missing-evidence list when the source is non-successful, the
model was not retained, any declared file is absent or changed, or any identity/fingerprint binding is
inconsistent.

### 4.3 Reproduction Gate

One candidate produces one immutable gate record. The record references the separate reproduction Run
and Training Instance, both candidate and reproduction fingerprints, source/reproduction metric values,
their six-decimal representations, and one of these outcomes:

- `passed`: execution completed, all required fingerprints match, and the six-decimal metric matches;
- `execution_failed`: the reproduction instance is terminal but not successful;
- `fingerprint_mismatch`: the reproduction did not use the exact declared inputs;
- `metric_mismatch`: execution succeeded but the six-decimal metric differs.

Failed gates remain evidence and cannot be overwritten or approved. Retrying requires a new candidate,
which avoids changing the meaning of an already-reviewed gate.

### 4.4 SOP Version And Formal Model

Approval publishes the next version under the candidate's SOP family. Version 1 has no predecessor;
later versions record the previous version and fingerprint plus a non-empty change summary. The SOP
manifest preserves the source instance, reproduction instance, approval, Dataset Version, exact method,
environment, performance, and optimization background.

The Formal Model copies `model.joblib` from the gate-passed reproduction instance. Its manifest records
the model hash, SOP Version, source and reproduction instances, Dataset Version, primary performance,
strategy summary, optimization background, and approval. The source instance model stays in its Run and
is not registered again.

Publication runs under one SOP lock. It prevalidates authorization, gate freshness, paths, file hashes,
capacity, and version collisions before writing. Model and SOP files are written first and the immutable
approval event is the publication marker written last. Readers expose only versions with a complete,
matching approval marker. An interrupted retry reuses identical files and completes the marker; it never
overwrites different content.

## 5. Domain API

Add commands and snapshots for these operations:

```text
create_sop_candidate(command) -> SopCandidateSnapshot
reproduce_sop_candidate(command) -> SopReproductionGateSnapshot
review_sop_candidate(command) -> SopReviewOutcome
list_sop_candidates(connection_path) -> tuple[SopCandidateStatus, ...]
list_sop_versions(connection_path, sop_id=None) -> tuple[SopVersionSnapshot, ...]
get_formal_model(connection_path, model_id) -> FormalModelSnapshot
```

Candidate and review commands carry the expected current fingerprints. Approval therefore fails closed if
the candidate, gate, reviewer policy, or evidence changed between display and action.

## 6. Reproduction Flow

1. Load the candidate and revalidate all cited source evidence.
2. Create a distinct reproduction Run using the source Dataset, plan, approval, and code fingerprints.
3. Freeze the source code revision package into that Run without reading mutable project code.
4. Prepare one instance from the source `input.json`, `environment.json`, and `split.csv`; use no cross-Run
   parent relationship.
5. Execute through the existing worker adapter and seal the result with retention reason
   `sop_reproduction` so a successful model is preserved.
6. Verify source and reproduction bindings and compare the primary metric with
   `Decimal(str(value)).quantize(Decimal("0.000001"), ROUND_HALF_UP)`.
7. Write one gate record. Only `passed` enables approval.

## 7. SOP Overview UI

The existing left navigation remains unchanged. `SOP Overview` gains two tabs:

- **Candidates:** select an eligible successful instance, enter SOP identity and reviewable method fields,
  create the candidate, run reproduction, inspect missing evidence or gate failure, and approve/reject when
  allowed.
- **Approved Versions:** select an SOP family/version and inspect source instance, Dataset Version, time,
  primary performance, strategy, optimization background, ordered steps, environment, reproduction gate,
  approval, and Formal Model.

A compact line chart plots version number against the primary metric for one SOP family. Candidate,
failed-gate, approved SOP, and Formal Model states use explicit text labels so formal and non-formal assets
cannot be confused. The UI catches `WorkspaceError` and refreshes from Domain Core after each action.

## 8. Failure Handling

- Missing or changed evidence: no candidate is written.
- Non-successful source or missing retained source model: no candidate is written.
- Reproduction worker failure: seal the failed reproduction instance and write `execution_failed`.
- Fingerprint or metric mismatch: write a failed gate; do not publish formal assets.
- Unauthorized or stale approval: reject before any SOP/model/approval write.
- Capacity or publication collision: leave the last valid authority visible and return an actionable error.
- Repeated commands: return the existing identical candidate, gate, or approved version; reject identity
  reuse with different content.

## 9. Test Strategy

1. Contract tests validate SOP, gate, approval, version, and Formal Model snapshots.
2. Repository integration tests cover complete candidate evidence, missing assets, changed hashes,
   unsuccessful sources, immutable candidates, gate outcomes, unauthorized approval, publication
   idempotency, and immutable version history.
3. Coordinator tests use the real frozen package and a deterministic fake executor to prove distinct
   execution records, exact fingerprint reuse, six-decimal pass/fail behavior, retained reproduction model,
   and failed execution handling.
4. Domain Core tests prove Experience cannot be supplied as an SOP source and formal assets appear only
   after a passed gate plus authorized approval.
5. Streamlit AppTest and real browser checks cover candidate, failed gate, approved version, Formal Model,
   version trend, desktop layout, and 390-pixel mobile layout.

## 10. Acceptance Mapping

- Unique source and full provenance: sections 2, 4.2, and 4.4.
- Evidence completeness: sections 4.2 and 8.
- Independent exact reproduction and six-decimal gate: sections 4.3 and 6.
- Authorized approval and failure isolation: sections 4.1, 4.4, and 8.
- Immutable versions and change background: section 4.4.
- Reproduction Formal Model: section 4.4.
- SOP Overview details and trend: section 7.
- Required success and failure tests: section 9.
