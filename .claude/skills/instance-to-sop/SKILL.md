---
name: instance-to-sop
description: Promote a specified, successfully reproduced Training Instance to an approved SOP Version and Formal Model. Use when a Training Instance should become the team's standard operating procedure, through independent reproduction and human approval.
---

# Instance to SOP

Use when a Training Instance is designated as the source of a formal SOP and has passed independent reproduction.

## Boundary
SOP only ever comes from one designated, successfully reproduced Training Instance. Approval is human-only. A broken lineage (`lineage_broken`) blocks approval. The approved SOP Version and Formal Model are immutable after registration.

## Preconditions
- A designated source Training Instance (run_id + instance_id).
- A confirmed dataset, approved plan, and the instance's reproducible evidence.
- An independent reproduction that passed the gate (metric matches to 6 decimals, ROUND_HALF_UP).

## Workflow
1. Create a SOP candidate from the instance (SOP Overview UI or DomainCore):
   ```
   DomainCore.create_sop_candidate(CreateSopCandidateCommand(...))
   ```
2. Reproduce independently:
   ```
   DomainCore.reproduce_sop_candidate(ReproduceSopCandidateCommand(...))
   ```
3. Human review + approve (UI only):
   ```
   DomainCore.review_sop_candidate(ReviewSopCandidateCommand(decision="approve"))
   ```
4. Approval creates the immutable SOP Version + Formal Model.

## Outputs
- `SopCandidateSnapshot` → `SopReproductionGateSnapshot` (passed) → `SopVersionSnapshot` + `FormalModelSnapshot`.

## Failure and next step
- `sop_gate_not_passed` / metric mismatch: the reproduction did not match; fix code/data and re-run.
- `lineage_broken`: restore the missing source/reproduction assets before approving.
- `unauthorized_sop_reviewer`: reconnect as an authorized reviewer.
