# MLagent MVP Task Handoff

Date: 2026-06-22

This handoff decomposes the implementation plan into task cards for a future development agent. The development agent should not infer architecture from scratch. It must implement against the approved specs and the full plan.

## Authoritative Inputs

Primary implementation plan:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`

Design and audit specs:

- `docs/superpowers/specs/2026-06-22-mlagent-claude-code-plugin-design.md`
- `docs/superpowers/specs/2026-06-22-mlagent-research-fit-evaluation.md`

Research background:

- `docs/research/README.md`
- `docs/research/2026-06-22-m1-agent-memory-systems.md`
- `docs/research/2026-06-22-m2-knowledge-ingestion.md`
- `docs/research/2026-06-22-m3-sqlite-fts5-index.md`
- `docs/research/2026-06-22-m4-claude-code-plugin.md`
- `docs/research/2026-06-22-m5-context-packs.md`
- `docs/research/2026-06-22-m6-skillversion-registry.md`
- `docs/superpowers/reports/2026-06-22-mlagent-reuse-survey.md`

## Non-Negotiable Boundaries

- Do not build a model training framework.
- Do not build a parameter optimizer.
- Do not add MLflow, DVC, Optuna, workflow orchestrators, vector databases, graph databases, or model registry servers.
- Do not import memory runtimes such as mem0, Letta, cognee, Graphiti, or LangMem.
- Do not use PyMuPDF as a default dependency.
- Do not make sqlite-vec, RRF, or hybrid retrieval part of MVP.
- Do not let Claude Code automatically approve formal SkillVersions.
- Do not record full logs, full diffs, training data, or model binaries by default.
- Keep durable assets human-readable and portable.
- Keep `indexes/` rebuildable and never the only source of truth.

## Execution Mode

The future development agent should implement one task at a time.

Recommended execution:

1. Start a clean implementation branch or worktree.
2. Open the full plan.
3. Implement Task 1 exactly.
4. Run the task-specific verification.
5. Commit.
6. Repeat for the next task.
7. After every task, ask the reviewer to inspect the diff if policy requires review.

Required sub-skill for implementation:

- `superpowers:subagent-driven-development`, or
- `superpowers:executing-plans`

This handoff is not a replacement for the full plan. The full plan contains exact test code, implementation snippets, commands, and expected outputs.

## Global Architecture

Package:

```text
mlagent_memory/
```

CLI:

```text
bin/mlagent-memory
```

Plugin shell:

```text
.claude-plugin/
skills/
hooks/
```

Project memory repo created by the tool:

```text
project_memory/
  project_profile/
  data_understanding/
  project_knowledge/
  raw_memory/
  experience/
  skill_versions/
  indexes/
```

Runtime stack:

```text
Python 3.10+
Typer
Pydantic v2
PyYAML
pypdf
langchain-text-splitters
sqlite-utils
pytest
SQLite FTS5
```

## Dependency Graph

```text
Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5
                              -> Task 6 -> Task 7 -> Task 8
Task 9 depends on Task 1 CLI naming and approved architecture
Task 10 depends on Task 1 CLI/package and should happen after Task 6
Task 11 depends on Tasks 1-10
```

Strict order recommended:

```text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
```

Reason: hooks and skills should not be added before storage, schema, and CLI paths exist.

## Task Cards

### Task 1: Python Package and CLI Skeleton

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 1`

Purpose:

- Create the Python package, Typer CLI, version command, status error path, and executable wrapper.

Creates:

- `pyproject.toml`
- `mlagent_memory/__init__.py`
- `mlagent_memory/constants.py`
- `mlagent_memory/errors.py`
- `mlagent_memory/cli.py`
- `bin/mlagent-memory`
- `tests/test_cli.py`

Key contract:

- `mlagent-memory version` prints `mlagent-memory 0.1.0`.
- `status` exits with code `2` and a clear message when `project_memory/` does not exist.

Verification:

```bash
python -m pytest tests/test_cli.py -q
```

Expected:

```text
2 passed
```

Commit:

```bash
git commit -m "feat: add mlagent memory cli skeleton"
```

Review focus:

- CLI user-facing failures are clean.
- `bin/mlagent-memory` imports the package rather than duplicating logic.
- No implementation beyond skeleton is added.

### Task 2: Schemas and YAML I/O

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 2`

Purpose:

- Add YAML read/write helpers, SHA-256 helper, and Pydantic schemas.

Creates:

- `mlagent_memory/io.py`
- `mlagent_memory/schemas.py`
- `tests/test_schemas.py`

Key contract:

- `RawMemoryRecord` accepts only known raw memory types.
- `ExperienceRecord` carries `confidence`, `needs_review`, and source records.
- `SkillVersion(state="approved")` is invalid unless `human_review.reviewed=true`.
- YAML round-trip preserves dict data.

Verification:

```bash
python -m pytest tests/test_schemas.py -q
```

Expected:

```text
4 passed
```

Commit:

```bash
git commit -m "feat: add memory schemas and yaml io"
```

Review focus:

- Approved SkillVersion gate is enforced in schema.
- No direct dependency on MLEM/modelstore runtimes.
- YAML root validation rejects non-mapping data.

### Task 3: Project Memory Repo Init and Status

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 3`

Purpose:

- Create standard `project_memory/` structure and status reporting.

Creates:

- `mlagent_memory/repo.py`
- `tests/test_repo.py`

Modifies:

- `mlagent_memory/cli.py`
- `tests/test_cli.py`

Key contract:

- `init` creates the full approved memory directory tree.
- `project_profile/project.yaml` records project name and primary metric.
- `skill_versions/registry.yaml` exists with empty `versions`.
- `status` reports asset counts.

Verification:

```bash
python -m pytest tests/test_repo.py tests/test_cli.py -q
```

Expected:

```text
5 passed
```

Commit:

```bash
git commit -m "feat: initialize project memory repos"
```

Review focus:

- Directory names exactly match the approved spec.
- No hidden database becomes the source of truth.
- Status does not require indexing.

### Task 4: SQLite FTS5 Index and Search

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 4`

Purpose:

- Add rebuildable SQLite FTS5 indexing and search.

Creates:

- `mlagent_memory/index.py`
- `tests/test_index.py`

Modifies:

- `mlagent_memory/cli.py`

Key contract:

- `rebuild_index(root)` deletes/rebuilds `indexes/memory.sqlite`.
- Indexed records always point back to durable source paths.
- Search supports asset type filtering.
- FTS5 availability is detected.

Verification:

```bash
python -m pytest tests/test_index.py -q
python -m pytest -q
```

Expected:

```text
all current tests passed
```

Commit:

```bash
git commit -m "feat: add sqlite fts memory index"
```

Review focus:

- `indexes/` is rebuildable.
- No vector search is added.
- Index rows contain source path and asset type.

### Task 5: Knowledge Import

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 5`

Purpose:

- Import TXT, Markdown, and basic PDF files into `project_knowledge/`.

Creates:

- `mlagent_memory/knowledge.py`
- `tests/test_knowledge.py`

Modifies:

- `mlagent_memory/index.py`
- `mlagent_memory/cli.py`

Key contract:

- Imported originals are copied into `project_knowledge/originals/`.
- `registry.yaml` records imported knowledge items.
- Notes are generated into `project_knowledge/notes/`.
- Unsupported file suffixes fail clearly.

Verification:

```bash
python -m pytest tests/test_knowledge.py -q
```

Expected:

```text
2 passed
```

Commit:

```bash
git commit -m "feat: import project knowledge files"
```

Review focus:

- Do not use PyMuPDF.
- Do not add OCR or heavyweight PDF parsing.
- pypdf extraction is accepted as basic PDF support only.
- Original file copy and hash are present.

### Task 6: Raw Memory and Experience Records

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 6`

Purpose:

- Write schema-checked raw memory and experience YAML records.

Creates:

- `mlagent_memory/raw.py`
- `mlagent_memory/experience.py`
- `tests/test_raw_experience.py`

Modifies:

- `mlagent_memory/cli.py`

Key contract:

- Raw records route by type:
  - `session -> raw_memory/sessions`
  - `exploration -> raw_memory/explorations`
  - `run -> raw_memory/runs`
  - `human_note -> raw_memory/human_notes`
- Experience records route by type:
  - `lesson -> experience/lessons`
  - `pitfall -> experience/pitfalls`
  - `successful_pattern -> experience/successful_patterns`
  - `failed_direction -> experience/failed_directions`

Verification:

```bash
python -m pytest tests/test_raw_experience.py -q
```

Expected:

```text
2 passed
```

Commit:

```bash
git commit -m "feat: add raw memory and experience records"
```

Review focus:

- Experience cannot be written without source records.
- Experience remains exploration guidance, not retraining procedure.
- No hook automation is added yet.

### Task 7: Context Pack Generation

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 7`

Purpose:

- Generate task-specific Context Packs using approved priority rules.

Creates:

- `mlagent_memory/context.py`
- `tests/test_context.py`

Modifies:

- `mlagent_memory/cli.py`

Key contract:

- Exploration Pack priority:
  1. current prompt
  2. data understanding
  3. experience
  4. project knowledge
  5. SkillVersion list
- Retraining Pack requires a specified SkillVersion.
- MVP retrieval uses FTS5 only.

Verification:

```bash
python -m pytest tests/test_context.py -q
```

Expected:

```text
2 passed
```

Commit:

```bash
git commit -m "feat: generate mlagent context packs"
```

Review focus:

- Current user prompt remains highest priority.
- SkillVersions are reference-only during exploration.
- No sqlite-vec, RRF, reranker, or vector DB is added.
- Packs are not allowed to dump full raw memory by default.

### Task 8: SkillVersion Candidate and Approval

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 8`

Purpose:

- Add candidate SkillVersion creation and explicit human approval.

Creates:

- `mlagent_memory/skill_versions.py`
- `tests/test_skill_versions.py`

Modifies:

- `mlagent_memory/cli.py`

Key contract:

- `create_skill_candidate` writes to `skill_versions/.candidates/<version>/`.
- Candidate state is `pending_review`.
- Candidate is not a formal retraining asset.
- `approve_skill_candidate` requires reviewer, approval note, and performance YAML.
- Approved versions move to `skill_versions/<version>/`.
- `registry.yaml` records approved versions.

Verification:

```bash
python -m pytest tests/test_skill_versions.py -q
```

Expected:

```text
2 passed
```

Commit:

```bash
git commit -m "feat: add skillversion approval workflow"
```

Review focus:

- No automatic formal approval.
- `performance.yaml` is mandatory for approved versions.
- MLEM/modelstore are not imported.
- Local explicit CLI approval is primary; Git PR approval is not part of this task.

### Task 9: Claude Code Plugin Manifest and Skills

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 9`

Purpose:

- Add Claude Code plugin manifest and five workflow skills.

Creates:

- `.claude-plugin/plugin.json`
- `skills/start-modeling-session/SKILL.md`
- `skills/explore-optimization/SKILL.md`
- `skills/retrain-from-memory/SKILL.md`
- `skills/distill-run-to-memory/SKILL.md`
- `skills/promote-memory-to-skill/SKILL.md`

Key contract:

- Plugin name is `mlagent`.
- Skills describe process and boundaries.
- Skills call CLI commands rather than duplicating deterministic behavior.
- `promote-memory-to-skill` states human approval requirement explicitly.

Verification:

```bash
test -f .claude-plugin/plugin.json
test -f skills/start-modeling-session/SKILL.md
test -f skills/explore-optimization/SKILL.md
test -f skills/retrain-from-memory/SKILL.md
test -f skills/distill-run-to-memory/SKILL.md
test -f skills/promote-memory-to-skill/SKILL.md
```

Expected:

```text
exit 0
```

Commit:

```bash
git commit -m "feat: add mlagent plugin skills"
```

Review focus:

- Start from official Claude Code plugin layout.
- Do not copy unrelated superpowers skills.
- Skills must not claim MLagent trains models.
- Skills must preserve exploration vs strict retraining separation.

### Task 10: Conservative Hooks

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 10`

Purpose:

- Add minimal Claude Code hooks that remind, summarize, and avoid over-capture.

Creates:

- `hooks/hooks.json`
- `hooks/session-start`
- `hooks/post-tool-use`
- `hooks/post-tool-batch`
- `hooks/stop`
- `mlagent_memory/hooks.py`

Key contract:

- Hooks live in `hooks/hooks.json`.
- MVP hook set:
  - `SessionStart`
  - `PostToolUse`
  - `PostToolBatch`
  - `Stop`
- Hooks output valid JSON.
- Hooks do not store full logs, full diffs, training data, or model binaries.

Verification:

```bash
chmod +x hooks/session-start hooks/post-tool-use hooks/post-tool-batch hooks/stop
printf '{"cwd":"."}' | hooks/session-start
```

Expected:

```text
JSON containing hookSpecificOutput and SessionStart
```

Commit:

```bash
git commit -m "feat: add conservative claude code hooks"
```

Review focus:

- Hooks should remain conservative reminders/summarizers.
- `PostToolBatch` should reduce noise, not capture full tool responses.
- Do not enable `PreCompact` or `PostCompact` in MVP.

### Task 11: End-to-End MVP Verification

Full plan section:

- `docs/superpowers/plans/2026-06-22-mlagent-mvp-implementation.md`, `Task 11`

Purpose:

- Add end-to-end CLI test and README usage.

Creates:

- `README.md`

Modifies:

- `tests/test_cli.py`

Key contract:

- CLI can initialize a memory repo.
- CLI can import knowledge.
- CLI can rebuild index.
- CLI can search imported knowledge.
- README states the MVP boundaries.

Verification:

```bash
python -m pytest -q
python -m mlagent_memory.cli version
bin/mlagent-memory version
```

Expected:

```text
all tests passed
mlagent-memory 0.1.0
mlagent-memory 0.1.0
```

Commit:

```bash
git commit -m "test: verify mlagent mvp flow"
```

Review focus:

- End-to-end flow exercises the real CLI surface.
- README does not overpromise training or optimization.
- No excluded dependency appears in `pyproject.toml`.

## Review Checklist For The Design/Review Agent

Use this checklist after each development task:

- Does the diff only touch the files listed for that task?
- Did the task-specific tests run and pass?
- Did the developer commit after the task?
- Did the implementation preserve file-first durable assets?
- Did the implementation avoid excluded dependencies?
- Did the implementation avoid turning MLagent into a training framework?
- Did any automatic behavior write full logs, full diffs, training data, or model binaries?
- Did SkillVersion approval remain explicitly human-gated?
- Did Context Pack generation keep current prompt as highest priority?
- Did indexes remain rebuildable?

## Final Acceptance Gate

The MVP is ready for review only when all of these commands pass:

```bash
python -m pytest -q
python -m mlagent_memory.cli version
bin/mlagent-memory version
```

Expected:

```text
all tests passed
mlagent-memory 0.1.0
mlagent-memory 0.1.0
```

The reviewer should also inspect:

- `pyproject.toml` for forbidden dependencies.
- `skill_versions.py` for mandatory human approval.
- `context.py` for FTS5-only MVP retrieval.
- `hooks/` for conservative capture behavior.
- `skills/` for correct boundaries between exploration, distillation, promotion, and retraining.
