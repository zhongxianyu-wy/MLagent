---
description: 当用户想把最佳实例/notebook 提升为版本化 SOP 时使用。需通过复现测试门禁 + 人工审批，严格不可绕过。
---

# Instance → SOP

Promotes an exploration run or notebook into a versioned SOP-skill in `skill_library/`. Two gates: reproduction test + human approval.

## Procedure

1. Confirm the source (best run or notebook) with the user.
2. Create a candidate:
   ```bash
   mlagent convert-to-sop --sop-name <name> --version <ver> --source-type exploration \
     --source-evidence raw_memory/runs/raw_001.yaml \
     --background "<why this SOP exists>" --reason "<why it's the baseline>" \
     --memory-root <path>
   ```
3. Run the reproduction test (end-to-end: no errors + output matches + metric recorded).
4. Record the result:
   ```bash
   mlagent set-gate-result --sop-name <name> --version <ver> --tests-passed --test-log <log_path> --memory-root <path>
   ```
   (Use `--tests-failed` if the test fails — the SOP cannot be approved until it passes.)
5. Human reviews performance + reproducibility. Prepare `performance.yaml`:
   ```yaml
   primary_metric: {name: auc, value: 0.91}
   dataset_version: data_v001
   validation_protocol: holdout
   ```
6. Approve:
   ```bash
   mlagent approve-sop --sop-name <name> --version <ver> --reviewer <user> \
     --approval-note "..." --performance-path performance.yaml --memory-root <path>
   ```

## Rules

- Gate is **strict**: `tests_passed=False` → `approve-sop` rejects. No bypass.
- Approved versions are **immutable**. To change, create a new version.
- Fill `background` and `reason` — they're the "why this SOP exists" for future traceability.
