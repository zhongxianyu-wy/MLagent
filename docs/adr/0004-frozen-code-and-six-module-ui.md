# ADR-0004: Frozen Training Code And A Six-Module Local UI

- Status: Accepted
- Date: 2026-07-14

## Context

Users need to inspect and modify training code while experiments run, without silently changing an active
instance. They also need one focused interface for the main review and traceability workflows.

## Decision

Each training instance uses a frozen `Code Revision`. UI or Claude edits create the next candidate revision
and never hot-reload a running instance. Only one write-capable UI Claude session may control a workspace.

The local Web UI has six first-level modules: Code Review, Dataset Overview, Run Status, SOP Overview,
Experience Review, and Lineage Trace. All writes pass through domain services.

## Consequences

- The UI must show both the active frozen revision and the newest candidate revision.
- UI failure cannot block core training, recording, or Git synchronization.
- Real-time code, round, and metric updates target a two-second display delay.
- UI cache or index state can be rebuilt without mutating authoritative assets.
