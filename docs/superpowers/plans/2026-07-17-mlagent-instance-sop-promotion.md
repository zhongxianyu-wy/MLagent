# Training Instance To SOP Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote one specified successful Training Instance through complete evidence validation, independent reproduction, authorized approval, immutable SOP Version publication, and Formal Model registration.

**Architecture:** Add a dedicated `SopRepository` for authoritative SOP assets and a `SopPromotionCoordinator` that reuses `RunRepository` plus the existing training executor. `DomainCore` remains the only API used by Streamlit, while Git-backed manifests and append-only gate/approval records remain the source of truth.

**Tech Stack:** Python 3.13, frozen dataclasses, JSON/SHA-256 Git assets, `Decimal` six-place comparison, existing `RunRepository`/`TrainingExecutor`, Streamlit, pandas, pytest, Streamlit AppTest.

---

## File Map

- Create `src/domain/sop_repository.py`: reviewer policy, candidates, reproduction gates, approvals, SOP Versions, Formal Models, immutable publication.
- Create `src/domain/sop_promotion.py`: independent reproduction orchestration using frozen source evidence.
- Modify `src/domain/models.py`: SOP commands, evidence references, snapshots, status contracts.
- Modify `src/domain/run_repository.py`: expose source frozen-input/code helpers and add `sop_reproduction` retention.
- Modify `src/domain/memory_repository.py`: bootstrap reviewer policy and validate backwards-compatible default reviewer behavior.
- Modify `src/domain/core.py`: SOP workflow facade methods and factories.
- Modify `src/ui/shell.py`: SOP state in shell data and module status.
- Modify `src/ui/app.py`: SOP Overview candidate/reproduction/review/version UI.
- Create focused tests under `tests/unit/` and `tests/integration/` for each boundary.

### Task 1: Define SOP Domain Contracts

**Files:**
- Modify: `src/domain/models.py`
- Create: `tests/unit/test_sop_models.py`

- [ ] **Step 1: Write failing snapshot and command contract tests**

```python
def test_sop_candidate_requires_exactly_one_source_instance():
    candidate = sop_candidate_snapshot()
    assert candidate.source_run_id == "run-source"
    assert candidate.source_instance_id == "instance-source"
    assert candidate.steps == ("Load frozen Dataset Version", "Execute train.py")


def test_passed_gate_requires_distinct_reproduction_and_six_decimal_values():
    gate = sop_gate_snapshot()
    assert gate.source_instance_id != gate.reproduction_instance_id
    assert gate.source_metric_six_decimals == "0.812346"
    assert gate.reproduction_metric_six_decimals == "0.812346"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest tests/unit/test_sop_models.py -q`

Expected: collection fails because SOP model classes do not exist.

- [ ] **Step 3: Add immutable dataclasses and validation**

Add these public contracts with `to_dict()` support and strict `__post_init__` validation:

```python
@dataclass(frozen=True)
class SopEvidenceReference:
    role: str
    asset_id: str
    asset_path: str
    sha256: str


@dataclass(frozen=True)
class CreateSopCandidateCommand:
    connection_path: Path
    sop_id: str
    name: str
    source_run_id: str
    source_instance_id: str
    strategy_summary: str
    optimization_background: str
    steps: tuple[str, ...]
    change_summary: str


@dataclass(frozen=True)
class ReproduceSopCandidateCommand:
    connection_path: Path
    candidate_id: str
    expected_candidate_fingerprint: str


@dataclass(frozen=True)
class ReviewSopCandidateCommand:
    connection_path: Path
    candidate_id: str
    expected_candidate_fingerprint: str
    expected_gate_fingerprint: str
    decision: str


@dataclass(frozen=True)
class SopCandidateSnapshot:
    asset_id: str
    asset_path: str
    sop_id: str
    name: str
    source_run_id: str
    source_instance_id: str
    candidate_fingerprint: str
    dataset_id: str
    dataset_version: int
    dataset_content_fingerprint: str
    dataset_version_fingerprint: str
    code_fingerprint: str
    configuration_fingerprint: str
    environment_fingerprint: str
    split_fingerprint: str
    random_seed: int
    primary_metric_name: str
    source_metric_value: float
    source_model_fingerprint: str
    strategy_summary: str
    optimization_background: str
    steps: tuple[str, ...]
    change_summary: str
    evidence: tuple[SopEvidenceReference, ...]
    created_at: str
    created_by: str


@dataclass(frozen=True)
class SopReproductionGateSnapshot:
    asset_id: str
    asset_path: str
    candidate_id: str
    candidate_fingerprint: str
    gate_fingerprint: str
    outcome: str
    source_run_id: str
    source_instance_id: str
    reproduction_run_id: str
    reproduction_instance_id: str
    source_metric_value: float
    reproduction_metric_value: float | None
    source_metric_six_decimals: str
    reproduction_metric_six_decimals: str | None
    created_at: str
    created_by: str


@dataclass(frozen=True)
class SopVersionSnapshot:
    asset_id: str
    asset_path: str
    sop_id: str
    version: int
    version_fingerprint: str
    previous_version_id: str | None
    previous_version_fingerprint: str | None
    candidate_id: str
    source_run_id: str
    source_instance_id: str
    reproduction_run_id: str
    reproduction_instance_id: str
    dataset_id: str
    dataset_version: int
    primary_metric_name: str
    primary_metric_value: float
    strategy_summary: str
    optimization_background: str
    steps: tuple[str, ...]
    change_summary: str
    approval_id: str
    formal_model_id: str
    created_at: str
    created_by: str


@dataclass(frozen=True)
class FormalModelSnapshot:
    asset_id: str
    asset_path: str
    model_path: str
    model_fingerprint: str
    sop_version_id: str
    source_instance_id: str
    reproduction_instance_id: str
    dataset_id: str
    dataset_version: int
    primary_metric_name: str
    primary_metric_value: float
    strategy_summary: str
    optimization_background: str
    approval_id: str
    created_at: str
    created_by: str


@dataclass(frozen=True)
class SopCandidateStatus:
    candidate: SopCandidateSnapshot
    gate: SopReproductionGateSnapshot | None
    state: str


@dataclass(frozen=True)
class SopReviewOutcome:
    decision: str
    candidate_id: str
    gate_id: str
    approval_id: str
    sop_version: SopVersionSnapshot | None
    formal_model: FormalModelSnapshot | None
```

Require safe IDs, non-empty method text and steps, SHA-256 fingerprints, allowed gate outcomes, `approve|reject` decisions, distinct source/reproduction identities, and complete passed-gate metric fields.

- [ ] **Step 4: Run model tests and existing contract tests**

Run: `.venv/bin/pytest tests/unit/test_sop_models.py tests/unit/test_run_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_sop_models.py
git commit -m "feat(sop): define promotion contracts"
```

### Task 2: Establish Reviewer Policy

**Files:**
- Modify: `src/domain/memory_repository.py`
- Create: `tests/integration/test_sop_reviewer_policy.py`

- [ ] **Step 1: Write failing bootstrap and compatibility tests**

```python
def test_bootstrap_configures_creator_as_authorized_reviewer(tmp_path):
    root = tmp_path / "memory"
    MemoryRepository().bootstrap(root, actor_id="alice")
    policy = json.loads((root / "approvals/reviewer-policy.json").read_text())
    assert policy["reviewer_ids"] == ["alice"]
    assert policy["policy_fingerprint"]


def test_schema_one_repository_without_policy_uses_creator_only(memory_root):
    (memory_root / "approvals/reviewer-policy.json").unlink(missing_ok=True)
    assert load_authorized_reviewers(memory_root) == ("alice",)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest tests/integration/test_sop_reviewer_policy.py -q`

Expected: reviewer policy file/helper is missing.

- [ ] **Step 3: Write the fingerprinted policy during bootstrap**

Use this schema:

```json
{
  "asset_type": "reviewer_policy",
  "asset_id": "reviewer-policy",
  "schema_version": 1,
  "reviewer_ids": ["alice"],
  "created_at": "2026-07-17T00:00:00Z",
  "created_by": "alice",
  "policy_fingerprint": "sha256"
}
```

Validate exact identity, a sorted unique non-empty reviewer list, safe repository-relative path, and the content fingerprint. For repositories created before this file existed, read `.mlagent/repository.json` and return only its stable `created_by` identity.

- [ ] **Step 4: Run policy, bootstrap, and Git tests**

Run: `.venv/bin/pytest tests/integration/test_sop_reviewer_policy.py tests/integration/test_memory_repository.py tests/integration/test_git_sync_hooks.py -q`

Expected: PASS with reviewer policy included in managed approval assets.

- [ ] **Step 5: Commit**

```bash
git add src/domain/memory_repository.py tests/integration/test_sop_reviewer_policy.py tests/integration/test_memory_repository.py
git commit -m "feat(memory): configure SOP reviewers"
```

### Task 3: Create And Validate SOP Candidates

**Files:**
- Create: `src/domain/sop_repository.py`
- Create: `tests/integration/test_sop_repository.py`
- Modify: `src/domain/run_repository.py`

- [ ] **Step 1: Write failing complete-candidate test**

Build a real governed Dataset, Run, frozen Code Revision, successful retained Training Instance, then assert:

```python
candidate = repository.create_candidate(
    sop_candidate_spec(source_run_id="run-1", source_instance_id="instance-1"),
    actor_id="alice",
    capacity=capacity,
)
assert candidate.source_instance_id == "instance-1"
assert {item.role for item in candidate.evidence} == {
    "dataset", "run", "training_instance", "input", "environment",
    "split", "code_revision", "metrics", "predictions", "source_model",
}
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/bin/pytest tests/integration/test_sop_repository.py::test_complete_source_creates_immutable_candidate -q`

Expected: `SopRepository` is missing.

- [ ] **Step 3: Expose safe read helpers from RunRepository**

Add public read-only methods that reuse existing validation:

```python
def load_instance_input(self, run_id: str, instance_id: str) -> dict[str, Any]:
    self.load_instance(run_id, instance_id)
    path = self.repository_path / RUN_ROOT / run_id / "instances" / instance_id / "input.json"
    return self._load_json(path, "invalid_training_instance")


def load_instance_environment(self, run_id: str, instance_id: str) -> dict[str, Any]:
    self.load_instance(run_id, instance_id)
    path = self.repository_path / RUN_ROOT / run_id / "instances" / instance_id / "environment.json"
    return self._load_json(path, "invalid_training_instance")


def load_instance_file(self, run_id: str, instance_id: str, role: str) -> Path:
    instance = self.load_instance(run_id, instance_id)
    manifest = self._load_json(self.repository_path / instance.asset_path, "invalid_training_instance")
    filename = manifest["files"][role]
    path = self.repository_path / instance.asset_path
    return path.parent / filename


def load_code_revision_for_instance(
    self,
    run_id: str,
    instance_id: str,
) -> FrozenCodeRevisionSnapshot:
    input_payload = self.load_instance_input(run_id, instance_id)
    return self._load_code_revision(
        self.repository_path / input_payload["code_revision_path"],
        run_id,
    )
```

Each method must call `load_instance()` first, verify manifest declarations and SHA-256 values, reject symbolic/outside paths, and never return unvalidated evidence.

- [ ] **Step 4: Implement candidate construction**

`SopRepository.create_candidate()` must:

1. require source state `completed`;
2. require metrics, predictions, and a retained model;
3. bind Dataset, RunStart, instance manifest, input/environment/split, code revision, seed, plan, and approval fingerprints;
4. emit a structured `WorkspaceError(code="sop_source_incomplete")` containing missing role names;
5. seal `sops/candidates/{candidate_id}/manifest.json` atomically;
6. return the existing identical candidate on retry and reject ID reuse with different content.

- [ ] **Step 5: Add RED tests for every incomplete source boundary**

Parameterize deletion/tampering of `model`, `metrics`, `predictions`, `input`, `environment`, `split`, and code files. Add separate tests for failed instance state, Dataset mismatch, and source model fingerprint mismatch. Every case must assert no candidate JSON exists.

- [ ] **Step 6: Implement minimal validation until all candidate tests pass**

Run: `.venv/bin/pytest tests/integration/test_sop_repository.py -k 'candidate or source' -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/domain/sop_repository.py src/domain/run_repository.py tests/integration/test_sop_repository.py
git commit -m "feat(sop): create evidence-bound candidates"
```

### Task 4: Execute An Independent Reproduction

**Files:**
- Create: `src/domain/sop_promotion.py`
- Create: `tests/integration/test_sop_promotion.py`
- Modify: `src/domain/run_repository.py`

- [ ] **Step 1: Write a failing successful-reproduction test**

Use a deterministic fake `TrainingExecutor` and assert:

```python
gate = coordinator.reproduce(candidate, actor_id="alice")
assert gate.outcome == "passed"
assert gate.reproduction_run_id != candidate.source_run_id
assert gate.reproduction_instance_id != candidate.source_instance_id
assert gate.source_metric_six_decimals == gate.reproduction_metric_six_decimals
assert run_repository.load_instance(
    gate.reproduction_run_id,
    gate.reproduction_instance_id,
).model_retention_reasons == ("sop_reproduction",)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/bin/pytest tests/integration/test_sop_promotion.py::test_reproduction_uses_distinct_exact_execution -q`

Expected: coordinator is missing.

- [ ] **Step 3: Add `sop_reproduction` retention support**

Extend `MODEL_RETENTION_REASONS` and model validation to allow exactly `sop_reproduction` for an independent SOP reproduction instance. Preserve existing baseline/stage-best/human-marked behavior.

- [ ] **Step 4: Implement `SopPromotionCoordinator`**

The coordinator must:

- revalidate candidate evidence before execution;
- create a new Run with the source Dataset/plan/approval bindings;
- copy the validated frozen code package, never mutable project code;
- prepare one parentless instance using the exact source input/environment/split/seed;
- execute and seal through existing worker APIs;
- retain a successful reproduction model;
- always finish the reproduction Run with a terminal reason.

- [ ] **Step 5: Verify exact frozen bindings**

Add assertions that source and reproduction configuration, environment, split, Dataset, code, random seed, plan, and approval fingerprints are equal. Run:

`.venv/bin/pytest tests/integration/test_sop_promotion.py -k 'reproduction_uses or exact_fingerprints' -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/domain/sop_promotion.py src/domain/run_repository.py src/domain/models.py tests/integration/test_sop_promotion.py
git commit -m "feat(sop): execute independent reproduction"
```

### Task 5: Seal Reproduction Gate Outcomes

**Files:**
- Modify: `src/domain/sop_repository.py`
- Modify: `src/domain/sop_promotion.py`
- Modify: `tests/integration/test_sop_promotion.py`
- Modify: `tests/integration/test_sop_repository.py`

- [ ] **Step 1: Write failing six-decimal gate tests**

```python
@pytest.mark.parametrize(
    ("source", "reproduced", "outcome"),
    ((0.81234551, 0.81234549, "metric_mismatch"),
     (0.81234551, 0.81234552, "passed")),
)
def test_gate_compares_round_half_up_at_six_places(source, reproduced, outcome):
    assert compare_reproduction_metric(source, reproduced) == outcome
```

Also add tests for executor failure and changed reproduction fingerprint.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest tests/integration/test_sop_promotion.py -k 'gate or failed' -q`

Expected: gate outcomes are not implemented.

- [ ] **Step 3: Implement decimal comparison and gate recording**

Use exactly:

```python
SIX_PLACES = Decimal("0.000001")

def metric_at_six_places(value: float) -> str:
    return format(
        Decimal(str(value)).quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
        ".6f",
    )
```

Write one immutable gate record under `approvals/sop-reproductions/{candidate_id}/{gate_id}.json`. The gate fingerprint includes candidate fingerprint, reproduction identities, all compared fingerprints, metric strings, outcome, actor, and time.

- [ ] **Step 4: Make gate retries idempotent**

Return the existing identical gate on retry. Reject a second differing gate for the same candidate with `sop_gate_exists`; require a new candidate instead.

- [ ] **Step 5: Run all reproduction and repository tests**

Run: `.venv/bin/pytest tests/integration/test_sop_promotion.py tests/integration/test_sop_repository.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/domain/sop_repository.py src/domain/sop_promotion.py tests/integration/test_sop_promotion.py tests/integration/test_sop_repository.py
git commit -m "feat(sop): enforce reproduction gate"
```

### Task 6: Approve Immutable SOP Version And Formal Model

**Files:**
- Modify: `src/domain/sop_repository.py`
- Modify: `tests/integration/test_sop_repository.py`

- [ ] **Step 1: Write failing successful-publication test**

```python
outcome = repository.review_candidate(
    review_command(decision="approve"),
    actor_id="alice",
    capacity=capacity,
)
assert outcome.sop_version.version == 1
assert outcome.formal_model.sop_version_id == outcome.sop_version.asset_id
assert formal_model_bytes == reproduction_model_bytes
assert outcome.formal_model.model_fingerprint == sha256(formal_model_bytes).hexdigest()
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/bin/pytest tests/integration/test_sop_repository.py::test_authorized_approval_publishes_sop_and_reproduction_model -q`

Expected: review/publication method is missing.

- [ ] **Step 3: Implement authorization and freshness gates**

Before writing, require:

- actor in the fingerprint-valid reviewer policy;
- expected candidate and gate fingerprints equal current records;
- gate outcome `passed`;
- reproduction model path and SHA still match;
- candidate source and reproduction identities remain distinct.

Reject with `unauthorized_sop_reviewer`, `stale_sop_review`, or `sop_gate_not_passed` before any formal file write.

- [ ] **Step 4: Implement append-only publication**

Under one lock, calculate the next `vNNNN`, previous version fingerprint, model ID, and all final bytes. Preflight capacity and collisions. Write Formal Model binary/manifest, SOP manifest, then approval marker last. Readers expose only a complete set whose hashes and cross-references match.

- [ ] **Step 5: Add failure and immutability tests**

Cover unauthorized approval, pending/failed gate, six-decimal mismatch, source actor attempting approval, interrupted publication retry, changed existing file, repeated identical approval, second source creating version 2, previous version unchanged, and required change summary for version 2.

- [ ] **Step 6: Run repository tests**

Run: `.venv/bin/pytest tests/integration/test_sop_repository.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/domain/sop_repository.py tests/integration/test_sop_repository.py
git commit -m "feat(sop): publish approved formal assets"
```

### Task 7: Add Domain Core SOP Workflow

**Files:**
- Modify: `src/domain/core.py`
- Create: `tests/integration/test_domain_core_sop.py`

- [ ] **Step 1: Write failing end-to-end Domain Core tests**

Test these public calls:

```python
candidate = core.create_sop_candidate(command)
gate = core.reproduce_sop_candidate(reproduce_command)
approved = core.review_sop_candidate(approve_command)
assert core.list_sop_versions(connection)[0] == approved.sop_version
assert core.get_formal_model(connection, approved.formal_model.asset_id)
```

Add a test that passing an Experience ID where a source Run/Instance is required returns `training_instance_not_found` and creates no SOP asset.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest tests/integration/test_domain_core_sop.py -q`

Expected: Domain Core SOP methods are missing.

- [ ] **Step 3: Add factories and facade methods**

Inject deterministic candidate/gate/approval/model/run/instance ID factories and an executor factory for tests. Every method must open the connected repository, use its actor and capacity, call only the domain repository/coordinator, rebuild Local Index after authoritative writes, and return typed snapshots.

- [ ] **Step 4: Verify full and blocked flows**

Run: `.venv/bin/pytest tests/integration/test_domain_core_sop.py tests/integration/test_domain_core_experience.py -q`

Expected: PASS; Experience behavior remains independent.

- [ ] **Step 5: Commit**

```bash
git add src/domain/core.py tests/integration/test_domain_core_sop.py
git commit -m "feat(core): expose SOP promotion workflow"
```

### Task 8: Build SOP Overview UI

**Files:**
- Modify: `src/ui/shell.py`
- Modify: `src/ui/app.py`
- Modify: `tests/contract/test_ui_shell.py`
- Create: `tests/integration/test_sop_overview_ui.py`

- [ ] **Step 1: Write failing shell-state tests**

Assert SOP module status is `Pending review` when any candidate awaits reproduction/approval, `Failed` when the selected candidate gate failed, and `Approved` when at least one formal version exists without pending candidates.

- [ ] **Step 2: Write failing AppTest for candidate workflow**

Seed an eligible instance and assert `SOP Overview` renders:

- eligible source selector;
- SOP name/ID, strategy summary, optimization background, ordered steps, and change summary inputs;
- candidate evidence and reproduction action;
- gate result and authorization-safe approval controls.

- [ ] **Step 3: Run UI tests and verify RED**

Run: `.venv/bin/pytest tests/contract/test_ui_shell.py tests/integration/test_sop_overview_ui.py -q`

Expected: SOP data is absent from shell and app.

- [ ] **Step 4: Add SOP data to shell and application load**

Extend `ShellState` with candidates and versions. Load them once through Domain Core in `main()`. Render `Candidates` and `Approved Versions` tabs without nested cards.

- [ ] **Step 5: Implement candidate, reproduction, and review actions**

Use a form for candidate creation, an icon/text command button for reproduction, approve/reject buttons only when the gate is reviewable, `st.spinner()` during reproduction, `WorkspaceError` message plus next action, and `st.rerun()` after success.

- [ ] **Step 6: Implement approved version details and trend**

Display source/reproduction IDs, Dataset Version, strategy, background, steps, environment, gate values, approval, and Formal Model. Build one pandas frame with `Version` and `Primary metric`, then render `st.line_chart` with stable dimensions.

- [ ] **Step 7: Run UI tests**

Run: `.venv/bin/pytest tests/contract/test_ui_shell.py tests/integration/test_sop_overview_ui.py tests/integration/test_experience_review_ui.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ui/shell.py src/ui/app.py tests/contract/test_ui_shell.py tests/integration/test_sop_overview_ui.py
git commit -m "feat(ui): add SOP promotion workspace"
```

### Task 9: Harden Cross-Asset Integrity

**Files:**
- Modify: `src/domain/sop_repository.py`
- Modify: `src/domain/sop_promotion.py`
- Modify: `tests/integration/test_sop_repository.py`
- Modify: `tests/integration/test_sop_promotion.py`

- [ ] **Step 1: Add adversarial RED tests**

Tamper and reseal one direct asset at a time to attempt cross-Run, cross-Instance, cross-Dataset, cross-candidate, and cross-version evidence substitution. Also test symlinks, path traversal, duplicate IDs, concurrent version collision, model replacement after gate, and reviewer-policy fingerprint tampering.

- [ ] **Step 2: Run adversarial tests and verify RED**

Run: `.venv/bin/pytest tests/integration/test_sop_repository.py tests/integration/test_sop_promotion.py -k 'tamper or substitution or collision or symlink' -q`

Expected: each new test fails at the missing integrity check.

- [ ] **Step 3: Add exact coherence validation**

Validate candidate, source RunStart, source input/manifest, gate, reproduction RunStart/input/manifest, approval, SOP Version, and Formal Model as one coherent chain. Internal hashes alone are insufficient; all stable IDs and declared paths must match across the chain.

- [ ] **Step 4: Run focused and full domain suites**

Run: `.venv/bin/pytest tests/integration/test_sop_repository.py tests/integration/test_sop_promotion.py tests/integration/test_run_repository.py tests/integration/test_domain_core_sop.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/sop_repository.py src/domain/sop_promotion.py tests/integration/test_sop_repository.py tests/integration/test_sop_promotion.py
git commit -m "fix(sop): harden formal asset lineage"
```

### Task 10: Final Acceptance And Handoff

**Files:**
- Modify only files required by findings from verification or review.

- [ ] **Step 1: Run formatting and static checks**

```bash
.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run the complete test suite**

Run: `.venv/bin/pytest -q`

Expected: all tests pass with zero failures.

- [ ] **Step 3: Request independent code review**

Ask the reviewer to prioritize unauthorized publication, prevalidation-before-write, six-decimal semantics, evidence substitution, idempotent interruption recovery, Formal Model source, and mobile UI behavior. Fix every confirmed P0/P1/P2 finding with a failing test first.

- [ ] **Step 4: Run real browser acceptance**

Start Streamlit with a fresh governed fixture and verify at `1440x1000` and `390x844`:

- candidate creation and source details;
- passed and failed gate displays;
- approved SOP Version and Formal Model details;
- version trend chart is visible;
- no page-level horizontal overflow;
- no browser console warning/error.

- [ ] **Step 5: Commit final review fixes**

```bash
git add src/domain/sop_repository.py src/domain/sop_promotion.py src/domain/core.py src/domain/models.py src/domain/run_repository.py src/ui/app.py src/ui/shell.py tests/unit/test_sop_models.py tests/integration/test_sop_reviewer_policy.py tests/integration/test_sop_repository.py tests/integration/test_sop_promotion.py tests/integration/test_domain_core_sop.py tests/integration/test_sop_overview_ui.py tests/contract/test_ui_shell.py
git commit -m "fix(sop): close promotion review findings"
```

Omit this commit when review produces no changes.

- [ ] **Step 6: Push and update Issue #8**

```bash
git push --set-upstream origin feat/issue-8-sop-promotion
gh issue comment 8 --repo zhongxianyu-wy/MLagent --body "Implemented and verified on feat/issue-8-sop-promotion."
gh issue edit 8 --repo zhongxianyu-wy/MLagent --remove-label ready-for-agent --add-label ready-for-human
```

Record the final commit, exact test count, browser viewports, review result, and branch URL in the Issue comment.

---

## Plan Self-Review

- Every Issue #8 acceptance criterion maps to Tasks 3 through 9.
- Notebook import and new-data SOP retraining remain out of scope.
- Candidate, gate, approval, SOP Version, and Formal Model identities remain distinct.
- Formal publication is gated by exact reproduction plus reviewer authorization.
- All production behavior begins with a failing test and ends with focused plus full verification.
