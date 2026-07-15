# Issue #4 Exploration Planning And Approval Design

> Date: 2026-07-15  
> Status: User approved  
> Base: `feat/issue-3-dataset-intake`  
> Scope: GitHub Issue #4

## 1. Decision

An Exploration Plan is a working record for one exploration workflow. It is not a reusable,
immutable strategy asset and does not have SOP-style `v1`, `v2`, or `v3` versions.

Claude Code expands the user's exploration direction into hypotheses, rounds, round-level changes,
the evaluation method, stop conditions, experience references, and candidate training code. MLagent
does not judge whether the scientific direction is good. The Domain Core checks only the minimum
structure, managed paths, exact Dataset Version binding, and approval integrity required to execute
safely.

Only an SOP created from a successful, independently reproduced, human-approved Training Instance
becomes an immutable, reusable, versioned training strategy.

## 2. Boundaries

### 2.1 Exploration Plan Record

The plan is represented by append-only planning events rather than an immutable plan-version
library. Events capture only facts needed for review and execution:

- plan created or updated;
- user direction and Claude-completed plan content;
- Trusted Experience references;
- Pending Experience references, visibly marked low confidence;
- pending references excluded by the user;
- candidate code paths and content fingerprints;
- approval, invalidation, and blocked-execution decisions.

The current plan is reconstructed from these events. Editing the plan or candidate code appends a
new event and changes its fingerprint. It does not create a reusable plan version.

### 2.2 SOP Strategy

Exploration records cannot be called, exported, or reused as formal SOP strategy versions. A later
SOP workflow may select one successful Training Instance, reproduce it independently, and create an
approved immutable SOP Version. That SOP owns the reusable training method and associated formal
model.

### 2.3 Code Review Scope

Issue #4 provides read-only candidate-code preview before approval. Direct code editing, immutable
Code Revisions, diffs, and the embedded Claude Code CLI remain in Issues #11 and #12.

Candidate code remains in plugin-managed workspace paths. Approval records its file list and a
stable aggregate fingerprint. The training gate recomputes the fingerprint before execution. A code
change after approval invalidates the approval and requires another explicit confirmation.

## 3. Workflow

```text
User direction
  -> Claude Code completes the exploration plan
  -> Claude Code generates candidate training code
  -> Domain Core records the current plan and fingerprints
  -> Run Status shows plan plus read-only code preview
  -> User explicitly approves current content
  -> Domain Core records approval bound to dataset, plan, and code fingerprints
  -> PreToolUse / CLI / UI training gate verifies the same fingerprints
  -> Issue #5 may create a Run and frozen Training Instance
```

MLagent performs no model-quality or scientific-method approval. It does reject malformed records,
unsafe code paths, missing required sections, mismatched Dataset Versions, or stale approvals.

## 4. Plan Content

The current plan record contains:

- `plan_id` and planning-session identity;
- exact Dataset Version ID, integer version, content fingerprint, and version fingerprint;
- user-provided exploration direction;
- baseline hypothesis;
- ordered exploration rounds;
- each round's hypothesis, optimization direction, and intended changes;
- primary evaluation metric and target copied from the confirmed Dataset Version;
- stop conditions and resource limits;
- separately labeled Trusted and Pending Experience references;
- excluded Pending Experience references;
- candidate code file paths and aggregate code fingerprint;
- current plan-content fingerprint;
- creator and timestamps.

The Domain Core requires these fields to be structurally complete but does not rewrite or score the
plan's scientific content.

## 5. Approval Semantics

Approval is an explicit human decision event, not a mutable status field on a formal plan asset. The
approval records:

- actor and timestamp;
- exact Dataset Version fingerprint;
- exact plan-content fingerprint;
- exact candidate-code fingerprint;
- planning event being approved;
- decision `approved`.

Any subsequent plan or code change makes the fingerprints differ and therefore makes the previous
approval unusable for new execution. The old approval remains in history as an audit fact.

An older approved exploration record is not a reusable strategy. It remains evidence only for its
associated Run. Reusing a training method across projects requires an approved SOP Version.

## 6. Training Gate

One Domain Core authorization operation is shared by adapters. It accepts the entry point, Dataset
Version, plan ID, approval event ID, current plan content, and current candidate code. It returns an
approved binding only when:

1. the Dataset Version exists and remains fingerprint-valid;
2. the approval actor and decision are valid;
3. the approved Dataset Version matches the requested Dataset Version;
4. the current plan fingerprint matches the approved fingerprint;
5. the current code fingerprint matches the approved fingerprint;
6. all candidate code paths remain inside managed roots.

CLI, PreToolUse Hook, and UI call this same operation. Adapters do not reimplement approval rules.
Issue #4 stops after authorization; Issue #5 owns real Run and Training Instance execution.

The retained legacy `--manifest-path` prototype route is not a v0.4 authoritative Run path and
cannot write governed Run or Training Instance assets.

## 7. Blocked Attempt Record

A rejected formal-training request appends one concise audit event containing:

- event ID, timestamp, and actor;
- adapter entry point;
- Dataset Version reference;
- plan and approval references when supplied;
- stable reason code;
- next action.

It excludes prompts, full command output, stack traces, and unrelated session history. A blocked
attempt never creates a Run, Training Instance, metric, prediction, or model record.

## 8. Run Status UI

Before a Run exists, Run Status shows the planning state:

- user direction and current approval state;
- Dataset Version and evaluation metric;
- expected round count;
- baseline and round-level optimization directions;
- stop conditions and resource limits;
- Trusted and low-confidence Pending Experience references;
- excluded Pending Experience references;
- candidate code file list and read-only code preview;
- approve action and stale-approval warning;
- whether formal training is currently authorized.

The interface uses the existing quiet six-module workspace shell. It does not add a landing page,
direct file editing, or a second approval system.

## 9. Error Handling

- Missing confirmed Dataset Version: reject planning and point to Dataset Overview.
- Missing required plan section: keep the plan unapproved and identify the missing field.
- Unsafe or missing code path: reject recording or authorization without reading outside managed
  roots.
- Changed plan or code after approval: report `approval_stale` and require reapproval.
- Missing approval: report `plan_approval_required`.
- Dataset mismatch: report `approved_dataset_mismatch`.
- Audit write failure: preserve the last valid state and reject formal execution.

## 10. Testing

Tests exercise public behavior through Domain Core and adapters:

1. A confirmed Dataset Version can create a structurally complete planning record.
2. Trusted and Pending Experience references remain separated; excluded pending references remain
   visible.
3. Plan updates are normal planning events, not SOP-style immutable versions.
4. Approval binds Dataset, plan, and code fingerprints.
5. Plan or code changes after approval invalidate authorization.
6. CLI, Hook, and UI cannot authorize formal training without approval.
7. Approved bindings reach an injected Issue #5 execution seam without starting mock training.
8. Blocked requests create minimal audit events and no Run or Training Instance.
9. Run Status renders plan details, confidence labels, code preview, and approval readiness on desktop
   and mobile layouts.
10. Existing Issue #2 and #3 tests remain green.

## 11. Non-Goals

- Scientific validation or automatic rejection of Claude's exploration direction.
- Real model training or Training Instance sealing, owned by Issue #5.
- Experience approval or extraction, owned by Issue #7.
- SOP creation, reproduction, approval, or versioning, owned by Issues #8 through #10.
- Direct code editing and Code Revision management, owned by Issue #11.
- Embedded Claude Code CLI control, owned by Issue #12.
