# ADR-0003: Experience, SOP, And Formal Model Boundaries

- Status: Accepted
- Date: 2026-07-14

## Context

Expert guidance and reproducible training methods have different trust and provenance requirements. Mixing
them would allow an unverified summary to become an executable team standard.

## Decision

Experience is evidence-backed guidance for future exploration. Pending experience may be shown as low
confidence but cannot create or modify an SOP.

An SOP can originate only from one specified successful training instance. A Notebook must first execute
into such an instance. The SOP candidate must reproduce independently under matching data, code,
configuration, environment, split, and seed fingerprints; the primary metric must match to six decimals.
An authorized human then approves an immutable SOP version.

The formal model defaults to the independent reproduction output associated with the approved SOP. Baseline,
stage-best, and human-marked models may remain in run packages but are not formal model versions.

## Consequences

- Experience and SOP may cite the same evidence but never have a derivation edge between them.
- Failed or incomplete instances cannot generate SOPs.
- SOP execution on new data creates a run and candidate model, not an automatic SOP/model update.
- Model binary hashes may differ when the metric and all declared reproduction conditions match.
