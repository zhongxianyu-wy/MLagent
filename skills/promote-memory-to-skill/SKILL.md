---
description: Use when the user asks to turn a best run or an existing notebook into a new MLagent SkillVersion.
---

# Promote Memory To Skill

Only humans can approve a formal SkillVersion.

Procedure:

1. Confirm whether the source is `best_run` or `ipynb_import`.
2. Generate a candidate with `mlagent-memory create-skill-candidate`.
3. Ask the user to review performance, reproducibility, inputs, outputs, and evidence.
4. Require a performance YAML file before approval.
5. Run `mlagent-memory approve-skill` only after explicit human confirmation.

Claude Code may create candidates. It must not approve a SkillVersion without explicit human review of benchmark performance.
