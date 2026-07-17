# Issue #7 Experience Extraction, Review, And Reuse Design

**Date:** 2026-07-17
**Status:** Approved product baseline refined for implementation
**Issue:** GitHub #7, Complete the Experience extraction, review, and reuse loop
**Base:** `feat/issue-6-git-sync`

## 1. Scope

Issue #7 adds the governed Experience lifecycle to the authoritative Team
Memory Repository. It covers:

- a durable session evidence boundary;
- deterministic extraction from newly created training evidence at `Stop`;
- an explicit no-op record when no reusable evidence exists;
- immutable Pending, Trusted, Rejected, Conflict, and Superseded history;
- human editing and review through Domain Core and Experience Review UI;
- separate retrieval of Trusted and optional low-confidence Pending guidance;
- applicability reasons and usage writeback into plans and training results;
- a hard domain boundary that prevents Experience actions from changing SOPs.

It does not use Experience to create an SOP, add semantic embeddings as an
authority, summarize full transcripts, extract from ordinary file reads, or
introduce automatic Experience approval.

## 2. Existing Boundaries

The Team Memory Git worktree remains the sole source of truth. The legacy
SQLite and vector-memory prototypes are not authoritative and are not used by
this lifecycle. Experience may cite the same Dataset, Run, Training Instance,
or Raw Record as a future SOP, but no Experience event creates an SOP
derivation or writes under `sops/` or `models/`.

Exploration Plans already separate Trusted, Pending, and excluded Pending IDs.
Issue #7 validates those references against Experience state, records why each
included Experience applies, and propagates actual usage into frozen Run and
Training Instance evidence.

## 3. Approaches Considered

### 3.1 Mutable Experience documents

One JSON document per Experience would be simple to read, but editing or
approval would destroy the candidate wording and review history and produce
same-path Git conflicts. Rejected.

### 3.2 Append-only Experience event families

Each Experience has an immutable event chain. Extraction appends the first
Pending event; review appends Trusted, Rejected, Conflict, or Superseded
events. The current projection is derived by following the single chain head.
Selected because it preserves audit history and works with the repository's
append-first Git model.

### 3.3 Vector memory as the primary store

Semantic search could rank broad text similarity, but a vector store is
rebuildable infrastructure and cannot enforce evidence, lifecycle, review, or
Git lineage. Rejected as an authority. A later optional index may accelerate
the same deterministic repository query without changing results.

## 4. Authoritative Structure

```text
raw-records/
  sessions/<session-id>/start.json
  sessions/<session-id>/stop.json
  runs/<run-id>/<event-id>.json
experiences/
  <experience-id>/<event-id>.json
```

The session start record captures the IDs of existing Run events and Training
Instances after successful startup synchronization. Repeated
`SessionStart` calls for the same Claude Code session reuse the first marker
and never move the boundary forward. The stop record records examined new
evidence, created candidate IDs, and `outcome: created|no_op`.

Experience files contain:

- stable Experience ID and unique event ID;
- state and previous event ID;
- conclusion, applicability, recommended action, failure boundary, and risk;
- numeric confidence from 0 through 1;
- Dataset, Run, Training Instance, and Raw Record evidence references;
- extraction session and source kind;
- reviewer, review time, decision, original and revised content;
- optional conflicting or replacement Experience relation.

Every referenced path must resolve inside Team Memory, identify the expected
asset, and retain its recorded SHA-256. Invalid or missing evidence fails
closed.

## 5. Session Evidence Boundary

`SessionStart` first performs Issue #6 synchronization. On a successful sync,
Domain Core creates or loads the session start record. This ordering prevents
the local marker from blocking a safe remote fast-forward.

`Stop` requires the marker and computes set differences against its captured
Run event and Training Instance IDs. It never selects evidence merely because
of file modification time, so clock skew, resumed sessions, and remote history
cannot leak older facts into the current extraction.

Only critical governed facts are examined. Full dialogue, full command output,
ordinary reads, and arbitrary files are outside the extractor input.

## 6. Extraction Rules

The MVP extractor is deterministic and conservative:

1. A completed child Training Instance whose primary metric is greater than
   its parent produces one improvement candidate describing the measured
   delta and optimization direction.
2. A failed child Training Instance with a bounded error code and summary
   produces one failure-boundary candidate.
3. Baselines without a comparison, duplicate evidence, stopped or timed-out
   attempts, empty directions, and unsupported facts create no candidate.
4. Candidate confidence remains below the Trusted threshold and is always
   presented as Pending/low confidence.

Candidate identity is deterministic from the extraction session and evidence,
making repeated `Stop` calls idempotent. No qualifying fact writes a stop
record with `outcome: no_op`; it does not create an empty Experience.

## 7. Lifecycle

Allowed transitions are:

```text
Pending -> Trusted | Rejected | Conflict
Conflict -> Trusted | Rejected
Trusted -> Superseded
Rejected -> terminal
Superseded -> terminal
```

Approval or rejection may revise the descriptive fields, but the original
Pending event remains unchanged. Conflict requires another existing
Experience. Supersession requires a distinct current Trusted replacement; the
superseded event records that ID. Every review event records actor, time,
decision, prior event, and revised content.

Concurrent heads fail as `experience_conflict`; they are not selected by
timestamp or filename. Review authorization uses the connected Team Memory
actor identity and leaves authorization policy enforcement to the configured
team repository boundary for v0.4.

## 8. Retrieval And Usage

Domain Core exposes deterministic lexical retrieval with optional Dataset
filtering. Results are partitioned into:

- Trusted guidance;
- Pending low-confidence suggestions, only when explicitly requested.

Rejected, Conflict, and Superseded projections are never returned as active
guidance. Each result includes `why_applicable`, based on matching Dataset,
metric, optimization direction, and query terms, plus direct evidence.

An Exploration Plan must:

- reference existing current Experience projections;
- place Trusted and Pending IDs in the correct confidence group;
- explicitly include or exclude every selected Pending suggestion;
- store a non-empty applicability reason for every included Experience.

Run start records and sealed Training Instance manifests copy the included
Experience IDs, event IDs, states, and applicability reasons from the approved
plan. This is the result-side usage writeback. Excluded Pending IDs remain in
the plan audit but are never copied as used guidance.

## 9. Domain Core And Hooks

Domain Core adds operations to:

- establish a session evidence boundary;
- complete extraction and then invoke existing Stop synchronization;
- list and load Experience projections and history;
- review, reject, mark conflict, and supersede;
- search Trusted and optional Pending guidance.

The `SessionStart` hook passes the Claude Code `session_id`, then reports the
number of Pending items before work starts. The `Stop` hook calls the composite
completion operation so extraction and its no-op audit occur before the
managed-path Git commit and push.

Hook adapters remain bounded and do not parse transcripts, write Experience
JSON, or invoke Git directly.

## 10. Experience Review UI

The existing left navigation remains unchanged. `Experience Review` shows
separate Pending, Trusted, Rejected, Conflict, and Superseded sections. The
selected item displays:

- conclusion and confidence;
- applicability, recommended action, failure boundary, and risk;
- direct Dataset, Run, Training Instance, and Raw Record evidence;
- immutable event and reviewer history;
- conflict or replacement relation.

Pending and Conflict items expose editable fields plus Approve, Reject, and
Mark conflict actions. Trusted items can be superseded by another Trusted
Experience. Actions call Domain Core and rerun the projection; the UI never
writes authoritative files directly.

## 11. SOP Isolation

`ExperienceRepository` is restricted to `experiences/` and session records
under `raw-records/sessions/`. It has no SOP repository dependency. Domain
tests snapshot `sops/` and `models/` before every lifecycle transition and
prove their paths and bytes remain unchanged.

Experience references are rejected as SOP source types by the later SOP
workflow. Issue #7 does not create placeholder SOP APIs or files in
anticipation of Issue #8.

## 12. Error Handling

- Missing session marker: Stop records no Experience and returns an actionable
  `experience_session_not_started` failure without fabricating a boundary.
- Missing or changed evidence: extraction or load fails closed and preserves
  existing assets.
- Duplicate Stop: returns the prior result and creates no new files.
- Invalid transition: no event is written.
- Concurrent event heads: returns Conflict for human reconciliation.
- Invalid confidence or empty reviewed content: no event is written.
- Git outage after extraction: Issue #6 preserves all new local assets as
  Pending Sync.
- UI action failure: shows the bounded Domain Core error and preserves the
  selected projection.

## 13. Testing

Focused tests prove:

1. session markers use ID set differences and are idempotent;
2. only new qualifying improvement or failure evidence creates candidates;
3. empty sessions write no-op records and no Experience;
4. every candidate has all required evidence roles and valid hashes;
5. every legal transition appends history and every illegal transition fails;
6. conflict and supersession relations reference valid Experience heads;
7. Trusted and optional Pending retrieval remain separate and explain
   applicability;
8. plans reject missing, stale, or misclassified Experience references;
9. Run and Training Instance evidence records actual included usage;
10. every Experience operation leaves SOP and Formal Model paths byte-for-byte
    unchanged;
11. SessionStart and Stop hooks delegate through Domain Core;
12. Streamlit Experience Review renders all state partitions and performs
    review actions.

Focused tests are followed by the complete repository suite and desktop/mobile
browser acceptance for the Experience Review module.

## 14. Acceptance Boundary

Issue #7 is complete when a real session can extract or explicitly no-op,
researchers can govern immutable Experience history, later plans can retrieve
and cite appropriate guidance, actual training results retain those citations,
and no Experience path can create or mutate an SOP or Formal Model.
