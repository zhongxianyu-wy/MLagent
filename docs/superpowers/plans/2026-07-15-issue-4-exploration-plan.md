# Exploration Planning And Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reviewable, append-only exploration planning workflow whose explicit human approval binds one confirmed Dataset Version, the current plan content, and current candidate code before any formal exploration can reach the Issue #5 execution seam.

**Architecture:** Store ordinary planning events under the existing `raw-records` managed path and approval/gate audit events under the existing `approvals` path, so Team Memory schema v1 remains compatible. `ExplorationRepository` owns canonical serialization, fingerprints, safe code reads, and append-only persistence; `DomainCore` owns Dataset Version binding and exposes the single authorization operation used by CLI, Hook, and UI. Exploration records deliberately have no reusable strategy version, and real Run/Training Instance creation remains out of scope.

**Tech Stack:** Python 3.11 dataclasses, SHA-256 canonical JSON fingerprints, atomic filesystem writes, pytest, Streamlit testing, Claude Code project Skills.

---

## File Structure

- Create `src/domain/exploration_repository.py`: authoritative planning, approval, code fingerprint, review-query, and gate-audit persistence.
- Modify `src/domain/models.py`: typed commands and snapshots shared by Domain Core and adapters.
- Modify `src/domain/core.py`: Dataset-bound record, approve, review, and authorize use cases.
- Modify `src/agent/main.py`: `design-and-explore` record/approve commands and approved `explore` gate.
- Modify `src/agent/hooks.py`: PreToolUse adapter that delegates to Domain Core.
- Modify `src/training/runner.py`: executor seam that never invokes a command when Domain Core denies it.
- Modify `src/ui/shell.py`: planning-aware Run Status context.
- Modify `src/ui/app.py`: Run Status plan review, confidence labels, read-only code preview, approval, and authorization check.
- Create `.claude/skills/design-and-explore/SKILL.md`: Claude Code workflow instructions, with human approval as the only promotion gate.
- Create focused contract/integration tests listed below; keep legacy prototype tests intact but do not route authoritative v0.4 behavior through `ConversationService`.

### Task 1: Typed Exploration Contracts

**Files:**
- Modify: `src/domain/models.py`
- Test: `tests/unit/test_exploration_models.py`

- [ ] **Step 1: Write failing tests for JSON-safe typed plan content**

```python
from pathlib import Path

from src.domain.models import (
    CandidateCodeFile,
    ExplorationPlanSnapshot,
    ExplorationRound,
)


def test_exploration_plan_snapshot_has_no_strategy_version_field():
    snapshot = ExplorationPlanSnapshot(
        asset_id="plan-event-1",
        asset_path="raw-records/exploration-plans/plan-1/plan-event-1.json",
        plan_id="plan-1",
        planning_session_id="session-1",
        dataset_id="ds-1",
        dataset_version=1,
        dataset_content_fingerprint="content-1",
        dataset_version_fingerprint="version-1",
        user_direction="Improve validation AUC",
        baseline_hypothesis="Start with a regularized linear model",
        rounds=(ExplorationRound(1, "Baseline", "baseline", ("fit baseline",)),),
        primary_metric="roc_auc",
        target_metric=0.9,
        stop_conditions=("target reached",),
        resource_limits={"max_minutes": 30},
        trusted_experience_ids=("exp-trusted",),
        pending_experience_ids=("exp-pending",),
        excluded_pending_experience_ids=("exp-excluded",),
        candidate_code_files=(CandidateCodeFile("train.py", "sha", 12),),
        code_fingerprint="code-sha",
        plan_fingerprint="plan-sha",
        state="pending_review",
        created_at="2026-07-15T00:00:00Z",
        created_by="alice",
    )

    payload = snapshot.to_dict()

    assert "version" not in payload
    assert payload["rounds"][0]["round_number"] == 1
    assert payload["candidate_code_files"][0]["path"] == "train.py"
```

- [ ] **Step 2: Run the model test and verify RED**

Run: `./.venv/bin/pytest tests/unit/test_exploration_models.py -q`

Expected: FAIL because the exploration dataclasses do not exist.

- [ ] **Step 3: Add immutable command and snapshot dataclasses**

Add these public contracts to `src/domain/models.py` and give snapshots `to_dict()` methods using the existing `_to_jsonable` helper:

```python
@dataclass(frozen=True)
class ExplorationRound:
    round_number: int
    hypothesis: str
    optimization_direction: str
    intended_changes: tuple[str, ...]


@dataclass(frozen=True)
class CandidateCodeFile:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class RecordExplorationPlanCommand:
    connection_path: Path
    code_root: Path
    dataset_id: str
    dataset_version: int
    plan_id: str
    planning_session_id: str
    user_direction: str
    baseline_hypothesis: str
    rounds: tuple[ExplorationRound, ...]
    stop_conditions: tuple[str, ...]
    resource_limits: dict[str, str | int | float]
    trusted_experience_ids: tuple[str, ...] = ()
    pending_experience_ids: tuple[str, ...] = ()
    excluded_pending_experience_ids: tuple[str, ...] = ()
    candidate_code_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApproveExplorationPlanCommand:
    connection_path: Path
    code_root: Path
    plan_id: str


@dataclass(frozen=True)
class AuthorizeTrainingCommand:
    connection_path: Path
    code_root: Path
    entry_point: str
    dataset_id: str
    dataset_version: int
    plan_id: str | None
    approval_id: str | None
```

Also add `ExplorationPlanSnapshot`, `ExplorationApprovalSnapshot`, `CandidateCodePreview`, `ExplorationReviewSnapshot`, and `TrainingAuthorization`. Do not add a `version` property to any exploration plan type.

- [ ] **Step 4: Run model tests and existing model tests**

Run: `./.venv/bin/pytest tests/unit/test_exploration_models.py tests/unit/test_memory_workspace_models.py tests/unit/test_dataset_intake_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit typed contracts**

```bash
git add src/domain/models.py tests/unit/test_exploration_models.py
git commit -m "feat(domain): define exploration approval contracts"
```

### Task 2: Append-Only Planning And Approval Repository

**Files:**
- Create: `src/domain/exploration_repository.py`
- Test: `tests/integration/test_exploration_repository.py`

- [ ] **Step 1: Write failing repository tests**

Cover these public behaviors in `tests/integration/test_exploration_repository.py`:

```python
def test_record_plan_appends_events_without_sop_style_versions(confirmed_workspace):
    first = confirmed_workspace.record_plan(user_direction="baseline")
    second = confirmed_workspace.record_plan(user_direction="add feature selection")

    assert first.asset_id != second.asset_id
    assert not hasattr(first, "version")
    assert confirmed_workspace.repository.current("plan-1") == second
    assert len(confirmed_workspace.repository.list_plan_events("plan-1")) == 2


def test_record_plan_separates_experience_confidence_and_exclusions(confirmed_workspace):
    plan = confirmed_workspace.record_plan(
        trusted=("experience-approved",),
        pending=("experience-pending", "experience-excluded"),
        excluded=("experience-excluded",),
    )

    assert plan.trusted_experience_ids == ("experience-approved",)
    assert plan.pending_experience_ids == (
        "experience-pending",
        "experience-excluded",
    )
    assert plan.excluded_pending_experience_ids == ("experience-excluded",)


def test_approval_binds_current_plan_dataset_and_code_fingerprints(confirmed_workspace):
    plan = confirmed_workspace.record_plan()
    approval = confirmed_workspace.repository.approve_current(
        plan.plan_id,
        code_root=confirmed_workspace.code_root,
        actor_id="alice",
        capacity=confirmed_workspace.capacity,
    )

    assert approval.plan_event_id == plan.asset_id
    assert approval.dataset_version_fingerprint == plan.dataset_version_fingerprint
    assert approval.plan_fingerprint == plan.plan_fingerprint
    assert approval.code_fingerprint == plan.code_fingerprint
```

Also test missing sections, duplicated confidence references, excluded IDs not present in Pending, unsafe `../` paths, symlinks, missing files, non-UTF-8 code, duplicate candidate paths, oversized event files, malformed stored JSON, and immutable path collisions.

- [ ] **Step 2: Run repository tests and verify RED**

Run: `./.venv/bin/pytest tests/integration/test_exploration_repository.py -q`

Expected: FAIL because `ExplorationRepository` does not exist.

- [ ] **Step 3: Implement canonical plan recording**

Create `ExplorationRepository` with these storage paths:

```python
PLAN_ROOT = Path("raw-records/exploration-plans")
APPROVAL_ROOT = Path("approvals/exploration-plans")
GATE_AUDIT_ROOT = Path("approvals/training-gates")
MAX_CODE_FILES = 32
MAX_CODE_FILE_BYTES = 1_000_000


class ExplorationRepository:
    def __init__(self, repository_path: Path, event_id_factory=None,
                 approval_id_factory=None, audit_id_factory=None,
                 clock=None) -> None:
        self.repository_path = repository_path.expanduser().resolve()
        self.event_id_factory = event_id_factory or (
            lambda: f"plan-event-{uuid.uuid4()}"
        )
        self.approval_id_factory = approval_id_factory or (
            lambda: f"plan-approval-{uuid.uuid4()}"
        )
        self.audit_id_factory = audit_id_factory or (
            lambda: f"gate-audit-{uuid.uuid4()}"
        )
        self.clock = clock or _utc_now
```

Implement the complete public methods `record_plan(command, dataset, actor_id, capacity)`,
`current(plan_id)`, `latest()`, `list_plan_events(plan_id)`,
`approve_current(plan_id, code_root, actor_id, capacity)`, and
`load_approval(plan_id, approval_id)`. Each loader validates the stored schema and returns the
corresponding typed snapshot; no loader infers or exposes a strategy version. Trusted Experience,
Pending Experience, and excluded Pending Experience references remain separate fields throughout.

Canonicalize plan payload with `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and SHA-256. Compute the aggregate code fingerprint from sorted relative path plus per-file SHA-256. Write each event once through a temporary sibling file and atomic rename. Validate every path component for symlinks and containment, mirroring `DatasetRepository` safety behavior.

- [ ] **Step 4: Implement approval and read-only preview behavior**

`approve_current` must recompute all code hashes and reject changed code with `candidate_code_changed`; it writes an `exploration_plan_approval` event containing `decision="approved"`, actor, timestamp, plan event ID, Dataset Version fingerprints, plan fingerprint, and code fingerprint. Add `review(plan_id, code_root)` to return the current plan, most recent applicable approval, code previews, and one of `pending_review`, `approved`, or `approval_stale` without mutating history.

- [ ] **Step 5: Run repository tests**

Run: `./.venv/bin/pytest tests/integration/test_exploration_repository.py -q`

Expected: PASS.

- [ ] **Step 6: Commit repository behavior**

```bash
git add src/domain/exploration_repository.py tests/integration/test_exploration_repository.py
git commit -m "feat(memory): store exploration planning events"
```

### Task 3: Domain Core Approval And Shared Training Gate

**Files:**
- Modify: `src/domain/core.py`
- Modify: `src/domain/exploration_repository.py`
- Test: `tests/contract/test_domain_core_exploration_plan.py`

- [ ] **Step 1: Write failing Domain Core contract tests**

```python
def test_domain_core_requires_exact_confirmed_dataset_when_recording_plan(workspace):
    with pytest.raises(WorkspaceError) as caught:
        workspace.core.record_exploration_plan(
            workspace.plan_command(dataset_version=99)
        )

    assert caught.value.code == "dataset_version_not_found"


def test_authorization_rejects_missing_approval_and_appends_minimal_audit(workspace):
    plan = workspace.record_plan()

    with pytest.raises(WorkspaceError) as caught:
        workspace.core.authorize_training(
            workspace.authorization_command(plan_id=plan.plan_id, approval_id=None)
        )

    assert caught.value.code == "plan_approval_required"
    audits = workspace.gate_audits()
    assert audits[-1]["reason_code"] == "plan_approval_required"
    assert "prompt" not in audits[-1]
    assert not list((workspace.memory_root / "runs").glob("**/*"))
    assert not list((workspace.memory_root / "models").glob("**/*"))


def test_authorization_rejects_stale_plan_or_code_and_accepts_exact_binding(workspace):
    plan = workspace.record_plan()
    approval = workspace.approve(plan.plan_id)
    authorization = workspace.authorize(plan.plan_id, approval.asset_id)
    assert authorization.authorized is True

    workspace.update_plan(plan.plan_id)
    with pytest.raises(WorkspaceError) as plan_error:
        workspace.authorize(plan.plan_id, approval.asset_id)
    assert plan_error.value.code == "approval_stale"
```

Add cases for code changes, requested Dataset Version mismatch, approval from another plan, malformed approval, unsafe code path at authorization time, and audit-write failure. Assert successful authorization only returns a binding and never creates Run, Training Instance, metric, prediction, or model assets.

- [ ] **Step 2: Run Domain Core tests and verify RED**

Run: `./.venv/bin/pytest tests/contract/test_domain_core_exploration_plan.py -q`

Expected: FAIL because the Domain Core methods do not exist.

- [ ] **Step 3: Add orchestration methods**

Implement `record_exploration_plan(command: RecordExplorationPlanCommand) ->
ExplorationPlanSnapshot`, `approve_exploration_plan(command: ApproveExplorationPlanCommand) ->
ExplorationApprovalSnapshot`, `get_exploration_review(connection_path: Path, code_root: Path,
plan_id: str | None = None) -> ExplorationReviewSnapshot | None`, and
`authorize_training(command: AuthorizeTrainingCommand) -> TrainingAuthorization` in `DomainCore`.

All four methods load actor and repository from `.mlagent-workspace.json`. Record uses `_require_confirmed_from_repository` and copies the Dataset Version metric and target instead of trusting plan JSON. Authorization compares requested Dataset Version, current planning event, approval event, and recomputed code fingerprint; every rejection after workspace resolution must append a concise training-gate audit before re-raising.

- [ ] **Step 4: Run Domain Core and prior dataset contracts**

Run: `./.venv/bin/pytest tests/contract/test_domain_core_exploration_plan.py tests/contract/test_domain_core_dataset_intake.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the shared gate**

```bash
git add src/domain/core.py src/domain/exploration_repository.py tests/contract/test_domain_core_exploration_plan.py
git commit -m "feat(domain): gate training on exact plan approval"
```

### Task 4: Claude Workflow And CLI Adapters

**Files:**
- Create: `.claude/skills/design-and-explore/SKILL.md`
- Modify: `src/agent/main.py`
- Test: `tests/integration/test_design_and_explore_cli.py`
- Modify: `tests/integration/test_explore_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Test `design-and-explore record --plan-file plan.json --code-root workspace`, `design-and-explore approve --plan-id plan-1 --code-root workspace`, and authoritative `explore --dataset-id ds-1 --dataset-version 1 --plan-id plan-1 --approval-id approval-1 --code-root workspace`. Use a fake Domain Core to assert adapters construct the typed commands exactly.

Add these gate assertions:

```python
def test_explore_does_not_call_execution_seam_when_authorization_fails(capsys):
    calls = []
    exit_code = main(
        [
            "explore",
            "--workspace-config", "/workspace/.mlagent-workspace.json",
            "--dataset-id", "ds-1",
            "--dataset-version", "1",
            "--plan-id", "plan-1",
            "--approval-id", "approval-1",
            "--code-root", "/workspace",
        ],
        domain_core_factory=lambda: DenyingCore("plan_approval_required"),
        explore_factory=lambda request: calls.append(request) or 0,
    )

    assert exit_code == 2
    assert calls == []
    assert "plan_approval_required" in capsys.readouterr().out


def test_approved_explore_reaches_issue_five_seam_with_bound_fingerprints():
    requests = []
    argv = [
        "explore",
        "--workspace-config", "/workspace/.mlagent-workspace.json",
        "--dataset-id", "ds-1",
        "--dataset-version", "1",
        "--plan-id", "plan-1",
        "--approval-id", "approval-1",
        "--code-root", "/workspace",
    ]
    assert main(
        argv,
        domain_core_factory=lambda: approved_core,
        explore_factory=lambda request: requests.append(request) or 0,
    ) == 0
    assert requests[0]["authorization"]["plan_fingerprint"] == "plan-sha"
    assert requests[0]["authorization"]["code_fingerprint"] == "code-sha"
```

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `./.venv/bin/pytest tests/integration/test_design_and_explore_cli.py tests/integration/test_explore_cli.py -q`

Expected: FAIL because the new command and approval gate are absent.

- [ ] **Step 3: Implement CLI parsing and delegation**

Parse the Claude-generated plan JSON into `ExplorationRound` and `RecordExplorationPlanCommand`. Print snapshot/error JSON using existing conventions. In authoritative `explore`, require `--plan-id`, `--approval-id`, and `--code-root`; call `DomainCore.authorize_training` before `explore_factory`. If no factory is injected after successful authorization, print `training_execution_not_implemented` and return 2 rather than invoking the legacy harness.

- [ ] **Step 4: Add the Claude Code Skill workflow**

The Skill must instruct Claude Code to:

1. obtain the exact confirmed Dataset Version;
2. expand the user's direction into complete plan JSON without scoring scientific quality;
3. generate candidate code under the selected code root;
4. call `design-and-explore record`;
5. direct the user to Run Status for read-only review;
6. call `design-and-explore approve` only after explicit human confirmation;
7. call authoritative `explore` with returned plan and approval IDs;
8. never describe an Exploration Plan as an SOP/versioned strategy or auto-approve it.

- [ ] **Step 5: Run CLI tests**

Run: `./.venv/bin/pytest tests/integration/test_design_and_explore_cli.py tests/integration/test_explore_cli.py tests/integration/test_real_explore_cli.py -q`

Expected: PASS, with legacy manifest-only prototype behavior unchanged and unable to write governed v0.4 Run assets.

- [ ] **Step 6: Commit adapters**

```bash
git add .claude/skills/design-and-explore/SKILL.md src/agent/main.py tests/integration/test_design_and_explore_cli.py tests/integration/test_explore_cli.py
git commit -m "feat(cli): add design and explore approval flow"
```

### Task 5: PreToolUse And Executor Bypass Protection

**Files:**
- Modify: `src/agent/hooks.py`
- Modify: `src/training/runner.py`
- Modify: `tests/contract/test_safety_hooks.py`
- Modify: `tests/integration/test_safety_runner_gate.py`

- [ ] **Step 1: Write failing Hook and runner tests**

```python
def test_pre_tool_use_delegates_training_authorization_to_domain_core():
    core = RecordingCore()
    result = authorize_training_tool(
        TrainingToolContext(
            connection_path=Path("/workspace/.mlagent-workspace.json"),
            code_root=Path("/workspace"),
            dataset_id="ds-1",
            dataset_version=1,
            plan_id="plan-1",
            approval_id="approval-1",
        ),
        domain_core=core,
    )
    assert result.authorized is True
    assert core.commands[0].entry_point == "claude_pre_tool_use"


def test_runner_never_executes_when_plan_gate_denies():
    calls = []
    with pytest.raises(WorkspaceError):
        run_command_with_training_gate(
            ["python", "train.py"],
            authorization_command=unauthorized_command,
            domain_core=denying_core,
            executor=lambda command: calls.append(command) or 0,
        )
    assert calls == []
```

- [ ] **Step 2: Run Hook tests and verify RED**

Run: `./.venv/bin/pytest tests/contract/test_safety_hooks.py tests/integration/test_safety_runner_gate.py -q`

Expected: FAIL because approval-aware adapters do not exist.

- [ ] **Step 3: Implement thin adapters**

Keep existing destructive-command and write-path safety checks. Add a typed `TrainingToolContext`, map it once to `AuthorizeTrainingCommand(entry_point="claude_pre_tool_use")`, and return the Domain Core authorization. Add `run_command_with_training_gate` that calls authorization first, then existing command safety, then the injected executor. Do not duplicate fingerprint or approval rules in either adapter.

- [ ] **Step 4: Run Hook and runner tests**

Run: `./.venv/bin/pytest tests/contract/test_safety_hooks.py tests/integration/test_safety_runner_gate.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Hook protection**

```bash
git add src/agent/hooks.py src/training/runner.py tests/contract/test_safety_hooks.py tests/integration/test_safety_runner_gate.py
git commit -m "feat(hook): block unapproved training tools"
```

### Task 6: Run Status Review And Approval UI

**Files:**
- Modify: `src/ui/shell.py`
- Modify: `src/ui/app.py`
- Modify: `tests/contract/test_ui_shell.py`
- Create: `tests/integration/test_run_status_ui.py`

- [ ] **Step 1: Write failing shell and Streamlit tests**

Test all required pre-run planning information:

```python
def test_run_status_renders_plan_confidence_code_and_approval(workspace, monkeypatch):
    workspace.record_plan(
        trusted=("experience-approved",),
        pending=("experience-pending", "experience-excluded"),
        excluded=("experience-excluded",),
    )
    app = load_app(workspace, monkeypatch)
    app.sidebar.radio[0].set_value("Run Status").run()

    assert not app.exception
    assert any("Pending review" in caption.value for caption in app.caption)
    assert any("Low confidence" in text.value for text in app.markdown)
    assert any("Excluded" in text.value for text in app.markdown)
    assert app.code[0].value == workspace.training_code
    assert app.button[0].label == "Approve current plan and code"


def test_run_status_approval_calls_domain_core_and_refreshes_state(workspace, monkeypatch):
    app = load_app(workspace, monkeypatch)
    app.sidebar.radio[0].set_value("Run Status").run()
    app.button[0].click().run()
    assert any("Approved" in caption.value for caption in app.caption)
```

Also test changed code displays `approval_stale`, missing code blocks approval, and a UI authorization check cannot succeed without approval.

- [ ] **Step 2: Run UI tests and verify RED**

Run: `./.venv/bin/pytest tests/contract/test_ui_shell.py tests/integration/test_run_status_ui.py -q`

Expected: FAIL because Run Status has no planning view.

- [ ] **Step 3: Make shell state planning-aware**

Extend `ShellState` with `exploration_review`. `build_shell_state` sets Run context/module state to `Pending review`, `Approved`, or `Failed` from the review snapshot while preserving current Dataset Overview behavior.

- [ ] **Step 4: Render the quiet operational Run Status view**

Read `MLAGENT_CODE_ROOT` with project root as default, query `DomainCore.get_exploration_review`, and render compact metrics for Dataset Version, metric/target, round count, and approval. Render baseline, each round's direction and changes, stop/resource tables, separate Trusted/Pending/Excluded experience sections, a file selector, and `st.code` read-only preview. The approval button calls `approve_exploration_plan`; the authorization check calls `authorize_training(entry_point="ui_run_status")`. No direct editor, diff, embedded CLI, performance chart, or mock run is added in Issue #4.

- [ ] **Step 5: Run UI and regression tests**

Run: `./.venv/bin/pytest tests/contract/test_ui_shell.py tests/integration/test_run_status_ui.py tests/integration/test_dataset_overview_ui.py tests/integration/test_streamlit_workspace_shell.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Run Status UI**

```bash
git add src/ui/shell.py src/ui/app.py tests/contract/test_ui_shell.py tests/integration/test_run_status_ui.py
git commit -m "feat(ui): review and approve exploration plans"
```

### Task 7: Cross-Artifact Review And Full Verification

**Files:**
- Modify only when a review finding requires a scoped correction.

- [ ] **Step 1: Prove no plan-version concept entered production code**

Run: `rg -n "ExplorationPlanVersion|exploration_plan_version|plan_version|方案版本" src .claude/skills/design-and-explore tests/unit/test_exploration_models.py tests/contract/test_domain_core_exploration_plan.py tests/integration/test_exploration_repository.py`

Expected: no production match; the intentional negative assertion in the model test may match only its test name.

- [ ] **Step 2: Run focused Issue #4 suite**

Run: `./.venv/bin/pytest tests/unit/test_exploration_models.py tests/integration/test_exploration_repository.py tests/contract/test_domain_core_exploration_plan.py tests/integration/test_design_and_explore_cli.py tests/integration/test_explore_cli.py tests/contract/test_safety_hooks.py tests/integration/test_safety_runner_gate.py tests/contract/test_ui_shell.py tests/integration/test_run_status_ui.py -q`

Expected: PASS.

- [ ] **Step 3: Run the complete regression suite**

Run: `./.venv/bin/pytest -q`

Expected: all tests pass; baseline before Issue #4 was 258 tests.

- [ ] **Step 4: Start the local Streamlit server and verify desktop/mobile views**

Run: `MLAGENT_WORKSPACE_CONFIG=/private/tmp/mlagent-issue4/.mlagent-workspace.json MLAGENT_CODE_ROOT=/private/tmp/mlagent-issue4/code ./.venv/bin/streamlit run src/ui/app.py --server.headless true --server.port 8501`

Use the in-app browser at `http://127.0.0.1:8501` to inspect Run Status at desktop and mobile widths. Verify no overlapping text, plan and confidence sections are readable, the code preview is non-editable, and the approval state refreshes.

- [ ] **Step 5: Request and address code review**

Review the branch against `430015a` and the approved design for security, bypass routes, stale approval handling, event immutability, minimum-record discipline, and tests. Apply only evidence-backed fixes, then rerun the affected tests and the complete suite.

- [ ] **Step 6: Commit final review fixes if any**

```bash
git add src .claude/skills/design-and-explore tests
git commit -m "fix(exploration): close approval review gaps"
```

- [ ] **Step 7: Push the branch and update Issue #4 handoff**

Run: `git push -u origin feat/issue-4-exploration-plan`

Expected: branch is available remotely with implementation and verification evidence; Issue #4 is ready for human review and remains distinct from Issue #5 training execution.
