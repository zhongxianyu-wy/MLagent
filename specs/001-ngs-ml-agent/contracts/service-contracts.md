# Service Contracts

These contracts are Python service boundaries first and frontend API boundaries later. Implementations may expose them through CLI, Streamlit, or HTTP without changing the payloads.

## ConversationService

### `start_session() -> ConversationSession`

Starts a Claude Code-like interactive shell session.

### `handle_turn(session_id: str, user_text: str) -> ConversationTurnResult`

Parses optional slash command, preserves the natural-language tail, routes the request through ask, plan, or agent mode, and returns a streaming answer handle, clarification question, validation plan, run status, or final answer.

### `classify_turn(session_id: str, user_text: str) -> RuntimeMode`

Classifies natural language without a slash command as ask, plan, or agent intent.

### `stream_ask(session_id: str, user_text: str) -> Iterator[str]`

Streams a normal LLM answer without project tool execution or experiment state mutation.

### `build_validation_plan(session_id: str, user_text: str) -> ValidationPlan`

Runs Socratic planning and creates or updates a validation plan without training execution.

### `parse_slash_command(user_text: str) -> ParsedCommand | None`

Returns command name, resolved mode, alias source, and natural-language tail. Examples: `/explore ...`, `/train_type1 ...`, `/research ...`.

### `promote_plan(session_id: str, plan_id: str) -> ExperimentRun`

Converts a ready `ValidationPlan` into an agent-mode run after explicit user confirmation.

### `list_commands() -> list[SlashCommand]`

Lists supported slash commands and aliases for `/help`.

## ModeGuardService

### `authorize(mode: RuntimeMode, service_method: str, mutation_type: str | None = None) -> SafetyDecision`

Deterministically allows or blocks a service call before LLM-proposed execution. Ask mode may only write conversation history. Plan mode may read memory summaries and create/update validation plans. Agent mode must still pass command and path safety hooks.

## HarnessRegistryService

### `load_seed_config(path: str = "config/harnesses.toml") -> list[FunctionalHarness]`

Loads default command and alias mappings such as `/train_type1`.

### `resolve(command: str) -> FunctionalHarness`

Returns the active harness for an explicit slash command or alias. This method never falls back to free-form intent classification.

## HTTP/SSE API Shape

Recommended frontend-facing routes:

- `POST /api/conversations` → start session
- `POST /api/conversations/{session_id}/turns` → submit ask/plan/agent turn
- `GET /api/conversations/{session_id}/stream` → SSE stream for tokens, clarifications, and progress
- `GET /api/datasets/{dataset_id}` → dataset manifest
- `POST /api/runs` → start run from request or promoted plan
- `GET /api/runs/{experiment_id}` → run status
- `GET /api/runs/{experiment_id}/rounds` → round traces
- `POST /api/runs/{experiment_id}/stop` → stop run
- `GET /api/memory/search?q=...` → semantic memory search
- `POST /api/skills/{skill_id}/optimize` → start `/skill_opt`
- `GET /api/skill-optimizations/{job_id}` → optimization report/status
- `POST /api/skill-optimizations/{job_id}/approve` → publish optimized Skill
- `GET /api/research/{job_id}` → research job status/artifacts

## DatasetService

### `inspect_path(path: str) -> IntakeInspection`

Returns candidate feature files, label files, split files, notebook files, confidence scores, and unresolved questions.

### `answer_clarification(session_id: str, answer: str) -> IntakeInspection`

Records one Socratic answer and returns the next unresolved question or ready-to-build state.

### `build_manifest(session_id: str) -> DatasetManifest`

Creates standardized train/test feature and label files plus manifest.

## RunService

### `start_run(request: RunRequest) -> ExperimentRun`

Starts exploration, reproduction, interactive validation, distillation, or research.

### `get_status(experiment_id: str) -> RunStatus`

Returns run state, current round, stop reason, best metric, and progress.

### `list_rounds(experiment_id: str) -> list[ExperimentRoundTrace]`

Returns frontend-ready round trace rows.

### `stop_run(experiment_id: str, reason: str) -> RunStatus`

Requests user stop and records stop reason.

## ExplorationToolService

### `list_available_tools(dataset_id: str, objective: str) -> list[ExplorationTool]`

Returns ranked exploration tool candidates such as AIDE tree search, memory-guided search, manual plan execution, or Skill-seeded search.

### `propose_round(tool_id: str, request: ExplorationToolRequest) -> ExplorationToolResult`

Runs a bounded tool proposal with timeout and returns either a trace-ready proposal or a structured failure reason for fallback.

## MemoryService

### `search(query: str, top_k: int = 5) -> list[MemoryEntry]`

Searches semantic memory and returns entries with metadata from the SQLite metadata index.

### `add_experience(round_id: str, summary: str, confidence: str) -> MemoryEntry`

Adds a reviewed or system-generated experiment summary to semantic memory and links it to the originating round.

### `get_related_context(dataset_id: str, objective: str, top_k: int = 5) -> list[MemoryEntry]`

Returns experience and Skill context for autonomous exploration planning.

### `link_memory_to_skill(memory_id: str, candidate_id: str) -> None`

Creates a bridge record between semantic knowledge and a SkillCandidate.

## SkillService

### `list_skills() -> list[ApprovedSkill]`

Lists approved Skills and metadata.

### `create_candidate_from_notebook(path: str) -> SkillCandidate`

Parses a notebook into a candidate following `skill-creator` structure.

### `create_candidate_from_best_run(experiment_id: str) -> SkillCandidate`

Creates a candidate from the best trace and linked memory evidence.

### `iterate_candidate(candidate_id: str) -> SkillCandidate`

Runs skill-creator validation and darwin-skill-style evaluate-improve-test-keep/revert.

### `approve_candidate(candidate_id: str) -> ApprovedSkill`

Publishes a human-approved candidate to `.claude/skills/<skill-name>/SKILL.md`.

### `optimize_skill(skill_id: str, dataset_id: str | None = None, repeat_count: int = 3, max_runtime_minutes: int = 60, selection_metric: str = "auc") -> SkillOptimizationJob`

Backs up the current Skill, confirms dataset approval when needed, proposes an optimized candidate, runs old/new parallel modeling tests within budget, uses training k-fold metrics for candidate selection, and returns a pending review job.

### `approve_skill_optimization(skill_opt_job_id: str) -> ApprovedSkill`

Replaces the approved Skill only after user approval.

## DreamService

### `maybe_start_idle_dream(now: int) -> DreamJob | None`

Starts memory maintenance only when idle for more than 2 hours, no run is active, no Skill optimization job is active, and an exclusive idle lease can be acquired.

### `run_dream_job(dream_job_id: str) -> DreamJob`

Deduplicates, summarizes, and reviews memory entries without modifying approved Skills.

## IdleSchedulerService

### `acquire_lease(lease_type: str, owner_id: str, ttl_seconds: int) -> IdleSchedulerLease | None`

Acquires an exclusive background-job lease or returns `None` if another active owner holds it.

### `heartbeat(lease_id: str, now: int) -> IdleSchedulerLease`

Refreshes an active lease while the owner is still running.

### `release(lease_id: str, status: str) -> IdleSchedulerLease`

Releases or expires the lease without deleting the audit record.

## ResearchService

### `research_target(target: str) -> ResearchJob`

Uses muyu-search-mcp to research a paper, project, or URL.

### `research_recent(topic: str, months: int = 6) -> ResearchJob`

Uses muyu-search-mcp planning flow to research recent methods.

### `ingest_research(job_id: str) -> list[ResearchArtifact]`

Stores method summaries and source metadata in semantic memory.

## ProviderService

### `load_provider_config(path: str | None = None) -> LLMProviderConfig`

Loads Anthropic-compatible model settings.

### `complete_control_step(messages: list[dict], tools: list[dict]) -> LLMResponse`

Performs one control-center LLM step. It may propose actions, but it cannot write metrics directly.

## SafetyService

### `validate_command(command: str, intent: str | None = None) -> SafetyDecision`

Blocks destructive or out-of-scope commands before local execution.

### `validate_write_path(path: str) -> SafetyDecision`

Allows writes only under approved project output directories unless explicitly approved by the user.

## TrackingService

### `log_round(round_id: str) -> None`

Reads deterministic round trace data from SQLite and writes params, metrics, tags, and artifacts to local MLflow tracking.

## Streamlit Readiness Review

The service layer is ready for a Streamlit MVP as long as the UI treats `frontend_api/` as the only integration boundary. Streamlit may use direct Python service calls for the local desktop workflow, while the same payloads can later be exposed through HTTP/SSE without changing frontend state models.

- `ConversationService` owns chat sessions, ask-mode streaming, slash-command parsing, Socratic plan turns, and plan-to-agent promotion.
- `DatasetService` owns path inspection, clarification answers, and standardized manifest creation.
- `RunService` owns agent-mode run creation, status polling, round traces, and user stop requests.
- `MemoryService` owns semantic search, related context retrieval, and memory-to-Skill linkage.
- `SkillService` owns approved Skill listing, candidate creation, darwin-style iteration, approval, and `/skill_opt` jobs.
- `ResearchService` owns target and recent-method research jobs plus knowledge ingestion.

Streamlit views should render the same event and status shapes that the HTTP/SSE layer exposes: conversation tokens, clarification prompts, run progress, round trace rows, optimization reports, and research artifacts. The UI must not call AIDE, MLflow, ChromaDB, or local file adapters directly; those remain behind service contracts so later web frontends and local Streamlit screens share the same behavior and safety gates.
