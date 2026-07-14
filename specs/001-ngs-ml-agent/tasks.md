# Tasks: NGS ML Experiment Agent

**Input**: Design documents from `/specs/001-ngs-ml-agent/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Core contract and integration tests are included because evaluation integrity, data intake, memory linking, and Skill publishing are high-risk.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested independently after the foundational phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: User story label from [spec.md](./spec.md).
- Every task includes an exact file path.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the Python project structure and test harness.

- [x] T001 Create project package directories in `src/` and test directories in `tests/`
- [x] T002 Create `pyproject.toml` with Python 3.11, pytest, pandas, numpy, scikit-learn, xgboost, mem0ai, chromadb, mlflow, nbformat, and optional streamlit dependencies
- [x] T003 Create `.env.example` with Anthropic-compatible provider, MLflow, ChromaDB, and SQLite settings
- [x] T004 Create `.gitignore` entries for `.env`, `db/`, `experiments/data/`, `experiments/standardized/`, `experiments/models/`, `experiments/outputs/`, and `db/chroma/`
- [x] T005 [P] Create shared test fixtures directory `tests/fixtures/` with placeholder README in `tests/fixtures/README.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build cross-story contracts that all modes depend on.

**Critical**: No user story work should start until this phase is complete.

- [x] T006 [P] Implement `DatasetManifest`, `RunControlPolicy`, `EvaluationConfig`, `ExperimentRun`, `ExperimentRoundTrace`, `MemoryEntry`, `SkillCandidate`, `ApprovedSkill`, `ResearchArtifact`, `LLMProviderConfig`, `SafetyDecision`, and `TrackingRecord` models in `src/models.py`
- [x] T007 Implement initial SQLite schema initialization for foundation storage contracts in `src/memory/episodic.py`
- [x] T008 [P] Implement Anthropic-compatible provider config loader in `src/provider/config.py`
- [x] T009 Implement Anthropic-compatible provider client wrapper in `src/provider/client.py`
- [x] T010 [P] Implement deterministic metric functions in `src/evaluation/metrics.py`
- [x] T011 [P] Implement threshold selection from k-fold validation predictions in `src/evaluation/threshold.py`
- [x] T012 Implement k-fold evaluation orchestration in `src/evaluation/cv.py`
- [x] T013 Implement run control stop-condition evaluator in `src/agent/run_control.py`
- [x] T014 Implement frontend-facing run trace repository methods in `src/memory/episodic.py`
- [x] T015 [P] Add contract tests for provider config and model validation in `tests/contract/test_foundation_contracts.py`
- [x] T016 Add integration tests proving thresholds do not use test-set predictions in `tests/integration/test_threshold_no_test_leakage.py`
- [x] T017 Add storage contract tests for conversation sessions, validation plans, harnesses, mode policies, exploration tools, dream jobs, idle leases, and skill optimization jobs in `tests/contract/test_storage_contracts.py`
- [x] T018 Extend SQLite schema initialization for expanded runtime storage contracts in `src/memory/episodic.py`

**Checkpoint**: Foundation ready. All stories can use standard models, storage, provider config, evaluation, and run control.

---

## Phase 2b: Foundational Supplements From Design Review

**Purpose**: Close the previously identified gaps around memory, Skill linkage, safety, tracking, and AIDE isolation before story implementation.

**Critical**: Execute these immediately after expanded storage is green. They are blocking prerequisites for US2-US6.

- [x] T019 [P] Add contract tests for semantic memory metadata preservation in `tests/contract/test_semantic_memory_contract.py`
- [x] T020 [P] Add contract tests for safety hook command/path decisions in `tests/contract/test_safety_hooks.py`
- [x] T021 [P] Add contract tests for MLflow tracking bridge in `tests/contract/test_tracking_service.py`
- [x] T022 [P] Add contract tests for AIDE adapter isolation in `tests/contract/test_aide_adapter_contract.py`
- [x] T023 Implement metadata index persistence in `src/memory/metadata_index.py`
- [x] T024 Implement insert-only semantic memory adapter in `src/memory/semantic.py`
- [x] T025 Implement `MemoryService.search`, `add_experience`, and `get_related_context` in `src/frontend_api/memory_service.py`
- [x] T026 Implement command and write-path safety hooks in `src/agent/hooks.py`
- [x] T027 Implement local MLflow tracking bridge in `src/tracking/mlflow_tracker.py`
- [x] T028 Implement AIDE provider routing adapter in `src/aide_adapter/routing.py`
- [x] T029 Implement AIDE journal-to-trace bridge in `src/aide_adapter/journal_bridge.py`
- [x] T030 Add integration test for memory-to-Skill evidence linkage in `tests/integration/test_memory_skill_linkage.py`
- [x] T031 Add integration test that blocked commands never reach the training runner in `tests/integration/test_safety_runner_gate.py`
- [x] T032 Add integration test that a completed round logs SQLite trace and tracking record in `tests/integration/test_round_trace_tracking.py`

---

## Phase 2c: Conversational CLI Runtime (Blocking User-Facing Entry)

**Purpose**: Make the default CLI a Claude Code-like LLM runtime with ask, plan, agent, mode guards, slash commands, functional harnesses, and plan promotion. This is the last blocking layer before US1.

- [x] T033 [P] Add contract tests for slash command parsing and alias mapping in `tests/contract/test_slash_commands.py`
- [x] T034 [P] Add contract tests for conversation session state in `tests/contract/test_conversation_service.py`
- [x] T035 [P] Add contract tests for ask/plan/agent runtime mode classification in `tests/contract/test_runtime_modes.py`
- [x] T036 [P] Add contract tests for mode capability guard blocking forbidden service calls in `tests/contract/test_mode_guard.py`
- [x] T037 [P] Add contract tests for configured functional harness routing from `config/harnesses.toml` in `tests/contract/test_functional_harnesses.py`
- [x] T038 [P] Add contract tests for plan promotion to agent run in `tests/contract/test_plan_promotion.py`
- [x] T039 Add integration test that ask mode streams an answer without tool calls in `tests/integration/test_ask_mode_streaming.py`
- [x] T040 Add integration test that plan mode asks Socratic questions, may read memory summaries, and creates a `ValidationPlan` without execution in `tests/integration/test_plan_mode_socratic.py`
- [x] T041 Add integration test that no-argument CLI starts interactive shell in `tests/integration/test_cli_interactive_entry.py`
- [x] T042 Add integration test that `/train_type1` routes to agent exploration with natural-language tail preserved in `tests/integration/test_train_type1_routing.py`
- [x] T043 Create default functional harness seed config in `config/harnesses.toml`
- [x] T044 Implement slash command registry, parser, and harness seed loading in `src/agent/slash_commands.py`
- [x] T045 Implement runtime mode classification and constraints in `src/agent/modes.py`
- [x] T046 Implement deterministic mode capability guard in `src/agent/mode_guard.py`
- [x] T047 Implement conversation session and turn state in `src/agent/dialogue.py`
- [x] T048 Implement interactive chat shell loop in `src/agent/chat_shell.py`
- [x] T049 Implement `ConversationService.start_session`, `handle_turn`, `classify_turn`, `stream_ask`, `build_validation_plan`, `parse_slash_command`, and `list_commands` in `src/frontend_api/conversation_service.py`
- [x] T050 Implement `ConversationService.promote_plan` in `src/frontend_api/conversation_service.py`
- [x] T051 Update `src/agent/main.py` so no-argument CLI opens chat shell and explicit subcommands remain available for automation

---

## Phase 2d: Advanced Runtime Services (Non-Blocking Enhancements)

**Purpose**: Add frontend HTTP streaming, idle dream maintenance, Skill self-optimization, and AIDE exploration-tool integration. These improve the complete product but do not block US1 data intake or the first US2 exploration MVP when mocked.

- [x] T052 Add API route contract tests for REST/SSE frontend integration in `tests/contract/test_http_api_contract.py`
- [x] T053 Implement REST/SSE API skeleton in `src/api/app.py`, `src/api/routes.py`, and `src/api/schemas.py`
- [x] T054 Add contract tests for idle scheduler lease acquisition, heartbeat, expiration, and release in `tests/contract/test_idle_scheduler.py`
- [x] T055 Implement idle scheduler and exclusive lease repository in `src/scheduler/idle.py` and `src/scheduler/lease.py`
- [x] T056 Add contract tests for dream idle trigger and memory-only scope in `tests/contract/test_dream_service.py`
- [x] T057 Implement dream memory maintenance service in `src/memory/dream.py`
- [x] T058 Add contract tests for `/skill_opt` backup, budget, dataset approval, no-test-selection, and old/new comparison workflow in `tests/contract/test_skill_optimization.py`
- [x] T059 Implement Skill optimization workflow in `src/skill_bridge/optimizer.py`
- [x] T060 Add contract tests for bounded `ExplorationTool` timeout and fallback behavior in `tests/contract/test_exploration_tool_contract.py`
- [x] T061 Implement exploration tool interface and fallback orchestrator in `src/exploration_tools/base.py` and `src/exploration_tools/orchestrator.py`
- [x] T062 Add integration test for AIDE as bounded exploration tool candidate in `tests/integration/test_aide_exploration_tool.py`

---

## Phase 3: User Story 1 - Standardize Input Data (Priority: P1) MVP

**Goal**: Inspect user paths, clarify ambiguous data conventions, and produce `DatasetManifest`.

**Independent Test**: Run intake against fixture feature/label files and verify manifest plus standardized files are produced.

### Tests for User Story 1

- [x] T063 [P] [US1] Add fixture feature and label files in `tests/fixtures/data_intake/`
- [x] T064 [P] [US1] Add contract tests for `DatasetService` in `tests/contract/test_dataset_service.py`
- [x] T065 [US1] Add integration test for ambiguous intake Socratic clarification in `tests/integration/test_data_intake_socratic.py`

### Implementation for User Story 1

- [x] T066 [P] [US1] Implement path/file inspection in `src/data_intake/explorer.py`
- [x] T067 [P] [US1] Implement Socratic clarification session state in `src/data_intake/socratic.py`
- [x] T068 [P] [US1] Implement manifest builder and validation in `src/data_intake/manifest.py`
- [x] T069 [P] [US1] Implement reproducible train/test splitter in `src/data_intake/splitter.py`
- [x] T070 [US1] Implement `DatasetService` in `src/frontend_api/dataset_service.py`
- [x] T071 [US1] Add `intake` CLI command in `src/agent/main.py`

**Checkpoint**: User Story 1 is independently usable and produces standard training input.

---

## Phase 4: User Story 2 - Explore Feature Engineering Directions (Priority: P1)

**Goal**: Run autonomous feature exploration with memory/Skill context, deterministic evaluation, and per-round frontend traces.

**Independent Test**: Run 10 mocked rounds and verify trace completeness, stop conditions, and best metric selection.

### Tests for User Story 2

- [x] T072 [P] [US2] Add contract tests for `RunService` exploration methods in `tests/contract/test_run_service_exploration.py`
- [x] T073 [P] [US2] Add integration test for 10-round exploration trace completeness in `tests/integration/test_exploration_traces.py`
- [x] T074 [US2] Add integration test for target/max-iteration/runtime/patience stop reasons in `tests/integration/test_run_control_stop_reasons.py`

### Implementation for User Story 2

- [x] T075 [P] [US2] Implement preprocessing strategy planner primitives in `src/training/preprocessing.py`
- [x] T076 [P] [US2] Implement feature subset strategy primitives in `src/training/feature_selection.py`
- [x] T077 [P] [US2] Implement training subprocess runner in `src/training/runner.py`
- [x] T078 [P] [US2] Implement XGBoost training script in `src/training/scripts/train_xgboost.py`
- [x] T079 [P] [US2] Implement sklearn training script in `src/training/scripts/train_sklearn.py`
- [x] T080 [US2] Implement memory and Skill context retrieval before exploration in `src/agent/control_center.py`
- [x] T081 [US2] Implement exploration harness and round trace writing in `src/agent/harness.py`
- [x] T082 [US2] Implement `RunService.start_run`, `get_status`, `list_rounds`, and `stop_run` in `src/frontend_api/run_service.py`
- [x] T083 [US2] Add `explore` CLI command in `src/agent/main.py`

**Checkpoint**: User Story 2 delivers the autonomous MVP exploration loop.

---

## Phase 5: User Story 3 - Reproduce a Skill Strictly (Priority: P2)

**Goal**: Execute an approved Skill on a standardized dataset without exploratory changes.

**Independent Test**: Reproduce a fixture Skill and verify adaptation limits, metrics, model output, and memory writeback.

### Tests for User Story 3

- [x] T084 [P] [US3] Add fixture approved Skill in `tests/fixtures/skills/ngs-xgboost-baseline/SKILL.md`
- [x] T085 [P] [US3] Add contract tests for Skill listing and strict reproduction in `tests/contract/test_skill_reproduction.py`
- [x] T086 [US3] Add integration test for missing-feature strict failure in `tests/integration/test_skill_strict_reproduction.py`

### Implementation for User Story 3

- [x] T087 [P] [US3] Implement approved Skill registry reads in `src/skill_bridge/registry.py`
- [x] T088 [US3] Implement strict Skill execution adapter in `src/agent/harness.py`
- [x] T089 [US3] Implement Skill execution writeback to SQLite, semantic memory, and registry in `src/memory/skill_linker.py`
- [x] T090 [US3] Implement Skill listing and reproduction entrypoints in `src/frontend_api/skill_service.py`
- [x] T091 [US3] Add `reproduce` CLI command in `src/agent/main.py`

**Checkpoint**: User Story 3 can run independently after standard data intake.

---

## Phase 6: User Story 4 - Interactively Validate User Directions (Priority: P2)

**Goal**: Execute one user-directed validation at a time, return results, and pause.

**Independent Test**: Submit one validation instruction and verify exactly one direction runs and the experiment pauses.

### Tests for User Story 4

- [x] T092 [P] [US4] Add contract tests for interactive validation requests in `tests/contract/test_interactive_validation.py`
- [x] T093 [US4] Add integration test that interactive validation pauses after one result in `tests/integration/test_interactive_pause.py`

### Implementation for User Story 4

- [x] T094 [US4] Implement user instruction to experiment direction conversion in `src/agent/control_center.py`
- [x] T095 [US4] Implement paused-run state transitions in `src/frontend_api/run_service.py`
- [x] T096 [US4] Add `interact` CLI command in `src/agent/main.py`

**Checkpoint**: User Story 4 supports controlled researcher-in-the-loop validation.

---

## Phase 7: User Story 5 - Distill Skills from Notebooks or Runs (Priority: P3)

**Goal**: Generate SkillCandidates from notebooks or best runs, validate them, iterate them, and require human approval.

**Independent Test**: Distill from a fixture notebook and from a best run trace; verify candidate lifecycle and no automatic publication.

### Tests for User Story 5

- [x] T097 [P] [US5] Add fixture notebook in `tests/fixtures/notebooks/skill_source.ipynb`
- [x] T098 [P] [US5] Add contract tests for SkillCandidate lifecycle in `tests/contract/test_skill_candidate_lifecycle.py`
- [x] T099 [US5] Add integration test that unapproved SkillCandidate is not published in `tests/integration/test_skill_candidate_review_gate.py`

### Implementation for User Story 5

- [x] T100 [P] [US5] Implement SkillCandidate model persistence in `src/skill_bridge/candidate.py`
- [x] T101 [P] [US5] Implement notebook-to-SkillCandidate generation in `src/skill_bridge/generator.py`
- [x] T102 [US5] Implement best-run-to-SkillCandidate generation in `src/skill_bridge/generator.py`
- [x] T103 [US5] Implement skill-creator structural validation in `src/skill_bridge/generator.py`
- [x] T104 [US5] Implement darwin-skill evaluate/improve/test/keep-or-revert adapter in `src/skill_bridge/darwin_adapter.py`
- [x] T105 [US5] Implement human approval publishing in `src/skill_bridge/registry.py`
- [x] T106 [US5] Implement SkillCandidate service methods in `src/frontend_api/skill_service.py`
- [x] T107 [US5] Add `distill` CLI command in `src/agent/main.py`

**Checkpoint**: User Story 5 converts experience into reviewable executable knowledge.

---

## Phase 8: User Story 6 - Ingest Literature and Project Knowledge (Priority: P3)

**Goal**: Research external papers/projects using local muyu-search-mcp and ingest structured knowledge into semantic memory.

**Independent Test**: Research a fixture target using mocked muyu-search responses and verify searchable ResearchArtifacts.

### Tests for User Story 6

- [x] T108 [P] [US6] Add contract tests for `ResearchService` in `tests/contract/test_research_service.py`
- [x] T109 [US6] Add integration test for research artifact ingestion with mocked muyu-search-mcp in `tests/integration/test_research_ingestion.py`

### Implementation for User Story 6

- [x] T110 [P] [US6] Implement muyu-search-mcp client wrapper in `src/research/muyu_client.py`
- [x] T111 [US6] Implement target paper/project research extraction in `src/research/knowledge_ingest.py`
- [x] T112 [US6] Implement recent-method automatic research mode in `src/research/knowledge_ingest.py`
- [x] T113 [US6] Implement research service methods in `src/frontend_api/research_service.py`
- [x] T114 [US6] Add `research` CLI command in `src/agent/main.py`

**Checkpoint**: User Story 6 enriches knowledge without publishing unvalidated Skills.

---

## Final Phase: Polish & Cross-Cutting Concerns

- [x] T115 [P] Update root `specs/plan.md` to point to canonical Spec Kit plan in `specs/001-ngs-ml-agent/plan.md`
- [x] T116 [P] Update root `specs/tasks.md` to point to canonical Spec Kit tasks in `specs/001-ngs-ml-agent/tasks.md`
- [x] T117 [P] Add quickstart validation test in `tests/integration/test_quickstart_paths.py`
- [X] T118 Run `uv run pytest tests/ --cov=src --cov-report=term-missing` and fix failures
- [X] T119 Review frontend service contracts for Streamlit readiness in `specs/001-ngs-ml-agent/contracts/service-contracts.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2 + 2b + 2c)**: Depends on Setup and blocks all user stories. Phase 2b closes memory/safety/tracking gaps; Phase 2c establishes the required conversational LLM entry, mode guard, harness registry, and plan promotion.
- **Advanced runtime services (Phase 2d)**: Depends on Phase 2 + 2b + 2c where applicable, but does not block US1 and may run in parallel with US1/US2 MVP once the core conversational shell is stable.
- **US1 Data Standardization (Phase 3)**: Depends on Foundational and conversational shell routing.
- **US2 Exploration (Phase 4)**: Depends on Foundational, Phase 2b, Phase 2c harness routing, and US1. AIDE-backed exploration can wait for Phase 2d; memory-guided or mocked tools are enough for the MVP loop.
- **US3 Reproduction (Phase 5)**: Depends on Foundational, Phase 2b, and US1.
- **US4 Interactive Validation (Phase 6)**: Depends on US2 harness and run service.
- **US5 Skill Distillation (Phase 7)**: Depends on US2 traces and memory contracts; can run after US2.
- **US6 Research Ingestion (Phase 8)**: Depends on Foundational and Phase 2b semantic memory contracts; can run after Phase 2b with mocked search, but full value comes after US2/US5.
- **Polish**: Depends on selected user stories.

### User Story Dependencies

- **US1 (P1)**: Independent MVP data intake.
- **US2 (P1)**: Requires US1 manifest and foundational evaluation/storage.
- **US3 (P2)**: Requires US1 manifest and approved Skill fixture.
- **US4 (P2)**: Requires US2 run harness.
- **US5 (P3)**: Requires traces from US2 or notebook fixture.
- **US6 (P3)**: Independent research ingestion after memory foundation.

### Parallel Opportunities

- T005, T008, T010, T011, T015 can run in parallel after setup starts.
- T033-T038 can run in parallel within Phase 2c test definition.
- T052-T062 can run after Phase 2c and may proceed in parallel with US1/US2 when they touch independent API, scheduler, dream, skill optimization, or exploration-tool files.
- T066-T069 can run in parallel within US1.
- T075-T079 can run in parallel within US2.
- US3 and US6 can proceed in parallel after US1 and foundational storage are complete.
- T100 and T101 can run in parallel in US5 before lifecycle integration.

## Parallel Example: User Story 2

```bash
# Can be split across workers after foundational phase:
Task: "Implement preprocessing strategy planner primitives in src/training/preprocessing.py"
Task: "Implement feature subset strategy primitives in src/training/feature_selection.py"
Task: "Implement XGBoost training script in src/training/scripts/train_xgboost.py"
Task: "Implement sklearn training script in src/training/scripts/train_sklearn.py"
```

## Implementation Strategy

### TDD Execution Rule

For every implementation task, follow Superpowers TDD strictly:

1. Write or extend the named contract/integration/unit test first.
2. Run the narrow test and confirm it fails for the expected reason.
3. Implement the minimum production code needed to pass.
4. Re-run the narrow test and then the relevant story test set.
5. Refactor only after green.

No production code task may start unless its failing test has been observed in the current session.

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete Phase 2b design-review supplements.
3. Complete Phase 2c conversational runtime, mode guard, harness registry, and plan promotion.
4. Complete US1 data standardization.
5. Complete US2 exploration with mocked trainer first, then real local scripts.
6. Add Phase 2d services as soon as their tests are needed by UI, dream, skill optimization, or AIDE-backed exploration.
7. Validate with the interactive shell tests, 10-round fixture, safety gate tests, tracking tests, memory linkage tests, and threshold leakage test.

### Incremental Delivery

1. Deliver US1 so users can standardize messy inputs.
2. Deliver US2 so the system performs autonomous feature exploration.
3. Add US3 strict Skill reproduction.
4. Add US4 interactive validation.
5. Add US5 Skill distillation.
6. Add US6 research ingestion.

### Validation Gates

- Do not start autonomous exploration without a valid `DatasetManifest`.
- Do not use test predictions for threshold selection.
- Do not publish a Skill without skill-creator validation, darwin-skill iteration, and human approval.
- Do not expose frontend views directly to AIDE internals; use `frontend_api/` services.
- Do not execute LLM-proposed local commands without passing `src/agent/hooks.py`.
- Do not treat MLflow as frontend state; SQLite trace records remain the UI source of truth.
- Do not make argparse subcommands the primary user experience; no-argument CLI must enter the LLM conversation shell.
- Do not allow ask mode to call tools or mutate experiment state.
- Do not allow plan mode to launch training or write model artifacts; it may only create/update `ValidationPlan`.
- Do not allow agent mode to execute until clarification and safety gates pass.
- Do not start a dream job unless an idle scheduler lease is held.
- Do not select a `/skill_opt` candidate with test-set predictions or labels; test metrics are report-only after selection.
- Do not rely on prompt-only intent inference for explicit functional slash command routing; use the harness registry.
