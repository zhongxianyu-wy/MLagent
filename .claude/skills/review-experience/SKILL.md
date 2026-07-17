---
name: review-experience
description: Use when a user wants to inspect, edit, approve, reject, conflict, or supersede an MLagent Experience candidate.
---

# Review Experience

Review Experience only through Domain Core operations or the Experience Review UI. Do not edit
Team Memory files directly.

## Workflow

1. Select the exact Experience ID and current event version.
2. Inspect its conclusion, applicability, failure boundary, confidence, immutable history, and all
   Dataset, Run, Training Instance, and Raw Record evidence. Verify the displayed evidence hashes
   before deciding.
3. For Pending or Conflict Experience, edit reviewable content when needed and choose one explicit
   human action:
   - approve to Trusted;
   - reject with a reason;
   - mark Conflict and link the conflicting Experience.
4. For Trusted Experience, supersede only by linking another current Trusted Experience and stating
   why it replaces the earlier guidance.
5. Confirm the resulting state and appended review event in history.

Never auto-approve. Rejected and Superseded Experience are terminal. Conflict must name its related
Experience, and Superseded must name its Trusted replacement.

## Boundary

Experience is expert guidance for exploration. An Experience transition must not create, approve,
or modify an SOP, SOP Version, Formal Model, or immutable training strategy. SOP promotion remains a
separate independently reproduced and human-approved workflow.
