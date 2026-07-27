---
name: bootstrap-memory
description: Initialize the authoritative Team Memory Git repository and the local workspace connection. Use at project start, before any dataset/run/SOP work, when .mlagent-workspace.json is absent or a fresh team memory is needed.
---

# Bootstrap Memory

Use when the workspace has no `.mlagent-workspace.json`, or a fresh authoritative Team Memory is required.

## Boundary
Never bootstrap inside an existing authoritative repo. Never auto-push to a remote without explicit human confirmation. The connection file is the only local pointer; the Git repo is the sole source of truth.

## Preconditions
- A local directory path for the team memory repo (outside the connection file's parent).
- A team-member actor identity.
- (Optional) an SSH remote URL.

## Workflow
1. Run the bootstrap:
   ```bash
   python -m src.agent.main bootstrap-memory <repo-path> --actor <id> \
       [--remote URL] --workspace-config .mlagent-workspace.json
   ```
2. Confirm the connection file and Git repo were created.
3. Open the Streamlit UI pointing at the connection.

## Outputs
- `.mlagent-workspace.json` connection.
- Authoritative Team Memory Git repo (manifest + reviewer policy + capacity policy).
- Rebuildable LocalIndex.

## Failure and next step
- `connection_inside_repository` / `invalid_repository_path`: pick a repo path outside the connection directory.
- `git_unavailable` / `git_init_failed`: install git or check permissions.
- `remote_unreachable`: omit `--remote` and configure Git Sync later.
