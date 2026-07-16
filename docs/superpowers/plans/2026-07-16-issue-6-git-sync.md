# Safe Team Memory Git Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add incremental, conflict-safe Team Memory Git synchronization through Domain Core, Claude Code SessionStart/Stop hooks, and the live UI status bar.

**Architecture:** A new `GitSyncService` owns all native Git state transitions and persists only a rebuildable local projection under `.mlagent-local`. Domain Core remains the application boundary, Hook adapters remain thin, and the UI polls only Domain Core. Real local bare repositories prove ordinary Git fetch, fast-forward, merge, commit, push, conflict, and retry semantics.

**Tech Stack:** Python 3.11+, native Git subprocesses, `fcntl` locks, atomic JSON files, pytest, Streamlit AppTest, local bare Git remotes.

---

## File Map

- `src/domain/models.py`: immutable synchronization commands and projections.
- `src/domain/git_sync.py`: safe Git synchronization service.
- `src/domain/memory_repository.py`: public capacity refresh used by pre-commit guards.
- `src/domain/core.py`: workspace synchronization application boundary.
- `src/agent/session_start.py`: Claude Code SessionStart adapter.
- `src/agent/session_stop.py`: Claude Code Stop adapter.
- `.claude/hooks/mlagent-session-start.sh`: fail-visible SessionStart wrapper.
- `.claude/hooks/mlagent-session-stop.sh`: non-destructive Stop wrapper.
- `.claude/settings.json`: register the two lifecycle hooks.
- `src/ui/shell.py`: map synchronization projection to the approved UI vocabulary.
- `src/ui/app.py`: two-second top Git metric fragment.
- `tests/unit/test_git_sync_models.py`: model invariants.
- `tests/integration/test_git_sync_service.py`: real bare-remote synchronization behavior.
- `tests/integration/test_domain_core_git_sync.py`: Domain Core and Local Index behavior.
- `tests/integration/test_git_sync_hooks.py`: hook contracts and settings.
- `tests/contract/test_ui_shell.py`: status vocabulary and capacity-detail mapping.
- `tests/integration/test_streamlit_workspace_shell.py`: live Git metric rendering.

### Task 1: Define Synchronization Domain Contracts

**Files:**
- Modify: `src/domain/models.py`
- Create: `tests/unit/test_git_sync_models.py`
- Modify: `tests/unit/test_memory_workspace_models.py`
- Modify: `tests/contract/test_ui_shell.py`

- [ ] **Step 1: Write failing synchronization model tests**

```python
from pathlib import Path

import pytest

from src.domain.models import (
    SessionStopSyncCommand,
    SyncStatusSnapshot,
)


def test_sync_status_accepts_conflict_only_with_paths_and_action():
    status = SyncStatusSnapshot(
        state="conflict",
        branch="main",
        local_head="local-sha",
        remote_head="remote-sha",
        ahead_count=1,
        behind_count=1,
        changed_managed_paths=(),
        conflict_paths=("datasets/ds-1/v0001/manifest.json",),
        last_attempt_at="2026-07-16T00:00:00Z",
        last_success_at=None,
        sync_commit=None,
        message="Same authoritative path changed on both sides.",
        next_action="Review both committed versions.",
    )

    assert status.state == "conflict"
    assert status.conflict_paths == (
        "datasets/ds-1/v0001/manifest.json",
    )


def test_sync_status_rejects_conflict_without_conflict_paths():
    with pytest.raises(ValueError, match="conflict_paths"):
        SyncStatusSnapshot(
            state="conflict",
            branch="main",
            local_head="local-sha",
            remote_head="remote-sha",
            ahead_count=1,
            behind_count=1,
            changed_managed_paths=(),
            conflict_paths=(),
            last_attempt_at="2026-07-16T00:00:00Z",
            last_success_at=None,
            sync_commit=None,
            message="Conflict",
            next_action="Review",
        )


def test_session_stop_command_requires_nonempty_session_identity():
    with pytest.raises(ValueError, match="session_id"):
        SessionStopSyncCommand(
            connection_path=Path(".mlagent-workspace.json"),
            session_id="",
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/test_git_sync_models.py -q
```

Expected: collection fails because the synchronization models do not exist.

- [ ] **Step 3: Add immutable commands and projection**

Add to `src/domain/models.py`:

```python
@dataclass(frozen=True)
class SessionStopSyncCommand:
    connection_path: Path
    session_id: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.session_id, "session_id")


@dataclass(frozen=True)
class SyncStatusSnapshot:
    state: str
    branch: str | None
    local_head: str | None
    remote_head: str | None
    ahead_count: int
    behind_count: int
    changed_managed_paths: tuple[str, ...]
    conflict_paths: tuple[str, ...]
    last_attempt_at: str | None
    last_success_at: str | None
    sync_commit: str | None
    message: str
    next_action: str | None

    def __post_init__(self) -> None:
        _validate_state(self.state, _SYNC_STATES, "state")
        _validate_non_negative(self.ahead_count, "ahead_count")
        _validate_non_negative(self.behind_count, "behind_count")
        _validate_non_empty(self.message, "message")
        if self.state == "conflict":
            if not self.conflict_paths:
                raise ValueError("conflict requires conflict_paths")
            _validate_non_empty(self.next_action, "next_action")
        elif self.conflict_paths:
            raise ValueError("conflict_paths require conflict state")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


_SYNC_STATES = frozenset(
    {
        "not_configured",
        "synced",
        "syncing",
        "pending_sync",
        "conflict",
    }
)
```

Add `sync: SyncStatusSnapshot` to `WorkspaceSnapshot` and update existing
workspace fixtures with a `not_configured` or `synced` projection.

- [ ] **Step 4: Run focused model tests**

Run:

```bash
.venv/bin/pytest \
  tests/unit/test_git_sync_models.py \
  tests/unit/test_memory_workspace_models.py \
  tests/contract/test_ui_shell.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_git_sync_models.py \
  tests/unit/test_memory_workspace_models.py tests/contract/test_ui_shell.py
git commit -m "feat(domain): define git sync contracts"
```

### Task 2: Persist Local Sync State And Inspect Repository Differences

**Files:**
- Create: `src/domain/git_sync.py`
- Create: `tests/integration/test_git_sync_service.py`

- [ ] **Step 1: Write failing state and difference tests**

Create helpers that initialize a Team Memory repository, push it to a local
bare remote, and clone it for a second actor. Then add:

```python
def test_missing_local_state_is_derived_without_network(sync_workspace):
    service = sync_workspace.service("alice")

    status = service.status()

    assert status.state == "synced"
    assert status.branch == sync_workspace.branch
    assert status.ahead_count == 0
    assert status.behind_count == 0
    assert status.changed_managed_paths == ()


def test_untracked_managed_asset_is_pending_but_unrelated_file_is_not_staged(
    sync_workspace,
):
    managed = sync_workspace.root / "experiences/candidate-1.json"
    managed.write_text('{"asset_type":"experience_candidate"}\n')
    unrelated = sync_workspace.root / "notes.txt"
    unrelated.write_text("private note\n")

    status = sync_workspace.service("alice").status()

    assert status.state == "pending_sync"
    assert status.changed_managed_paths == (
        "experiences/candidate-1.json",
    )
    assert "notes.txt" not in status.changed_managed_paths
```

Also corrupt `.mlagent-local/sync-state.json` and assert `status()` returns
`pending_sync` with a recovery action instead of raising or mutating Git.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest \
  tests/integration/test_git_sync_service.py \
  -k "missing_local_state or untracked_managed or corrupt" -q
```

Expected: FAIL because `GitSyncService` does not exist.

- [ ] **Step 3: Implement status persistence and Git inspection**

Create `src/domain/git_sync.py` with:

```python
SYNC_STATE_PATH = Path(".mlagent-local/sync-state.json")
SYNC_LOCK_PATH = Path(".mlagent-local/sync.lock")


class GitSyncService:
    def __init__(self, repository_path: Path, actor_id: str, clock=None):
        self.repository_path = repository_path.expanduser().resolve()
        self.actor_id = actor_id
        self.clock = clock or _utc_now

    def status(self) -> SyncStatusSnapshot:
        branch = self._current_branch()
        local_head = self._rev_parse("HEAD")
        remote_ref = self._remote_ref(branch)
        remote_head = self._optional_rev_parse(remote_ref)
        ahead, behind = self._ahead_behind(local_head, remote_head)
        changed = self._managed_changes()
        persisted = self._load_local_state()
        if persisted is not None and persisted.state in {"syncing", "conflict"}:
            return persisted
        state = (
            "not_configured"
            if not self._origin_url()
            else "pending_sync"
            if changed or ahead or behind
            else "synced"
        )
        return SyncStatusSnapshot(
            state=state,
            branch=branch,
            local_head=local_head,
            remote_head=remote_head,
            ahead_count=ahead,
            behind_count=behind,
            changed_managed_paths=changed,
            conflict_paths=(),
            last_attempt_at=None if persisted is None else persisted.last_attempt_at,
            last_success_at=None if persisted is None else persisted.last_success_at,
            sync_commit=None if persisted is None else persisted.sync_commit,
            message=_status_message(state),
            next_action=_status_action(state),
        )
```

Use `git status --porcelain=v1 -z --untracked-files=all -- <managed paths>`
and parse NUL-delimited records. Persist JSON through a temporary file and
`Path.replace()`. Validate every loaded field through `SyncStatusSnapshot`.
Use bounded stderr summaries and reject unsupported commands containing force
options in the central `_git()` method.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_git_sync_service.py \
  -k "missing_local_state or untracked_managed or corrupt" -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/git_sync.py tests/integration/test_git_sync_service.py
git commit -m "feat(memory): project local git sync state"
```

### Task 3: Implement Incremental SessionStart Synchronization

**Files:**
- Modify: `src/domain/git_sync.py`
- Modify: `tests/integration/test_git_sync_service.py`

- [ ] **Step 1: Write failing startup synchronization tests**

Add real bare-remote tests:

```python
def test_session_start_pushes_initial_branch_without_reclone(empty_remote_workspace):
    before_git_dir = inode(empty_remote_workspace.root / ".git")

    status = empty_remote_workspace.service("alice").session_start()

    assert status.state == "synced"
    assert status.ahead_count == 0
    assert remote_head(empty_remote_workspace.remote, status.branch) == status.local_head
    assert inode(empty_remote_workspace.root / ".git") == before_git_dir


def test_session_start_fast_forwards_remote_only_commit(two_clients):
    write_and_commit(
        two_clients.bob,
        "raw-records/bob-event.json",
        '{"asset_type":"run_event"}\n',
    )
    push(two_clients.bob)

    status = two_clients.alice_service.session_start()

    assert status.state == "synced"
    assert (two_clients.alice / "raw-records/bob-event.json").is_file()
    assert git(two_clients.alice, "merge-base", "--is-ancestor",
               status.remote_head, status.local_head).returncode == 0


def test_session_start_merges_disjoint_divergence(two_clients):
    write_and_commit(two_clients.alice, "experiences/alice.json", "{}\n")
    write_and_commit(two_clients.bob, "raw-records/bob.json", "{}\n")
    push(two_clients.bob)

    status = two_clients.alice_service.session_start()

    assert status.state == "synced"
    assert (two_clients.alice / "experiences/alice.json").is_file()
    assert (two_clients.alice / "raw-records/bob.json").is_file()
    assert parent_count(two_clients.alice, "HEAD") == 2
```

Add a no-change test proving HEAD and object count remain unchanged except for
ordinary fetch bookkeeping.

- [ ] **Step 2: Run startup tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_git_sync_service.py \
  -k "session_start" -q
```

Expected: FAIL because `session_start()` does not exist.

- [ ] **Step 3: Implement fetch, fast-forward, merge, and push**

Add:

```python
def session_start(self) -> SyncStatusSnapshot:
    with self._sync_lock():
        self._persist(self._syncing_status())
        if self._origin_url() is None:
            return self._finish_not_configured()
        if not self._fetch():
            return self._finish_pending("fetch_failed")
        return self._integrate_and_push(allow_commit=False)
```

`_integrate_and_push()` must:

- establish upstream with `git push --set-upstream origin HEAD:<branch>` when
  the fetched remote branch does not exist;
- use `git rev-list --left-right --count HEAD...<remote-ref>`;
- push on ahead-only;
- run `git merge --ff-only <remote-ref>` on behind-only when no worktree
  changes exist;
- for divergence, compute the merge base and both changed-path sets with
  `git diff --name-only -z <base>..<ref>`;
- return Conflict before merge when path sets intersect;
- run an ordinary `git -c user.name=... -c user.email=... merge --no-edit
  <remote-ref>` only for disjoint changes;
- abort an unexpected merge conflict and persist Conflict;
- never use pull, reset, checkout of conflict winners, or force push.

- [ ] **Step 4: Run startup tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_git_sync_service.py \
  -k "session_start" -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/git_sync.py tests/integration/test_git_sync_service.py
git commit -m "feat(memory): synchronize session startup"
```

### Task 4: Commit Managed Differences And Recover Rejected Pushes

**Files:**
- Modify: `src/domain/git_sync.py`
- Modify: `src/domain/memory_repository.py`
- Modify: `tests/integration/test_git_sync_service.py`
- Modify: `tests/integration/test_memory_repository_readiness.py`

- [ ] **Step 1: Write failing Stop, conflict, network, and capacity tests**

Add:

```python
def test_session_stop_commits_only_managed_differences(two_clients):
    managed = two_clients.alice / "experiences/candidate.json"
    managed.write_text("{}\n")
    unrelated = two_clients.alice / "notes.txt"
    unrelated.write_text("local only\n")

    status = two_clients.alice_service.session_stop("session-1")

    assert status.state == "synced"
    assert "experiences/candidate.json" in show_names(two_clients.alice, "HEAD")
    assert "notes.txt" not in show_names(two_clients.alice, "HEAD")
    assert unrelated.is_file()


def test_empty_session_stop_does_not_create_commit(two_clients):
    before = rev_parse(two_clients.alice, "HEAD")

    status = two_clients.alice_service.session_stop("session-empty")

    assert status.state == "synced"
    assert rev_parse(two_clients.alice, "HEAD") == before


def test_rejected_push_fetches_merges_disjoint_and_retries_once(two_clients):
    (two_clients.alice / "experiences/alice.json").write_text("{}\n")
    write_and_commit(two_clients.bob, "raw-records/bob.json", "{}\n")
    push(two_clients.bob)

    status = two_clients.alice_service.session_stop("session-retry")

    assert status.state == "synced"
    assert remote_contains(two_clients.remote, "experiences/alice.json")
    assert remote_contains(two_clients.remote, "raw-records/bob.json")


def test_same_path_divergence_preserves_local_commit_and_reports_conflict(
    two_clients,
):
    path = "experiences/shared.json"
    write_and_commit(two_clients.bob, path, '{"actor":"bob"}\n')
    push(two_clients.bob)
    (two_clients.alice / path).write_text('{"actor":"alice"}\n')

    status = two_clients.alice_service.session_stop("session-conflict")

    assert status.state == "conflict"
    assert status.conflict_paths == (path,)
    assert json.loads((two_clients.alice / path).read_text())["actor"] == "alice"
    assert rev_parse(two_clients.alice, "HEAD") != status.remote_head
```

Add unavailable-remote then retry, warning-capacity commit, exact-limit
rejection, exact-file-limit rejection, and command-recorder assertions that no
invocation contains `--force`, `--force-with-lease`, or a force refspec.

- [ ] **Step 2: Run Stop tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_git_sync_service.py \
  -k "session_stop or rejected_push or divergence or unavailable or capacity or force" -q
```

Expected: FAIL because Stop synchronization is not implemented.

- [ ] **Step 3: Expose actual capacity refresh**

Add to `MemoryRepository`:

```python
def capacity_status(self, repository_path: Path) -> CapacityStatus:
    root = repository_path.expanduser().resolve()
    manifest = self._load_manifest(root / MANIFEST_PATH)
    self._validate_manifest(manifest)
    return self._capacity_status(root, manifest["limits"])
```

Test that it excludes `.git` and `.mlagent-local` exactly like `open()`.

- [ ] **Step 4: Implement managed commit and retry**

Add:

```python
def session_stop(
    self,
    session_id: str,
    capacity: CapacityStatus,
) -> SyncStatusSnapshot:
    with self._sync_lock():
        self._persist(self._syncing_status())
        self._require_commit_capacity(capacity)
        self._stage_managed_paths()
        sync_commit = self._commit_staged(session_id)
        if self._origin_url() is None:
            return self._finish_not_configured(sync_commit=sync_commit)
        if self._push():
            return self._finish_synced(sync_commit=sync_commit)
        if not self._fetch():
            return self._finish_pending(
                "remote_unreachable",
                sync_commit=sync_commit,
            )
        return self._integrate_and_push(
            allow_commit=True,
            sync_commit=sync_commit,
            retry_limit=1,
        )
```

Stage only:

```python
["git", "add", "-A", "--", *MANAGED_PATHS]
```

The explicit pathspec is mandatory. Commit only when
`git diff --cached --quiet` returns 1. Use:

```text
chore(memory): sync managed assets

MLagent-Session: <bounded session id>
```

Persist Pending Sync after network or permission failure. Keep the local commit
and files. Persist Conflict with sorted paths after same-path divergence.

- [ ] **Step 5: Run all Git service tests**

Run:

```bash
.venv/bin/pytest \
  tests/integration/test_git_sync_service.py \
  tests/integration/test_memory_repository_readiness.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/domain/git_sync.py src/domain/memory_repository.py \
  tests/integration/test_git_sync_service.py \
  tests/integration/test_memory_repository_readiness.py
git commit -m "feat(memory): commit and retry managed sync"
```

### Task 5: Route Synchronization Through Domain Core

**Files:**
- Modify: `src/domain/core.py`
- Modify: `src/domain/models.py`
- Create: `tests/integration/test_domain_core_git_sync.py`
- Modify: `tests/contract/test_domain_core_workspace.py`

- [ ] **Step 1: Write failing Domain Core tests**

```python
def test_domain_core_session_start_syncs_then_rebuilds_index(sync_core_workspace):
    write_remote_asset(
        sync_core_workspace,
        "raw-records/remote-event.json",
        '{"asset_type":"run_event","asset_id":"remote-event"}\n',
    )

    status = sync_core_workspace.core.sync_session_start(
        sync_core_workspace.connection_path
    )
    snapshot = sync_core_workspace.core.open_workspace(
        sync_core_workspace.connection_path
    )

    assert status.state == "synced"
    assert snapshot.sync == status
    assert snapshot.indexed_assets >= 1


def test_domain_core_stop_preserves_pending_commit_on_remote_failure(
    sync_core_workspace,
):
    asset = sync_core_workspace.memory_root / "experiences/candidate.json"
    asset.write_text("{}\n")
    sync_core_workspace.disable_remote()

    status = sync_core_workspace.core.sync_session_stop(
        SessionStopSyncCommand(
            connection_path=sync_core_workspace.connection_path,
            session_id="session-1",
        )
    )

    assert status.state == "pending_sync"
    assert status.sync_commit is not None
    assert asset.is_file()
```

Also prove `get_sync_status()` performs no fetch by replacing the remote with an
unreachable URL after a successful sync and asserting the saved projection is
returned quickly.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_domain_core_git_sync.py -q
```

Expected: FAIL because Domain Core has no synchronization methods.

- [ ] **Step 3: Implement Domain Core methods**

Add:

```python
def sync_session_start(self, connection_path: Path) -> SyncStatusSnapshot:
    connection, repository = self._open_connected_repository(connection_path)
    status = GitSyncService(
        repository.repository_path,
        connection.actor_id,
        clock=self.clock,
    ).session_start()
    if status.state == "synced":
        LocalIndex(repository.repository_path).rebuild()
    return status


def sync_session_stop(
    self,
    command: SessionStopSyncCommand,
) -> SyncStatusSnapshot:
    connection, repository = self._open_connected_repository(
        command.connection_path
    )
    capacity = self.memory_repository.capacity_status(
        repository.repository_path
    )
    return GitSyncService(
        repository.repository_path,
        connection.actor_id,
        clock=self.clock,
    ).session_stop(command.session_id, capacity)


def get_sync_status(self, connection_path: Path) -> SyncStatusSnapshot:
    connection = self._load_connection(connection_path)
    return GitSyncService(
        connection.repository_path,
        connection.actor_id,
        clock=self.clock,
    ).status()
```

Refactor connection/repository opening only enough to remove duplication.
Populate `WorkspaceSnapshot.sync` in bootstrap and open paths.

- [ ] **Step 4: Run Domain Core and workspace tests**

Run:

```bash
.venv/bin/pytest \
  tests/integration/test_domain_core_git_sync.py \
  tests/contract/test_domain_core_workspace.py \
  tests/integration/test_memory_repository_bootstrap.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/core.py src/domain/models.py \
  tests/integration/test_domain_core_git_sync.py \
  tests/contract/test_domain_core_workspace.py
git commit -m "feat(domain): expose team memory synchronization"
```

### Task 6: Add Claude Code SessionStart And Stop Hooks

**Files:**
- Create: `src/agent/session_start.py`
- Create: `src/agent/session_stop.py`
- Create: `.claude/hooks/mlagent-session-start.sh`
- Create: `.claude/hooks/mlagent-session-stop.sh`
- Modify: `.claude/settings.json`
- Create: `tests/integration/test_git_sync_hooks.py`

- [ ] **Step 1: Write failing hook adapter tests**

```python
def test_session_start_hook_delegates_and_emits_bounded_context(
    configured_hook_workspace,
):
    result = run_hook(
        ".claude/hooks/mlagent-session-start.sh",
        {
            "session_id": "session-1",
            "cwd": str(configured_hook_workspace.root),
            "hook_event_name": "SessionStart",
            "source": "startup",
            "model": "claude-test",
        },
        configured_hook_workspace.environment,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    output = payload["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    assert "Synced" in output["additionalContext"]


def test_stop_hook_commits_managed_changes_without_blocking_stop(
    configured_hook_workspace,
):
    (configured_hook_workspace.memory / "experiences/candidate.json").write_text(
        "{}\n"
    )

    result = run_hook(
        ".claude/hooks/mlagent-session-stop.sh",
        {
            "session_id": "session-1",
            "cwd": str(configured_hook_workspace.root),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "Done",
            "background_tasks": [],
            "session_crons": [],
        },
        configured_hook_workspace.environment,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout).get("decision") is None
    assert git_head(configured_hook_workspace.memory) != (
        configured_hook_workspace.initial_head
    )
```

Also assert malformed input is fail-visible, hook output contains no remote URL
or credentials, and `.claude/settings.json` registers SessionStart and Stop
using the project wrappers.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_git_sync_hooks.py -q
```

Expected: FAIL because the adapters and wrappers do not exist.

- [ ] **Step 3: Implement adapters and wrappers**

`src/agent/session_start.py`:

```python
def handle(payload: dict[str, object]) -> dict[str, object]:
    if payload.get("hook_event_name") != "SessionStart":
        raise ValueError("hook_event_name must be SessionStart")
    connection = Path(
        os.environ.get("MLAGENT_WORKSPACE_CONFIG", ".mlagent-workspace.json")
    )
    status = DomainCore().sync_session_start(connection)
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": _bounded_sync_context(status),
        }
    }
```

`src/agent/session_stop.py` validates `Stop`, requires `session_id`, invokes
`sync_session_stop`, and returns only a bounded `systemMessage`. It never emits
`decision: "block"`.

Both shell wrappers select `MLAGENT_PYTHON`, project `.venv`, or `python3`, then
run the corresponding module. SessionStart failures are visible on stderr but
cannot overwrite assets. Stop failures leave local assets and return a
non-blocking error.

Register:

```json
"SessionStart": [
  {
    "matcher": "startup|resume|clear|compact",
    "hooks": [
      {
        "type": "command",
        "command": "sh \"$CLAUDE_PROJECT_DIR/.claude/hooks/mlagent-session-start.sh\"",
        "timeout": 60,
        "statusMessage": "Synchronizing MLagent team memory"
      }
    ]
  }
],
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "sh \"$CLAUDE_PROJECT_DIR/.claude/hooks/mlagent-session-stop.sh\"",
        "timeout": 60,
        "statusMessage": "Committing MLagent managed memory"
      }
    ]
  }
]
```

- [ ] **Step 4: Run hook tests**

Run:

```bash
.venv/bin/pytest \
  tests/integration/test_git_sync_hooks.py \
  tests/integration/test_pre_tool_use_training_gate.py -q
```

Expected: PASS, including the existing PreToolUse registration.

- [ ] **Step 5: Commit**

```bash
git add src/agent/session_start.py src/agent/session_stop.py \
  .claude/hooks/mlagent-session-start.sh \
  .claude/hooks/mlagent-session-stop.sh .claude/settings.json \
  tests/integration/test_git_sync_hooks.py
git commit -m "feat(hook): synchronize session memory lifecycle"
```

### Task 7: Render Live Sync And Capacity Status

**Files:**
- Modify: `src/ui/shell.py`
- Modify: `src/ui/app.py`
- Modify: `tests/contract/test_ui_shell.py`
- Modify: `tests/integration/test_streamlit_workspace_shell.py`
- Modify: `tests/contract/test_frontend_streamlit_contracts.py`

- [ ] **Step 1: Write failing UI projection tests**

```python
def test_shell_maps_sync_projection_to_approved_git_status():
    snapshot = replace(
        workspace_snapshot(),
        sync=sync_status("pending_sync"),
    )

    shell = build_shell_state(snapshot)

    assert shell.context["git"] == "Pending Sync"


def test_shell_exposes_capacity_warning_for_top_metric():
    snapshot = replace(
        workspace_snapshot(),
        sync=sync_status("synced"),
        capacity=replace(workspace_snapshot().capacity, state="warning"),
    )

    shell = build_shell_state(snapshot)

    assert shell.git_detail == "Capacity warning"
```

Add a Streamlit test that loads a saved Conflict projection and asserts the
first five metrics contain `("Git", "Conflict")`. Add a source contract for:

```python
@st.fragment(run_every=2.0)
def _render_live_sync_status(...):
```

- [ ] **Step 2: Run UI tests and verify RED**

Run:

```bash
.venv/bin/pytest \
  tests/contract/test_ui_shell.py \
  tests/integration/test_streamlit_workspace_shell.py \
  tests/contract/test_frontend_streamlit_contracts.py -q
```

Expected: FAIL because the shell and app still map only remote reachability.

- [ ] **Step 3: Implement shell mapping and live fragment**

Map:

```python
git_status = {
    "not_configured": "Pending confirmation",
    "synced": "Synced",
    "syncing": "Syncing",
    "pending_sync": "Pending Sync",
    "conflict": "Conflict",
}[snapshot.sync.state]
```

Add `Synced` and `Syncing` to `GLOBAL_STATUS_VOCABULARY`. Add `git_detail` to
`ShellState`, with `Capacity warning` or `Capacity blocked` when applicable.

Refactor top metrics so the Git column calls:

```python
@st.fragment(run_every=2.0)
def _render_live_sync_status(core, connection_path, initial_status, detail):
    try:
        status = core.get_sync_status(connection_path)
        value = _sync_display(status.state)
    except WorkspaceError:
        value = initial_status
    st.metric("Git", value, delta=detail)
```

The fragment must not fetch, push, stage, or read `.mlagent-local` directly.

- [ ] **Step 4: Run UI tests**

Run:

```bash
.venv/bin/pytest \
  tests/contract/test_ui_shell.py \
  tests/integration/test_streamlit_workspace_shell.py \
  tests/contract/test_frontend_streamlit_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui/shell.py src/ui/app.py tests/contract/test_ui_shell.py \
  tests/integration/test_streamlit_workspace_shell.py \
  tests/contract/test_frontend_streamlit_contracts.py
git commit -m "feat(ui): display live memory sync state"
```

### Task 8: Complete Acceptance, Review, And Delivery

**Files:**
- Review all Issue #6 changes
- Update GitHub Issue #6 after successful verification

- [ ] **Step 1: Run focused Issue #6 acceptance**

```bash
.venv/bin/pytest \
  tests/unit/test_git_sync_models.py \
  tests/integration/test_git_sync_service.py \
  tests/integration/test_domain_core_git_sync.py \
  tests/integration/test_git_sync_hooks.py \
  tests/contract/test_ui_shell.py \
  tests/integration/test_streamlit_workspace_shell.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full suite**

```bash
.venv/bin/pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run static repository checks**

```bash
git diff --check
uv lock --check
.venv/bin/python -m compileall -q src
rg -n "T[B]D|T[O]DO|git add \\.|reset --hard|force-with-lease|--force" \
  src tests .claude docs/superpowers/specs/2026-07-16-issue-6-git-sync-design.md
```

Expected: no placeholders or unsafe synchronization commands.

- [ ] **Step 4: Inspect real authoritative boundaries**

Use a real bare-remote fixture and verify:

```bash
git -C <client> status --short
git -C <client> show --name-only --format= HEAD
find <client>/.mlagent-local -maxdepth 2 -type f -print
git -C <client> ls-files .mlagent-local .env '*.pem' '*.key'
```

Expected:

- managed assets and ordinary commits synchronize;
- `.mlagent-local` state exists but is untracked;
- unrelated files and credentials remain untracked;
- local commits survive Pending Sync and Conflict;
- no SOP Version or Formal Model is created by synchronization.

- [ ] **Step 5: Browser acceptance**

Start Streamlit on an unused local port with a fixture workspace. Verify desktop
and 390x844 mobile viewports:

- Git metric renders Synced, Pending Sync, and Conflict projections;
- capacity warning is visible;
- no horizontal overflow or metric overlap;
- the existing six navigation modules and Run Status remain intact.

- [ ] **Step 6: Review the cumulative diff**

Review from `3bbad38` for:

- destructive Git commands;
- force push;
- staging outside `MANAGED_PATHS`;
- conflict paths being overwritten;
- local sync state entering Git;
- stale capacity use before commit;
- Hook adapters bypassing Domain Core;
- UI calling Git directly;
- regression of exploration/SOP boundaries.

- [ ] **Step 7: Push and update Issue #6**

```bash
git push -u origin feat/issue-6-git-sync
```

Replace `ready-for-agent` with `ready-for-human` and comment with branch, head,
focused/full test evidence, bare-remote scenarios, browser evidence, and the
explicit statement that Issue #6 creates no Experience, SOP Version, or Formal
Model.
