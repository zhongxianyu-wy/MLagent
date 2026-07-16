# Issue #6 Safe Team Memory Git Synchronization Design

**Date:** 2026-07-16
**Status:** Approved product baseline refined for implementation
**Issue:** GitHub #6, Synchronize authoritative memory assets safely through Git
**Base:** `feat/issue-5-training-instance`

## 1. Scope

Issue #6 adds incremental synchronization for the authoritative Team Memory
Repository. It covers:

- `SessionStart` fetch and safe integration;
- `Stop` commit of real managed-path differences and push;
- one rejected-push fetch/integrate/retry cycle;
- conflict and network-failure preservation;
- local synchronization status for Domain Core and the UI;
- pre-commit capacity checks;
- local bare-remote acceptance tests.

It does not add Experience extraction, SOP lifecycle behavior, repository
cloning, Git LFS, force push, automatic conflict resolution, or a second source
of authority.

## 2. Existing Boundaries

The Team Memory Git worktree remains the sole source of truth. Domain services
create or validate authoritative assets under the schema-managed paths:

```text
datasets/
raw-records/
experiences/
sops/
runs/
models/
approvals/
```

The Local Index, synchronization state, locks, credentials, and workspace
connection remain local-only under ignored paths. Synchronization does not
change the immutability rules of Dataset Versions, Training Instances, SOP
Versions, or Formal Models.

## 3. Approaches Considered

### 3.1 Hooks execute Git directly

This is small initially, but it duplicates branch, conflict, capacity, and
error behavior across `SessionStart`, `Stop`, CLI, and UI paths. It also lets
shell adapters bypass Domain Core. Rejected.

### 3.2 Domain Git service using standard Git commands

A dedicated service owns safe Git state transitions and is called only through
Domain Core. It uses ordinary Git object transfer, preserves standard team
history, and is testable against local bare remotes. Selected.

### 3.3 GitPython abstraction

GitPython can simplify some inspection calls, but merge and push failure
semantics still depend on native Git, while adding another dependency and
translation layer. The repository already uses controlled Git subprocesses.
Rejected for v0.4.

## 4. Components

### 4.1 `GitSyncService`

`src/domain/git_sync.py` owns:

- repository-local synchronization locking;
- atomic local sync-state persistence;
- fetch, branch/ref discovery, ahead/behind calculation, and push;
- safe fast-forward and disjoint-change merge;
- managed-path status inspection and staging;
- capacity validation immediately before commit;
- one fetch/integrate/retry after a rejected push;
- actionable conflict and Pending Sync results.

It does not create domain assets or read the Local Index as authority.

### 4.2 Domain Core

Domain Core exposes:

- `sync_session_start(connection_path)`;
- `sync_session_stop(connection_path, session_id)`;
- `get_sync_status(connection_path)`.

`sync_session_start` rebuilds the Local Index after successful integration.
`sync_session_stop` commits only staged managed changes, then pushes. Opening a
workspace reads the local sync projection without performing a hidden fetch.

### 4.3 Claude Code adapters

Project hooks call small Python adapters:

- `SessionStart` validates hook input, invokes `sync_session_start`, and emits
  bounded additional context describing Synced, Pending Sync, or Conflict;
- `Stop` invokes `sync_session_stop` and emits a user-facing status without
  blocking Claude from ending its response.

The adapters do not parse transcripts, stage files, merge branches, or call Git
directly. `Stop` does not create an empty commit. The hook configuration follows
the current Claude Code command-hook contract: JSON input on stdin, exit zero
for normal lifecycle completion, `SessionStart` additional context, and no
matcher for `Stop`.

## 5. Synchronization Projection

`SyncStatusSnapshot` is a derived local projection with:

- `state`: `not_configured`, `synced`, `syncing`, `pending_sync`, or `conflict`;
- current branch, local HEAD, observed remote HEAD;
- ahead and behind commit counts;
- changed managed paths and conflict paths;
- last attempt and last success timestamps;
- latest local sync commit, message, and next action.

The projection is stored atomically at:

```text
.mlagent-local/sync-state.json
```

The file is ignored, rebuildable, and never committed. A missing state is
derived from current local refs and managed changes. A malformed state fails
closed to `pending_sync`; it cannot alter Git or authoritative assets.

## 6. SessionStart Algorithm

The service takes `.mlagent-local/sync.lock`, writes `syncing`, and then:

1. Validate the Team Memory repository and configured `origin`.
2. Run `git fetch --prune origin`; no clone or full worktree replacement occurs.
3. Resolve the current local branch and corresponding upstream or
   `origin/<branch>` ref.
4. If the remote branch is absent, push the local branch and establish upstream.
5. Calculate ahead/behind counts from local HEAD and the fetched remote ref.
6. If equal, report `synced` unless managed worktree differences remain.
7. If local is ahead only, push the existing commits.
8. If local is behind only, fast-forward only when integration is worktree-safe.
9. If histories diverge, compare paths changed from the merge base:
   - any path changed on both sides produces `conflict`;
   - disjoint changes are merged with an ordinary merge commit and pushed.
10. Rebuild the Local Index after successful remote integration.

Uncommitted managed assets are never discarded. When a remote integration
would touch a dirty worktree, the service stops with `pending_sync` and an
actionable message rather than stashing, resetting, or overwriting.

## 7. Stop Algorithm

The service takes the same lock and then:

1. Refresh repository capacity from actual files.
2. Reject any file at or above the configured single-file limit.
3. Reject an at-or-above-limit repository before automatic commit.
4. Stage with explicit pathspecs for `MANAGED_PATHS` only.
5. Inspect the staged diff:
   - no staged changes means no commit;
   - staged changes create one audit-friendly Git commit using the connected
     actor identity and session ID.
6. Push local commits.
7. If push fails, fetch once and retry only after safe fast-forward or disjoint
   integration.
8. If fetch or push remains unavailable, preserve the local commit and report
   `pending_sync`.
9. If the same path changed on both sides, preserve the local commit and report
   `conflict`.

Changes outside managed paths remain unstaged and uncommitted. No flow invokes
`git add .`, `git add -A` without pathspecs, `git reset --hard`, automatic
checkout of conflict winners, or any force-push form.

## 8. Conflict Semantics

For divergent histories, the service finds the merge base and compares changed
paths on each side. Intersection is a conflict even if Git might textually
auto-merge the file, because authoritative same-path changes require human
review.

The conflict result includes sorted repository-relative paths and recommends:

1. inspect both committed versions;
2. resolve through the owning Domain Core workflow;
3. create a new append-only asset or approved version where required;
4. commit normally and retry synchronization.

If an unexpected native merge conflict occurs after a disjoint preflight, the
service aborts that in-progress merge, preserves the pre-merge local commit, and
returns `conflict`.

## 9. Capacity

Existing manifest limits remain authoritative:

- single managed file strictly below 100,000,000 bytes;
- repository strictly below 20,000,000,000 bytes;
- warning at the configured ratio, no later than 80%.

Domain asset writers continue checking projected capacity before publication.
Git synchronization performs a final actual-file scan before staging and
committing so manually introduced oversized files cannot enter shared history.
Capacity warning does not block a below-limit commit, but is shown beside sync
state. Hard-limit violations leave files untouched and return Pending Sync with
the violating paths or limit.

## 10. UI

`WorkspaceSnapshot` includes the sync projection. The top Git metric uses:

- `Synced`;
- `Syncing`;
- `Pending Sync`;
- `Conflict`;
- `Pending confirmation` when no remote is configured.

A two-second Streamlit fragment calls `DomainCore.get_sync_status` and updates
only the Git metric. Capacity warning or blocked state is displayed as metric
detail. The UI never invokes Git or edits `.mlagent-local/sync-state.json`
directly.

## 11. Error Handling

- Remote unavailable: local worktree and commits remain unchanged;
  `pending_sync` is persisted.
- Push rejected: fetch, safe integration, and one retry only.
- Same-path divergence: no merge attempt; `conflict` is persisted.
- Dirty integration target: no stash or overwrite; `pending_sync`.
- Capacity hard limit: no staging or commit; `pending_sync`.
- Lock contention: bounded wait failure reports `sync_busy`; it does not run a
  second synchronization concurrently.
- Git command failure: bounded diagnostics only, no complete logs or
  credentials in authoritative records.

## 12. Testing

Tests use real local repositories and a local bare remote to prove:

1. initial push and upstream establishment;
2. no-change startup and empty Stop create no commit;
3. fetch plus fast-forward transfers only new Git objects;
4. two clients add disjoint managed paths and converge through an ordinary
   merge;
5. two clients change the same path and both local commits remain preserved
   while status becomes Conflict;
6. unavailable remote preserves local assets and becomes Pending Sync;
7. a later SessionStart safely retries the pending push;
8. Stop stages managed paths only;
9. capacity warning and hard guards use manifest limits;
10. command history contains no force push;
11. SessionStart and Stop hooks delegate to Domain Core;
12. the top UI status updates from the local projection.

Focused tests are followed by the complete repository suite.

## 13. Acceptance Boundary

Issue #6 is complete when incremental collaboration and failure recovery are
observable through Domain Core, hooks, and the top UI status. It creates no
Experience, SOP Version, or Formal Model, and it does not change the ordinary
exploration-versus-SOP boundary established in prior issues.
