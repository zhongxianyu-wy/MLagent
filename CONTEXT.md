# MLagent Domain Context

## Purpose

MLagent helps a bioinformatics or computational biology team explore classification models while keeping
every reusable result reviewable, reproducible, and traceable. Claude Code drives the conversation and
workflow; deterministic domain services execute training and write authoritative assets.

## Ubiquitous Language

| Term | Meaning |
| --- | --- |
| Workspace | One local plugin project connected to one team memory repository. |
| Team Memory Repository | The private ordinary Git repository containing all authoritative project assets. |
| Authoritative Asset | A structured, versioned Git file or managed attachment that represents team truth. |
| Local Index | Disposable query data derived from authoritative assets; it can never overwrite them. |
| Dataset Version | Standardized features, labels, split, task, metric protocol, and one stable fingerprint. |
| Exploration Plan | User-approved hypotheses, rounds, evaluation method, target, stop rules, and cited experience. |
| Run | One bounded exploration or SOP execution containing ordered training instances. |
| Training Instance | One real execution with frozen data, code, configuration, environment, split, and seed. |
| Code Revision | An immutable code snapshot and fingerprint; a running instance never hot-reloads it. |
| Raw Record | Minimal facts and necessary evidence from a run, not a full conversation or full log. |
| Experience Candidate | Evidence-backed expert guidance extracted after a session but not yet approved. |
| Trusted Experience | A reviewed experience version that may guide future exploration. |
| SOP Candidate | A reproducible training method drafted from exactly one specified successful instance. |
| Reproduction Gate | Independent execution under matching fingerprints whose primary metric matches to six decimals. |
| SOP Version | An approved, immutable training method that has passed the reproduction gate. |
| Run Model | A retained baseline, stage-best, or human-marked model inside a run package. |
| Formal Model | The approved SOP reproduction model registered with strategy and optimization background. |
| Provenance Edge | A typed direct relation such as source, evidence, version, approval, or supersession. |
| Pending Sync | Local commits or assets preserved after a remote outage or conflict and awaiting safe synchronization. |

## Invariants

1. Raw records, experience, SOPs, and models are different asset types.
2. Experience guides exploration; it never creates or modifies an SOP.
3. An SOP originates from one specified training instance only.
4. A Notebook must first reproduce into a training instance before it can be an SOP source.
5. A formal SOP requires an independent reproduction gate and human approval.
6. Formal models are associated with approved SOP versions; ordinary intermediate models are not.
7. Committed authoritative assets are never overwritten in place.
8. The UI and Claude Code workflows write through domain services, not directly to Git files.
9. Git synchronization never force-pushes or silently resolves conflicting authoritative files.
10. Binary and multiclass classification are in scope; regression is not part of v0.4 MVP.

## State Transitions

```text
Experience Candidate -> Trusted Experience | Rejected Experience | Superseded Experience

Specified Training Instance -> SOP Candidate -> Reproduction Passed -> Approved SOP Version
                                           \-> Reproduction Failed -> Revised Candidate | Rejected

Notebook Import -> Reproduced Training Instance -> SOP Candidate
                \-> Import/Reproduction Failure

Approved SOP Version -> Formal Model
SOP Retraining on New Data -> New Run + Candidate Model (never automatic formal registration)
```

## Vocabulary To Avoid

- Do not call a training SOP a Claude Code Skill. A Skill orchestrates; an SOP is a domain asset.
- Do not call full chat history “raw memory”. Raw records contain only critical facts and evidence.
- Do not use “semantic memory” as the authority. Search indexes are derived from Git assets.
- Do not describe experience as an SOP source, even when both cite the same training instance.
