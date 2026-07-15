---
name: design-and-explore
description: Create candidate ML exploration plans and code for a confirmed MLagent Dataset Version, route them through explicit human review, and start only an exactly approved formal exploration.
---

# Design And Explore

Use this workflow when the user asks to design, revise, or run a model exploration.

## Boundary

An Exploration Plan is a working record for one exploration workflow. It is not an SOP, not a
reusable strategy version, and not authority to train by itself. Only a later independently
reproduced and human-approved SOP can become an immutable reusable strategy.

Do not score or reject the scientific quality of the user's direction. Complete it into a clear,
reviewable plan, generate candidate code, and preserve the user's decisions.

Never auto-approve a plan. Approval requires an explicit human confirmation after the user has had
the opportunity to inspect both plan and code in the read-only Run Status view.

## Workflow

1. Identify the exact confirmed Dataset Version from Dataset Overview. Do not substitute a latest
   version when the user selected a specific version.
2. Ask only for missing direction or resource constraints that prevent a complete record.
3. Use relevant Trusted Experience as normal references. Label Pending Experience as low
   confidence. Keep user-excluded Pending Experience visible but do not use it to design changes.
4. Complete one JSON plan with this structure:

```json
{
  "plan_id": "plan-<stable-id>",
  "planning_session_id": "session-<stable-id>",
  "user_direction": "User's requested exploration direction",
  "baseline_hypothesis": "Baseline hypothesis",
  "rounds": [
    {
      "round_number": 1,
      "hypothesis": "What this round tests",
      "optimization_direction": "baseline",
      "intended_changes": ["Concrete change"]
    }
  ],
  "stop_conditions": ["Target reached", "Round budget exhausted"],
  "risks": ["Validation overfitting", "Class imbalance sensitivity"],
  "resource_limits": {"max_minutes": 30, "max_parallel_jobs": 1},
  "trusted_experience_ids": [],
  "pending_experience_ids": [],
  "excluded_pending_experience_ids": [],
  "candidate_code_paths": ["train.py"]
}
```

5. Generate UTF-8 candidate training code under the selected managed code root. Use relative paths
   in the plan and do not read or write through symlinks.
6. Record the review candidate:

```bash
python -m src.agent.main design-and-explore record \
  --workspace-config .mlagent-workspace.json \
  --dataset-id <dataset-id> \
  --dataset-version <integer-version> \
  --plan-file <plan.json> \
  --code-root <managed-code-root>
```

7. Direct the user to Run Status. Summarize that the code preview is read-only in this issue; direct
   editing and diffs belong to the later Code Review implementation.
8. After explicit human confirmation, approve the exact current plan and code:

```bash
python -m src.agent.main design-and-explore approve \
  --workspace-config .mlagent-workspace.json \
  --plan-id <plan-id> \
  --code-root <managed-code-root>
```

9. Start formal exploration only with the returned approval ID:

```bash
python -m src.agent.main explore \
  --workspace-config .mlagent-workspace.json \
  --dataset-id <dataset-id> \
  --dataset-version <integer-version> \
  --plan-id <plan-id> \
  --approval-id <approval-id> \
  --code-root <managed-code-root>
```

If the plan or code changes, record the current content again and obtain a new explicit approval.
Do not reuse an older approval and do not describe ordinary planning events as strategy versions.
