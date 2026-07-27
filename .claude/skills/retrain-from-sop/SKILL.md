---
name: retrain-from-sop
description: Retrain an approved SOP Version on new data without mutating the frozen SOP or Formal Model. Use when new labeled data arrives and a researcher wants to test whether the SOP recipe still performs, producing only a new Run and candidate model.
---

# Retrain from SOP

Use when an approved SOP Version exists and new (compatible) data should be tested against the same recipe.

## Boundary
Retrain NEVER creates, mutates, or approves a SOP Version and NEVER overwrites the Formal Model. It only produces a new Run + candidate Training Instance. Results are always a candidate branch, not a new formal lineage.

## Preconditions
- An approved SOP Version (sop_id + version).
- A confirmed Dataset Version compatible with the SOP (same primary metric + task type).
- The SOP's frozen code is readable.

## Workflow
1. (Optional) check compatibility via the SOP Overview / DomainCore.
2. Trigger retrain through the SOP Overview UI (Retrain on new data) or DomainCore:
   ```
   DomainCore.retrain_from_sop(RetrainFromSopCommand(...))
   ```
3. Review the new Run + candidate metric in Run Status / Lineage Trace.
4. If the candidate is good, promote it via the normal instance-to-sop path (separate human approval).

## Outputs
- A new Run + sealed Training Instance + candidate model.
- `RetrainFromSopResult` with `sop_version_unchanged=True` and `formal_model_unchanged=True`.

## Failure and next step
- `sop_version_not_found`: confirm the sop_id/version in SOP Overview.
- `sop_retrain_incompatible`: the new dataset's metric/task/features do not match the SOP; reconcile the dataset.
- executor failure surfaces as Run state `failed`/`interrupted`; recover via Run Status.
