# ADR-0002: Git Assets Are Authoritative, Local Indexes Are Derived

- Status: Accepted
- Date: 2026-07-14

## Context

The team needs portable history, precise provenance, reviewable changes, and incremental collaboration
without introducing a second authoritative database.

## Decision

All datasets, raw records, experience, SOPs, retained run models, and formal models live as versioned assets
in one private ordinary Git repository. Assets are append-first and immutable after commit. A local index
may accelerate search, status, and lineage, but is disposable and rebuildable.

Git synchronization fetches and pushes only differences, never reclones during a normal session, never
force-pushes, and stops on conflicting authoritative files.

## Consequences

- Schema validation and stable IDs are required before writes.
- The index cannot be treated as team truth or committed to the shared memory repository.
- Single files must remain below 100 MB and the repository is managed below 20 GB.
- Remote failures leave local commits in `Pending Sync` rather than losing work.
