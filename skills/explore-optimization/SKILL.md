---
description: Use when the user asks Claude Code to explore model optimization directions using MLagent memory context.
---

# Explore Optimization

Claude Code performs the modeling exploration. MLagent supplies memory context and records evidence.

Procedure:

1. Preserve the user's current prompt as the highest-priority objective.
2. Run `mlagent-memory create-context-pack "<prompt>" --pack-type exploration --memory-root <path>`.
3. Use context in this order: current prompt, data understanding, high/medium confidence experience, project knowledge, SkillVersion list.
4. Explore through the project code and commands.
5. Record important run summaries through `mlagent-memory add-raw <record.yaml> --memory-root <path>`.

Do not force an existing SkillVersion unless the user explicitly asks for strict retraining.
