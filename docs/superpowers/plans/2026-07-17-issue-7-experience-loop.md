# Experience Extraction, Review, And Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an evidence-bounded, human-governed Experience lifecycle that extracts only current-session training lessons, supports immutable review and reuse, records actual usage, and cannot mutate SOP assets.

**Architecture:** A new append-only `ExperienceRepository` owns session markers, extraction, lifecycle projections, and deterministic retrieval inside Team Memory. Domain Core validates Experience references before planning and carries included citations into frozen Run evidence. Claude Code hooks and Streamlit remain thin adapters over Domain Core.

**Tech Stack:** Python 3.11+, dataclasses, atomic JSON files, SHA-256 evidence validation, native Git-backed Team Memory, pytest, Streamlit AppTest.

---

## File Map

- `src/domain/models.py`: Experience commands, projections, citations, session outcomes, and invariants.
- `src/domain/experience_repository.py`: authoritative append-only Experience and session evidence service.
- `src/domain/core.py`: Experience application boundary and plan-reference validation.
- `src/domain/exploration_repository.py`: applicability reasons in plan events.
- `src/domain/run_repository.py`: included Experience usage in Run and Training Instance evidence.
- `src/domain/run_execution.py`: propagate approved plan citations into Run creation and instances.
- `src/agent/session_start.py`: pass session identity and report Pending review count.
- `src/agent/session_stop.py`: extract before Git synchronization.
- `.claude/skills/review-experience/SKILL.md`: bounded human review workflow.
- `src/ui/shell.py`: Experience projection in shell state and module status.
- `src/ui/app.py`: Experience Review sections, evidence, history, and actions.
- `tests/unit/test_experience_models.py`: contract invariants.
- `tests/integration/test_experience_repository.py`: extraction, lifecycle, evidence, retrieval, and SOP isolation.
- `tests/integration/test_domain_core_experience.py`: Domain Core and planning validation.
- `tests/integration/test_experience_hooks.py`: lifecycle hook behavior.
- `tests/integration/test_experience_usage_writeback.py`: frozen plan-to-result citations.
- `tests/integration/test_experience_review_ui.py`: all UI partitions and actions.
- `tests/contract/test_ui_shell.py`: Experience module status projection.

### Task 1: Define Experience Domain Contracts

**Files:**
- Modify: `src/domain/models.py`
- Create: `tests/unit/test_experience_models.py`

- [ ] **Step 1: Write failing model tests**

```python
from pathlib import Path

import pytest

from src.domain.models import (
    ExperienceContent,
    ExperienceEvidence,
    ExperienceSnapshot,
    ReviewExperienceCommand,
)


def test_pending_experience_requires_all_direct_evidence_roles():
    with pytest.raises(ValueError, match="evidence roles"):
        ExperienceSnapshot(
            asset_id="experience-1",
            asset_path="experiences/experience-1/event-1.json",
            event_id="event-1",
            previous_event_id=None,
            state="pending",
            content=ExperienceContent(
                conclusion="Feature filtering improved roc_auc.",
                applicability="Same assay and label definition.",
                recommended_action="Retest filtering.",
                failure_boundary="One frozen split.",
                risk="May not transfer.",
                confidence=0.6,
            ),
            evidence=(
                ExperienceEvidence(
                    role="dataset",
                    asset_id="dataset-1:v1",
                    asset_path="datasets/dataset-1/v0001/manifest.json",
                    sha256="a" * 64,
                ),
            ),
            extraction_session_id="session-1",
            source_kind="metric_improvement",
            relation_type=None,
            related_experience_id=None,
            created_at="2026-07-17T00:00:00Z",
            created_by="agent",
            reviewed_at=None,
            reviewed_by=None,
            decision=None,
        )


def test_review_command_rejects_empty_reviewer_content():
    with pytest.raises(ValueError, match="conclusion"):
        ReviewExperienceCommand(
            connection_path=Path(".mlagent-workspace.json"),
            experience_id="experience-1",
            decision="approve",
            content=ExperienceContent(
                conclusion="",
                applicability="Same data.",
                recommended_action="Retest.",
                failure_boundary="One run.",
                risk="May vary.",
                confidence=0.8,
            ),
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/test_experience_models.py -q
```

Expected: collection fails because Experience contracts do not exist.

- [ ] **Step 3: Implement immutable contracts**

Add validated dataclasses for:

```python
@dataclass(frozen=True)
class ExperienceContent:
    conclusion: str
    applicability: str
    recommended_action: str
    failure_boundary: str
    risk: str
    confidence: float


@dataclass(frozen=True)
class ExperienceEvidence:
    role: str
    asset_id: str
    asset_path: str
    sha256: str


@dataclass(frozen=True)
class ExperienceCitation:
    experience_id: str
    event_id: str
    state: str
    why_applicable: str


@dataclass(frozen=True)
class ExperienceSnapshot:
    asset_id: str
    asset_path: str
    event_id: str
    previous_event_id: str | None
    state: str
    content: ExperienceContent
    evidence: tuple[ExperienceEvidence, ...]
    extraction_session_id: str
    source_kind: str
    relation_type: str | None
    related_experience_id: str | None
    created_at: str
    created_by: str
    reviewed_at: str | None
    reviewed_by: str | None
    decision: str | None


@dataclass(frozen=True)
class ReviewExperienceCommand:
    connection_path: Path
    experience_id: str
    decision: str
    content: ExperienceContent
    related_experience_id: str | None = None
```

Also add `ExperienceSearchResult`, `SessionExperienceOutcome`, and
`CompleteSessionCommand`. Validate state, confidence, relation pairing,
evidence roles, safe non-empty IDs, and JSON serialization.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_experience_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_experience_models.py
git commit -m "feat(domain): define experience contracts"
```

### Task 2: Establish Session Boundaries And Conservative Extraction

**Files:**
- Create: `src/domain/experience_repository.py`
- Create: `tests/integration/test_experience_repository.py`

- [ ] **Step 1: Write failing session extraction tests**

Create a real Team Memory fixture with one old completed Run, call
`start_session("session-1")`, then add a completed child instance whose metric
improves over its parent. Assert:

```python
outcome = experiences.complete_session(
    "session-1",
    actor_id="alice",
    capacity=capacity,
)

assert outcome.outcome == "created"
assert len(outcome.candidate_ids) == 1
candidate = experiences.current(outcome.candidate_ids[0])
assert candidate.state == "pending"
assert {item.role for item in candidate.evidence} == {
    "dataset",
    "run",
    "training_instance",
    "raw_record",
}
assert "roc_auc" in candidate.content.conclusion
assert old_instance.asset_id not in outcome.new_instance_ids
```

Add a baseline-only session and assert `outcome == "no_op"`,
`candidate_ids == ()`, no file exists under `experiences/`, and
`raw-records/sessions/session-1/stop.json` records `no_op`. Repeat Stop and
assert no new files.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_experience_repository.py \
  -k "session or improvement or no_op" -q
```

Expected: FAIL because `ExperienceRepository` does not exist.

- [ ] **Step 3: Implement session markers and evidence scan**

Create:

```python
SESSION_ROOT = Path("raw-records/sessions")
EXPERIENCE_ROOT = Path("experiences")


class ExperienceRepository:
    def start_session(
        self,
        session_id: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> SessionExperienceOutcome:
        ...

    def complete_session(
        self,
        session_id: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> SessionExperienceOutcome:
        ...
```

The start marker stores the current Run event and Training Instance ID sets.
Completion computes set differences, validates each referenced asset and hash,
creates improvement candidates only for completed child instances with a
positive metric delta, creates failure candidates only for failed child
instances, skips stopped/timed-out/baseline evidence, and writes the immutable
stop record. Use new-file atomic writes and projected capacity checks matching
the existing repositories.

- [ ] **Step 4: Add evidence-integrity and failure extraction tests**

Tamper with a Dataset or Training Instance after candidate creation and assert
`current()` fails closed. Add a failed child instance and assert the candidate
captures bounded error code/summary in its conclusion and failure boundary.
Assert full logs and unrelated files do not appear in any Experience file.

- [ ] **Step 5: Run extraction tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_experience_repository.py \
  -k "session or extraction or evidence or no_op" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/domain/experience_repository.py \
  tests/integration/test_experience_repository.py
git commit -m "feat(memory): extract session experiences"
```

### Task 3: Implement Immutable Review Lifecycle And SOP Isolation

**Files:**
- Modify: `src/domain/experience_repository.py`
- Modify: `tests/integration/test_experience_repository.py`

- [ ] **Step 1: Write failing lifecycle tests**

Assert:

```python
trusted = experiences.review(
    ReviewExperienceCommand(
        connection_path=connection,
        experience_id=pending.asset_id,
        decision="approve",
        content=replace(
            pending.content,
            conclusion="Reviewed conclusion.",
            confidence=0.9,
        ),
    ),
    actor_id="reviewer",
    capacity=capacity,
)

assert trusted.state == "trusted"
assert trusted.previous_event_id == pending.event_id
assert experiences.history(pending.asset_id)[0].content == pending.content
assert trusted.reviewed_by == "reviewer"
```

Cover Pending to Rejected and Conflict, Conflict to Trusted/Rejected, and
Trusted to Superseded with a distinct current Trusted replacement. Assert all
other transitions fail before writing.

Snapshot every file and byte under `sops/` and `models/` before extraction and
every review transition, then assert the snapshots are unchanged.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_experience_repository.py \
  -k "review or conflict or supersed or sop" -q
```

Expected: FAIL because lifecycle review is not implemented.

- [ ] **Step 3: Implement append-only review**

Add `history()`, `current()`, `list_current()`, and `review()`. Derive the
single current head through predecessor links and fail on missing predecessors,
cycles, or concurrent heads. Implement the exact transition table from the
design. Preserve evidence and extraction identity on every event; record
reviewed fields, relation, actor, timestamp, and decision in a unique JSON
event.

- [ ] **Step 4: Run lifecycle and SOP-isolation tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_experience_repository.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/experience_repository.py \
  tests/integration/test_experience_repository.py
git commit -m "feat(memory): govern experience review history"
```

### Task 4: Add Retrieval And Validate Exploration Usage

**Files:**
- Modify: `src/domain/experience_repository.py`
- Modify: `src/domain/models.py`
- Modify: `src/domain/core.py`
- Modify: `src/domain/exploration_repository.py`
- Create: `tests/integration/test_domain_core_experience.py`
- Modify: `tests/integration/test_exploration_repository.py`
- Modify: `tests/unit/test_exploration_models.py`

- [ ] **Step 1: Write failing retrieval and plan-validation tests**

Seed Trusted, Pending, Rejected, Conflict, and Superseded Experiences. Assert:

```python
trusted, pending = core.search_experiences(
    connection,
    query="feature filtering roc_auc",
    dataset_id="dataset-1",
    include_pending=True,
)

assert {item.experience.state for item in trusted} == {"trusted"}
assert {item.experience.state for item in pending} == {"pending"}
assert all(item.why_applicable for item in (*trusted, *pending))
```

Record a plan with trusted and active Pending IDs plus
`experience_applicability`. Assert Domain Core rejects missing IDs,
misclassified states, excluded IDs marked as used, and missing applicability
reasons.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_domain_core_experience.py \
  tests/integration/test_exploration_repository.py -q
```

Expected: FAIL because retrieval and applicability contracts do not exist.

- [ ] **Step 3: Implement deterministic retrieval**

Rank current Trusted and optional Pending projections using normalized query
terms against conclusion, applicability, recommendation, risk, metric, and
Dataset evidence. Return `ExperienceSearchResult` with a bounded
`why_applicable`; do not return Rejected, Conflict, or Superseded states.

- [ ] **Step 4: Persist applicability in Exploration Plans**

Add:

```python
experience_applicability: dict[str, str] = field(default_factory=dict)
```

to plan command and snapshot contracts. Include it in plan fingerprints and
validation. Domain Core loads each current Experience, verifies its confidence
group, requires reasons for all included IDs, and allows Pending exclusion
without marking it used.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_domain_core_experience.py \
  tests/integration/test_exploration_repository.py \
  tests/unit/test_exploration_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/domain/experience_repository.py src/domain/models.py \
  src/domain/core.py src/domain/exploration_repository.py \
  tests/integration/test_domain_core_experience.py \
  tests/integration/test_exploration_repository.py \
  tests/unit/test_exploration_models.py
git commit -m "feat(exploration): retrieve and cite experience"
```

### Task 5: Write Included Experience Into Frozen Training Results

**Files:**
- Modify: `src/domain/run_repository.py`
- Modify: `src/domain/run_execution.py`
- Create: `tests/integration/test_experience_usage_writeback.py`
- Modify: `tests/unit/test_run_models.py`

- [ ] **Step 1: Write failing usage-writeback test**

Execute a Run from an approved plan with one Trusted and one active Pending
citation plus one excluded Pending ID. Assert the Run start event and every
sealed Training Instance manifest include:

```python
[
    {
        "experience_id": "experience-trusted",
        "event_id": "trusted-event",
        "state": "trusted",
        "why_applicable": "Same assay and metric.",
    },
    {
        "experience_id": "experience-pending",
        "event_id": "pending-event",
        "state": "pending",
        "why_applicable": "Candidate direction matches.",
    },
]
```

Assert the excluded ID is absent and changing any citation invalidates the Run
event or Training Instance fingerprint.

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_experience_usage_writeback.py -q
```

Expected: FAIL because frozen Run evidence lacks Experience citations.

- [ ] **Step 3: Propagate immutable citations**

Add Experience citations to `RunStartSpec`, the allowed Run event fields,
`InstancePreparationSpec`, `input.json`, Training Instance manifests, and
snapshots. Build citations in Domain Core only after validating the approved
plan against current Experience event IDs. Copy the same ordered tuple through
`TrainingRunCoordinator`.

- [ ] **Step 4: Run focused Run tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_experience_usage_writeback.py \
  tests/integration/test_domain_core_training_instance.py \
  tests/unit/test_run_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/run_repository.py src/domain/run_execution.py \
  src/domain/core.py src/domain/models.py \
  tests/integration/test_experience_usage_writeback.py \
  tests/integration/test_domain_core_training_instance.py \
  tests/unit/test_run_models.py
git commit -m "feat(training): freeze experience usage"
```

### Task 6: Wire SessionStart, Stop, And Review Skill

**Files:**
- Modify: `src/domain/core.py`
- Modify: `src/agent/session_start.py`
- Modify: `src/agent/session_stop.py`
- Create: `.claude/skills/review-experience/SKILL.md`
- Create: `tests/integration/test_experience_hooks.py`
- Modify: `tests/integration/test_git_sync_hooks.py`

- [ ] **Step 1: Write failing hook tests**

Assert SessionStart passes `session_id` after synchronization, creates one
marker on startup/resume, and reports Pending review count. Assert Stop calls
`complete_session` exactly once before `sync_session_stop`, reports created or
no-op outcome plus sync status, and remains exit-zero on bounded workspace
failures.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/integration/test_experience_hooks.py \
  tests/integration/test_git_sync_hooks.py -q
```

Expected: FAIL because hooks expose synchronization only.

- [ ] **Step 3: Add Domain Core lifecycle orchestration**

After successful `sync_session_start`, establish the marker and expose Pending
count. For Stop, extract first and invoke existing managed-path synchronization
second. Keep `sync_session_stop` public and unchanged for Issue #6 callers.

- [ ] **Step 4: Update hook adapters and Skill**

Pass validated Claude Code `session_id` to Domain Core. Keep output bounded and
do not include candidate bodies or evidence paths in hook context. Add a
`review-experience` Skill that guides the user through evidence inspection,
editing, decision, and Domain Core-backed action without mentioning SOP
promotion.

- [ ] **Step 5: Run hook tests**

Run:

```bash
.venv/bin/pytest tests/integration/test_experience_hooks.py \
  tests/integration/test_git_sync_hooks.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/domain/core.py src/agent/session_start.py \
  src/agent/session_stop.py .claude/skills/review-experience/SKILL.md \
  tests/integration/test_experience_hooks.py \
  tests/integration/test_git_sync_hooks.py
git commit -m "feat(plugin): wire experience lifecycle hooks"
```

### Task 7: Build Experience Review UI

**Files:**
- Modify: `src/ui/shell.py`
- Modify: `src/ui/app.py`
- Modify: `tests/contract/test_ui_shell.py`
- Create: `tests/integration/test_experience_review_ui.py`

- [ ] **Step 1: Write failing shell and Streamlit tests**

Seed all five states, select `Experience Review`, and assert state tabs or
sections, counts, selected content, confidence, evidence roles, immutable
history, conflict/replacement relations, and reviewer metadata render. Edit a
Pending conclusion, click Approve, and assert the rerun shows Trusted while the
original history remains.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/contract/test_ui_shell.py \
  tests/integration/test_experience_review_ui.py -q
```

Expected: FAIL because Experience Review is a placeholder.

- [ ] **Step 3: Add Experience shell projection**

Add Experience groups to `ShellState`. Set module status to `Pending review`
when Pending or Conflict items exist, `Approved` when only Trusted items exist,
and `Not started` when no Experience exists.

- [ ] **Step 4: Render review controls**

Use compact tabs, a select box, text areas, numeric confidence input, evidence
table, and history table. Use clear command buttons for Approve, Reject, Mark
conflict, and Supersede. Call Domain Core, display bounded errors, and rerun on
success. Do not introduce cards, nested panels, or explanatory feature copy.

- [ ] **Step 5: Run UI tests**

Run:

```bash
.venv/bin/pytest tests/contract/test_ui_shell.py \
  tests/integration/test_experience_review_ui.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ui/shell.py src/ui/app.py \
  tests/contract/test_ui_shell.py \
  tests/integration/test_experience_review_ui.py
git commit -m "feat(ui): review governed experiences"
```

### Task 8: Complete Acceptance And Delivery

**Files:**
- Modify only if verification exposes a defect.

- [ ] **Step 1: Run all Experience-focused tests**

Run:

```bash
.venv/bin/pytest \
  tests/unit/test_experience_models.py \
  tests/integration/test_experience_repository.py \
  tests/integration/test_domain_core_experience.py \
  tests/integration/test_experience_usage_writeback.py \
  tests/integration/test_experience_hooks.py \
  tests/integration/test_experience_review_ui.py \
  tests/contract/test_ui_shell.py -q
```

Expected: PASS.

- [ ] **Step 2: Verify syntax, lock, and diff**

Run:

```bash
uv lock --check
.venv/bin/python -m compileall -q src tests
git diff --check
```

Expected: all commands exit zero.

- [ ] **Step 3: Run the full repository suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all tests pass with no regression.

- [ ] **Step 4: Perform browser acceptance**

Start Streamlit against a seeded Team Memory fixture and inspect Experience
Review at desktop and 390 x 844 mobile viewports. Verify all five states,
evidence/history tables, editing controls, long text wrapping, action feedback,
and no overlap or horizontal page overflow.

- [ ] **Step 5: Push and hand off**

Push `feat/issue-7-experience-loop`, comment the verification evidence on
GitHub Issue #7, and replace `ready-for-agent` with `ready-for-human`.
