# MLagent

MLagent is a local-first Claude Code plugin for project-level machine learning modeling memory.

It does not train models or optimize parameters itself. Claude Code performs exploration and retraining through the project code. MLagent stores memory assets, builds context packs, indexes project knowledge, and governs human-approved SkillVersions.

## Scope & Boundaries (MVP)

These clarifications describe what the MVP *actually does today* versus later phases.

- **Installation.** The plugin is a Python package. Install it with `pip install -e .` (or `pip install .`) to get the `mlagent-memory` console script and its dependencies (typer, pydantic, sqlite_utils). The skills call `mlagent-memory ...`. The `bin/mlagent-memory` wrapper is a development convenience: when a sibling `.venv/bin/python` exists (e.g. in a worktree), it re-execs into that interpreter so the third-party deps resolve; in production the package install provides them.
- **Hooks.** The MVP hooks (`session-start`, `post-tool-use`, `post-tool-batch`, `stop`) emit **reminders and additional context only**. They do **not** automatically capture tool output, diffs, or commands into `raw_memory/`. Automatic evidence capture is a later phase.
- **SkillVersion from notebook.** `create-skill-candidate` creates a **candidate container** (`skill.yaml` + template `reproduce.md` / `constraints.md` / `validation_checklist.md`). It does **not** parse notebooks or extract training code automatically; Claude Code fills in the reproduce details before human approval.

## MVP Commands

```bash
mlagent-memory init --project-name demo --primary-metric auc
mlagent-memory status
mlagent-memory import-knowledge docs/paper.md --type paper
mlagent-memory index
mlagent-memory search leakage
mlagent-memory create-context-pack "Improve AUC" --pack-type exploration
mlagent-memory create-skill-candidate --version v001_baseline --name baseline --source-type best_run --source-evidence raw_memory/runs/raw_001.yaml
mlagent-memory approve-skill --version v001_baseline --reviewer human --approval-note "Performance meets target" --performance-path performance.yaml
```

## MVP Boundaries

- No vector database by default.
- No graph database.
- No MLflow, DVC, Optuna, or workflow orchestrator.
- No automatic formal SkillVersion approval.
- No full log, full diff, training data, or model binary capture by default.
