# Issue #2 Team Memory Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one end-to-end `bootstrap-memory` workflow that creates or opens an authoritative ordinary-Git Team Memory Repository, rebuilds a disposable Local Index, and exposes the same workspace state through the CLI and a six-module local UI shell.

**Architecture:** A new `src/domain` package is the only application boundary used by adapters. `MemoryRepository` owns the structured Git workspace and validation, `LocalIndex` derives query rows from authoritative JSON assets, and `DomainCore` composes both into commands and snapshots. The existing CLI and the new Streamlit shell delegate to `DomainCore`; neither adapter writes repository files directly.

**Tech Stack:** Python 3.11+, standard-library `dataclasses`, `json`, `sqlite3`, `subprocess`, Streamlit, pytest, and ordinary Git.

---

## File Map

- Create `src/domain/models.py`: immutable bootstrap commands, workspace snapshots, capacity/remote state, and actionable issue contracts.
- Create `src/domain/memory_repository.py`: Team Memory manifest, managed directories, Git setup, remote validation, capacity scan, and local connection file.
- Create `src/domain/local_index.py`: disposable SQLite asset catalog rebuilt only from authoritative JSON files.
- Create `src/domain/core.py`: the public `bootstrap_memory`, `open_workspace`, and `rebuild_local_index` seam.
- Create `src/ui/shell.py`: pure six-module navigation and top-context view model.
- Create `src/ui/app.py`: Streamlit adapter that loads a local connection through `DomainCore`.
- Modify `src/agent/main.py`: add the `bootstrap-memory` CLI adapter and actionable JSON output.
- Modify `src/agent/slash_commands.py`: register the workflow action without implementing business rules in the parser.
- Modify `.gitignore`: keep the local workspace connection untracked.
- Create focused unit, contract, and integration tests under `tests/`.

### Task 1: Define the bootstrap domain contract

**Files:**
- Create: `src/domain/__init__.py`
- Create: `src/domain/models.py`
- Test: `tests/unit/test_memory_workspace_models.py`

- [ ] **Step 1: Write failing tests for serializable immutable workspace state**

```python
def test_workspace_snapshot_serializes_nested_statuses():
    snapshot = WorkspaceSnapshot(
        repository_id="tmr-1",
        schema_version=1,
        repository_path="/tmp/team-memory",
        actor_id="alice",
        managed_paths=("datasets", "runs"),
        index_path="/tmp/team-memory/.mlagent-local/index.sqlite3",
        indexed_assets=1,
        git_state="initialized",
        remote=RemoteStatus(state="not_configured", url=None, message="No origin remote configured."),
        capacity=CapacityStatus(state="ok", bytes_used=120, largest_file_bytes=80),
        ready=True,
        issues=(),
    )

    assert snapshot.to_dict()["remote"]["state"] == "not_configured"
    assert snapshot.to_dict()["managed_paths"] == ["datasets", "runs"]
```

- [ ] **Step 2: Run the model test and confirm RED**

Run: `.venv/bin/pytest tests/unit/test_memory_workspace_models.py -q`

Expected: FAIL because `src.domain.models` does not exist.

- [ ] **Step 3: Implement the minimal frozen dataclasses and error contract**

```python
@dataclass(frozen=True)
class WorkspaceIssue:
    code: str
    message: str
    next_action: str


@dataclass(frozen=True)
class BootstrapMemoryCommand:
    repository_path: Path
    actor_id: str
    remote_url: str | None = None
    connection_path: Path | None = None
```

Add `RemoteStatus`, `CapacityStatus`, `WorkspaceSnapshot`, `IndexSummary`, and `WorkspaceError`. Use `dataclasses.asdict` plus explicit tuple-to-list conversion for stable JSON output.

- [ ] **Step 4: Run the model test and confirm GREEN**

Run: `.venv/bin/pytest tests/unit/test_memory_workspace_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the contract**

```bash
git add src/domain tests/unit/test_memory_workspace_models.py
git commit -m "feat(domain): define memory workspace contract"
```

### Task 2: Bootstrap and reopen an authoritative Git workspace

**Files:**
- Create: `src/domain/memory_repository.py`
- Test: `tests/integration/test_memory_repository_bootstrap.py`

- [ ] **Step 1: Write the failing create/reopen integration test**

```python
def test_bootstrap_creates_and_reopens_authoritative_git_workspace(tmp_path):
    repository_path = tmp_path / "team-memory"
    manager = MemoryRepository(id_factory=lambda: "tmr-1", clock=lambda: "2026-07-14T00:00:00Z")

    created = manager.bootstrap(repository_path, actor_id="alice")
    reopened = manager.open(repository_path, actor_id="bob")

    assert created.repository_id == "tmr-1"
    assert reopened.repository_id == "tmr-1"
    assert (repository_path / ".git").is_dir()
    assert json.loads((repository_path / ".mlagent/repository.json").read_text())["schema_version"] == 1
    assert set(created.managed_paths) >= {"datasets", "raw-records", "experiences", "sops", "runs", "models"}
```

- [ ] **Step 2: Run the bootstrap test and confirm RED**

Run: `.venv/bin/pytest tests/integration/test_memory_repository_bootstrap.py::test_bootstrap_creates_and_reopens_authoritative_git_workspace -q`

Expected: FAIL because `MemoryRepository` does not exist.

- [ ] **Step 3: Implement safe initialization and validation**

Use schema version `1`, a manifest at `.mlagent/repository.json`, and managed roots `datasets`, `raw-records`, `experiences`, `sops`, `runs`, `models`, and `approvals`. Initialize Git only for an empty/unrecognized directory that contains no user files, create the managed directories, and merge these ignore entries without deleting existing rules:

```text
.mlagent-local/
.mlagent-workspace.json
.env
*.pem
*.key
```

Refuse a path that is a file, a non-empty unrecognized directory, malformed manifest JSON, a manifest with missing required fields, or an unsupported schema. Raise `WorkspaceError` with a stable code and a concrete next action.

- [ ] **Step 4: Add and pass tests for reopen idempotence and schema errors**

Run: `.venv/bin/pytest tests/integration/test_memory_repository_bootstrap.py -q`

Expected: PASS for create, reopen without rewriting identity, non-empty directory refusal, malformed manifest, and unsupported schema.

- [ ] **Step 5: Commit repository bootstrap**

```bash
git add src/domain/memory_repository.py tests/integration/test_memory_repository_bootstrap.py
git commit -m "feat(memory): bootstrap authoritative git workspace"
```

### Task 3: Rebuild a disposable Local Index

**Files:**
- Create: `src/domain/local_index.py`
- Test: `tests/integration/test_local_index_rebuild.py`

- [ ] **Step 1: Write the failing rebuild test**

```python
def test_deleted_index_rebuilds_without_changing_authoritative_assets(tmp_path):
    repository_path = bootstrap_repository(tmp_path)
    index = LocalIndex(repository_path)
    first = index.rebuild()
    manifest_before = (repository_path / ".mlagent/repository.json").read_bytes()

    index.path.unlink()
    rebuilt = index.rebuild()

    assert first.asset_count == rebuilt.asset_count == 1
    assert (repository_path / ".mlagent/repository.json").read_bytes() == manifest_before
    assert index.list_assets()[0]["asset_type"] == "team_memory_repository"
```

- [ ] **Step 2: Run the Local Index test and confirm RED**

Run: `.venv/bin/pytest tests/integration/test_local_index_rebuild.py -q`

Expected: FAIL because `LocalIndex` does not exist.

- [ ] **Step 3: Implement full rebuild from managed JSON assets**

Create `.mlagent-local/index.sqlite3` with an `assets` table containing path, SHA-256, asset type, asset ID, version, state, and creation time. Scan only `.mlagent/repository.json` plus JSON files under declared managed roots. Clear or recreate the database before inserting sorted rows. If SQLite reports corruption, remove only the index file and retry once.

- [ ] **Step 4: Pass deletion, corruption, and untracked-index tests**

Run: `.venv/bin/pytest tests/integration/test_local_index_rebuild.py -q`

Expected: PASS and `git status --short` in the temporary Team Memory Repository never lists `.mlagent-local/`.

- [ ] **Step 5: Commit the derived index**

```bash
git add src/domain/local_index.py tests/integration/test_local_index_rebuild.py
git commit -m "feat(memory): rebuild disposable local asset index"
```

### Task 4: Expose bootstrap through the Domain Core and CLI

**Files:**
- Create: `src/domain/core.py`
- Modify: `src/agent/main.py`
- Modify: `src/agent/slash_commands.py`
- Modify: `.gitignore`
- Test: `tests/contract/test_domain_core_workspace.py`
- Test: `tests/integration/test_bootstrap_memory_cli.py`

- [ ] **Step 1: Write failing Domain Core and CLI tests**

```python
def test_domain_core_bootstrap_writes_local_connection_and_builds_index(tmp_path):
    command = BootstrapMemoryCommand(
        repository_path=tmp_path / "team-memory",
        actor_id="alice",
        connection_path=tmp_path / ".mlagent-workspace.json",
    )

    snapshot = DomainCore(id_factory=lambda: "tmr-1", clock=lambda: "2026-07-14T00:00:00Z").bootstrap_memory(command)

    assert snapshot.ready is True
    assert snapshot.indexed_assets == 1
    assert json.loads(command.connection_path.read_text()) == {
        "actor_id": "alice",
        "repository_path": str(command.repository_path.resolve()),
    }
```

The CLI test must call `main(["bootstrap-memory", ...])`, assert exit `0`, parse stdout JSON, and then open the same connection through `DomainCore`.

- [ ] **Step 2: Run the contract and CLI tests and confirm RED**

Run: `.venv/bin/pytest tests/contract/test_domain_core_workspace.py tests/integration/test_bootstrap_memory_cli.py -q`

Expected: FAIL because the core and command do not exist.

- [ ] **Step 3: Implement the single public application seam**

`DomainCore.bootstrap_memory` must call `MemoryRepository`, rebuild `LocalIndex`, write a non-authoritative local connection file, and return one `WorkspaceSnapshot`. `open_workspace` and `rebuild_local_index` must use the same repositories. Add `bootstrap-memory` to the existing CLI and slash-command registry; adapters may serialize results but must not write repository files.

- [ ] **Step 4: Pass the adapter tests**

Run: `.venv/bin/pytest tests/contract/test_domain_core_workspace.py tests/integration/test_bootstrap_memory_cli.py tests/contract/test_slash_commands.py -q`

Expected: PASS, including non-zero actionable JSON for invalid repository and schema errors.

- [ ] **Step 5: Commit Domain Core and CLI wiring**

```bash
git add .gitignore src/domain/core.py src/agent/main.py src/agent/slash_commands.py tests/contract/test_domain_core_workspace.py tests/integration/test_bootstrap_memory_cli.py tests/contract/test_slash_commands.py
git commit -m "feat(cli): add bootstrap-memory domain workflow"
```

### Task 5: Validate remote and capacity readiness

**Files:**
- Modify: `src/domain/memory_repository.py`
- Test: `tests/integration/test_memory_repository_readiness.py`

- [ ] **Step 1: Write failing readiness tests using a local bare remote**

Create a bare remote with `git init --bare`, bootstrap with its local path, and assert `remote.state == "reachable"`. Add tests for an HTTPS remote being rejected as non-SSH, an unreachable SSH remote returning `remote_unreachable`, a single file at the configured limit returning `file_too_large`, and repository use at 80% returning `warning`.

- [ ] **Step 2: Run the readiness tests and confirm RED**

Run: `.venv/bin/pytest tests/integration/test_memory_repository_readiness.py -q`

Expected: FAIL because readiness checks are not implemented.

- [ ] **Step 3: Implement bounded Git and capacity checks**

Use `git remote get-url origin`, `git remote add origin`, and `git ls-remote origin` with a five-second timeout. Permit local filesystem remotes for hermetic tests; require `git@` or `ssh://` for network remotes. Exclude `.git` and `.mlagent-local` from capacity totals. Defaults are 100,000,000 bytes per file, 20,000,000,000 bytes per repository, and warning at 80%.

- [ ] **Step 4: Pass readiness and regression tests**

Run: `.venv/bin/pytest tests/integration/test_memory_repository_readiness.py tests/integration/test_memory_repository_bootstrap.py -q`

Expected: PASS with stable issue codes and next actions.

- [ ] **Step 5: Commit readiness validation**

```bash
git add src/domain/memory_repository.py tests/integration/test_memory_repository_readiness.py
git commit -m "feat(memory): report remote and capacity readiness"
```

### Task 6: Render the six-module UI shell from Domain Core state

**Files:**
- Create: `src/ui/__init__.py`
- Create: `src/ui/shell.py`
- Create: `src/ui/app.py`
- Test: `tests/contract/test_ui_shell.py`
- Test: `tests/integration/test_streamlit_workspace_shell.py`

- [ ] **Step 1: Write failing shell contract tests**

```python
def test_shell_has_exactly_six_primary_modules_and_context_fields():
    shell = build_shell_state(workspace_snapshot())

    assert shell.navigation == (
        "Code Review",
        "Dataset Overview",
        "Run Status",
        "SOP Overview",
        "Experience Review",
        "Lineage Trace",
    )
    assert tuple(shell.context) == ("workspace", "dataset", "run", "git", "writer")
```

The Streamlit smoke test bootstraps a temporary repository, points `MLAGENT_WORKSPACE_CONFIG` at its connection file, runs `streamlit.testing.v1.AppTest`, and verifies the six sidebar options plus the workspace/Git top context.

- [ ] **Step 2: Run the UI tests and confirm RED**

Run: `.venv/bin/pytest tests/contract/test_ui_shell.py tests/integration/test_streamlit_workspace_shell.py -q`

Expected: FAIL because the UI shell does not exist.

- [ ] **Step 3: Implement the pure shell state and thin Streamlit adapter**

Use a fixed sidebar `radio` for the six modules and a compact top context row for workspace, dataset, run, Git, and writer. Use the approved status vocabulary: Not started, Pending confirmation, Running, Success, Failed, Pending review, Approved, Rejected, Pending sync, and Conflict. Module bodies show only current state relevant to the selected module; do not create a landing page or direct file adapter.

- [ ] **Step 4: Pass UI tests and manually inspect the shell**

Run: `.venv/bin/pytest tests/contract/test_ui_shell.py tests/integration/test_streamlit_workspace_shell.py -q`

Then run: `.venv/bin/streamlit run src/ui/app.py --server.headless true --server.port 8501`

Expected: the first viewport shows fixed navigation and the top context without overlapping text at desktop and mobile widths.

- [ ] **Step 5: Commit the UI shell**

```bash
git add src/ui tests/contract/test_ui_shell.py tests/integration/test_streamlit_workspace_shell.py
git commit -m "feat(ui): add six-module memory workspace shell"
```

### Task 7: Verify, review, and publish issue #2

**Files:**
- Modify only files required by review findings.

- [ ] **Step 1: Run focused checks**

Run: `.venv/bin/pytest tests/unit/test_memory_workspace_models.py tests/contract/test_domain_core_workspace.py tests/contract/test_ui_shell.py tests/integration/test_memory_repository_bootstrap.py tests/integration/test_memory_repository_readiness.py tests/integration/test_local_index_rebuild.py tests/integration/test_bootstrap_memory_cli.py tests/integration/test_streamlit_workspace_shell.py -q`

Expected: PASS.

- [ ] **Step 2: Run the full suite**

Run: `.venv/bin/pytest -q`

Expected: all existing and new tests pass.

- [ ] **Step 3: Run the code-review skill against the branch base**

Review the diff from `docs/v0.4-matt-workflow` for correctness, ADR conformance, security, tests, and accidental legacy authority. Fix all high- and medium-severity findings and rerun affected tests.

- [ ] **Step 4: Verify repository and branch state**

Run: `git status --short`, `git log --oneline docs/v0.4-matt-workflow..HEAD`, and `git diff --check docs/v0.4-matt-workflow...HEAD`.

Expected: clean worktree, intentional commits only, and no whitespace errors.

- [ ] **Step 5: Push and report the implementation**

Push `feat/issue-2-memory-bootstrap`, post the verification summary to GitHub #2, and move the issue to `ready-for-human` without modifying parent #1.
