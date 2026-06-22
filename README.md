# MLagent

MLagent is a local-first Claude Code plugin for project-level machine learning modeling memory.

It does not train models or optimize parameters itself. Claude Code performs exploration and retraining through the project code. MLagent stores memory assets, builds context packs, indexes project knowledge, and governs human-approved SkillVersions.

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
