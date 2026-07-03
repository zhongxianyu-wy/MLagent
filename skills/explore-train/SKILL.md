---
description: Use when the user wants to explore a new ML direction, build a baseline, or run a training experiment. You write code grounded by injected experience; the human reviews. Flexible — no enforced structure.
---

# Explore + Train

## Procedure

1. Run `mlagent assemble-context "<user's goal>" --memory-root <path>` to get injected experience + conventions + SOPs.
2. Write/modify the training script. **Follow the code conventions** from the injected context (e.g., if conventions say "use 10-fold StratifiedKFold," use it).
3. Run the training. Capture stdout/stderr to `runs/<run_id>/log.txt` and metrics to `runs/<run_id>/metrics.json`.
4. After the run, record a raw_memory entry with a `conclusion` block:
   ```yaml
   id: raw_<ts>
   type: run
   created_at: <ISO>
   goal: "<user's goal>"
   hypothesis: "<what you expected>"
   results: {auc: 0.88}
   conclusion:
     hypothesis: "<what you expected>"
     outcome: confirmed | refuted | inconclusive
     summary: "<one-line verdict>"
     evidence: [runs/<run_id>/metrics.json]
   ```
5. `mlagent record-raw <file> --memory-root <path>`.

## When NOT to use

- Strictly retraining from an approved SOP → use `retrain-from-sop`.
- Promoting a best run to a SOP → use `instance-to-sop`.

## Gotchas

- Don't skip the conclusion — it's the "explore to conclusion" payoff. Even a refuted hypothesis is valuable.
- If the injected experience warns about a pitfall (e.g., "avoid post-outcome features"), heed it.
