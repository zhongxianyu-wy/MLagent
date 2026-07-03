---
description: 当用户想按某个已批准 SOP 版本严格重训时使用。直读 SOP，确定性复现——相同输入→相同产出。
---

# Retrain From SOP

Strict, deterministic retraining: identical input → identical output. The SOP version's SKILL.md + scripts are the controlling procedure.

## Procedure

1. User specifies the SOP name + version + new data.
2. Load the SOP:
   ```bash
   mlagent retrain <sop_name> <version> --memory-root <path>
   ```
3. Read the SOP's `SKILL.md` (the procedure) + `scripts/` (the runnable code) + `key_params` + `key_optimizations`.
4. Follow the procedure **exactly** — same preprocessing, same feature selection, same model, same hyperparameters. Only the DATA changes.
5. Run the training. Capture model + metrics.
6. Record the retraining run as a raw_memory entry with conclusion.

## Rules

- **Strict determinism**: use the same random seed, same CV folds, same hyperparameters. The only variable is the input data.
- If the result is better than the SOP's baseline, do NOT auto-promote — the user must explicitly run `instance-to-sop` to create a new version.
- If the result is worse, record the conclusion (outcome: refuted) and investigate.

## Gotchas

- Check `key_params` before running — these are the critical hyperparameters that must match.
- Check `key_optimizations` — these are the feature-selection/preprocessing choices that define the SOP's strategy.
