# Issue Tracker: GitHub

Specs and implementation tickets for this repository live in GitHub Issues:

- Repository: `zhongxianyu-wy/MLagent`
- PRs are not a feature-request or triage surface.
- The GitHub connector is preferred for issue operations in Codex.
- `gh` CLI is an allowed fallback only when its GitHub authentication is valid.

## Conventions

- A product spec is one parent issue containing the complete approved scope and testing decisions.
- `to-tickets` creates tracer-bullet child issues in dependency order.
- Every ticket links its parent spec and lists real blocking issue numbers.
- Agent-grabbable specs and tickets receive `ready-for-agent`.
- Do not close or rewrite the parent spec while delivering a child ticket.
- Git branches and commits should reference the issue number when implementation begins.

## Reading And Writing

Use the installed GitHub connector to search, create, update, label, and link issues. Infer the repository
from `origin` and verify the target is `zhongxianyu-wy/MLagent` before any mutation.
