# MLagent v0.4: Claude Code Plugin Memory, SOP, And Visual Collaboration

> Status: Approved product decisions synthesized for implementation planning
>
> Source: v0.4 PRD, domain context, and accepted ADRs
>
> GitHub Spec Issue: https://github.com/zhongxianyu-wy/MLagent/issues/1
>
> Scope: Binary and multiclass classification MVP

## Problem Statement

Bioinformatics and computational biology teams explore machine-learning models through conversations,
Notebook experiments, temporary scripts, and result directories. The useful facts from those explorations
are difficult to find later, successful results are difficult to reproduce exactly, and failed approaches
rarely become reusable team knowledge.

The user cannot reliably answer which dataset, code, configuration, environment, split, and random seed
produced a metric. Training experience and executable training methods are often mixed together, so an
unverified recommendation can be mistaken for a reproducible standard. Models may be retained without a
clear SOP or optimization background, while collaboration through ad hoc file copying risks overwriting
another person's work.

The user also lacks one place to inspect the active training code, understand the dataset and task, monitor
the direction and performance of each exploration round, review extracted experience, compare SOP
versions, and trace a formal model back to its direct evidence.

MLagent must solve these problems without becoming a general MLOps platform or recording every piece of
conversation and tool output. It needs a small, trustworthy core in which team assets are versioned,
reviewable, incrementally synchronized, and visible from Claude Code and a local UI.

## Solution

MLagent will remain a Claude Code plugin. Skills and Hooks guide the user through data intake, plan
approval, exploration, experience review, SOP creation, and SOP retraining. A deterministic Domain Core
will execute training, calculate metrics, enforce lifecycle rules, create authoritative assets, synchronize
Git, and provide the single application boundary used by the CLI, Hooks, and local Web UI.

All standardized datasets, Raw Records, Experience Candidates, Trusted Experience, SOP Candidates, SOP
Versions, retained Run Models, Formal Models, and approval records will live in one private Team Memory
Repository using ordinary Git. Those structured assets are the sole source of truth. A Local Index may
accelerate search and lineage but remains disposable and rebuildable.

Each Training Instance will freeze its Dataset Version, Code Revision, configuration, environment, split,
and random seed. Sessions will retain only critical facts and necessary evidence. Experience will guide
future exploration through a reviewable confidence lifecycle, but will never create an SOP. An SOP will
originate only from one specified successful Training Instance, pass an independent Reproduction Gate with
the primary metric equal to six decimal places, and receive human approval before it becomes an immutable
SOP Version with a Formal Model.

The local Web UI will expose six focused modules: Code Review, Dataset Overview, Run Status, SOP Overview,
Experience Review, and Lineage Trace. UI writes will pass through the same Domain Core rules as Claude Code
workflows, and edits will create new Code Revisions without hot-reloading a running instance.

## User Stories

1. As a bioinformatics engineer, I want to connect a workspace to a private Team Memory Repository, so that my team shares one authoritative history.
2. As a repository maintainer, I want SSH access and repository capacity checked during setup, so that synchronization failures are found before training begins.
3. As a team member, I want session startup to synchronize only Git differences, so that large histories are not downloaded again.
4. As a team member, I want remote outages to leave my local assets in Pending Sync, so that no completed work is lost.
5. As a team member, I want conflicting authoritative files to stop automatic synchronization, so that another person's work is never silently overwritten.
6. As a bioinformatics engineer, I want the plugin to inspect feature and label inputs, so that I can understand sample, feature, missingness, and class structure.
7. As a bioinformatics engineer, I want to confirm the Dataset Version fingerprint, so that later runs refer to an exact data state.
8. As a bioinformatics engineer, I want to confirm binary or multiclass task semantics, so that labels and positive-class meaning are not inferred incorrectly.
9. As a bioinformatics engineer, I want to confirm the primary metric, split, target performance, and stop rules, so that exploration has an explicit evaluation contract.
10. As a bioinformatics engineer, I want MLagent to draft an Exploration Plan before training, so that I can review its baseline, hypotheses, rounds, and risks.
11. As a bioinformatics engineer, I want formal training blocked until I approve the Exploration Plan, so that the agent cannot spend resources in an unapproved direction.
12. As a bioinformatics engineer, I want the plan to distinguish Trusted Experience from low-confidence Experience Candidates, so that I understand the evidence quality behind a suggestion.
13. As a bioinformatics engineer, I want to exclude a low-confidence Experience Candidate from a plan, so that uncertain guidance does not steer the run without my consent.
14. As a bioinformatics engineer, I want each exploration round to state its hypothesis and main optimization direction, so that performance changes are explainable.
15. As a bioinformatics engineer, I want each Training Instance to use a frozen Code Revision and declared inputs, so that its result remains reproducible after later edits.
16. As a bioinformatics engineer, I want a failed or timed-out training attempt recorded as a failed Training Instance, so that failure evidence is not discarded.
17. As a bioinformatics engineer, I want baseline, stage-best, and explicitly marked Run Models retained, so that useful checkpoints survive without saving every intermediate model.
18. As a team member, I want a Raw Record to retain only decisions, inputs, metrics, failures, conclusions, and necessary evidence, so that the repository stays useful rather than becoming a full log archive.
19. As a team member, I want an interrupted Run detected at the next session start, so that I can recover, continue, or close it explicitly.
20. As a bioinformatics engineer, I want session completion to extract evidence-backed Experience Candidates, so that successful patterns and failure modes become reviewable knowledge.
21. As a bioinformatics engineer, I want empty or unsupported experience omitted, so that the experience library does not accumulate noise.
22. As an authorized reviewer, I want to edit, approve, reject, supplement, conflict, or supersede an Experience Candidate, so that the team can govern expert knowledge over time.
23. As an authorized reviewer, I want every experience decision to retain the original wording, evidence, reviewer, time, and outcome, so that the review itself is auditable.
24. As a bioinformatics engineer, I want to select one successful Training Instance as an SOP source, so that the SOP is grounded in an actual execution.
25. As an authorized reviewer, I want an SOP Candidate rejected when its source evidence is incomplete, so that an incomplete method cannot become a team standard.
26. As a bioinformatics engineer, I want an imported Notebook parsed for execution order, dependencies, paths, randomness, and metrics, so that hidden assumptions become explicit.
27. As a bioinformatics engineer, I want a Notebook to execute into a Training Instance before SOP creation, so that a document alone is never treated as proof of reproducibility.
28. As an authorized reviewer, I want an SOP Candidate independently rerun under matching fingerprints, so that its method is verified rather than merely summarized.
29. As an authorized reviewer, I want the Reproduction Gate to require the primary metric to match at six decimal places, so that approval has one unambiguous standard.
30. As an authorized reviewer, I want model binary hashes allowed to differ when declared conditions and the metric match, so that platform-level serialization differences do not create a false failure.
31. As an authorized reviewer, I want to approve an SOP only after the Reproduction Gate passes, so that every SOP Version is a verified training method.
32. As a team member, I want SOP changes to create a new immutable version, so that previous training standards remain reproducible and comparable.
33. As a team member, I want a Formal Model to record its SOP Version, data, source and reproduction instances, performance, strategy, optimization background, and approval, so that it has complete provenance.
34. As a bioinformatics engineer, I want to retrain an exact SOP Version on a selected Dataset Version, so that repeated or expanded projects follow a known method.
35. As an authorized reviewer, I want SOP retraining on new data to produce only a new Run and candidate model, so that formal assets are not upgraded without review.
36. As a bioinformatics engineer, I want to inspect and directly edit relevant training code in the UI, so that I can challenge or correct an exploration implementation.
37. As a bioinformatics engineer, I want to prompt a real Claude Code CLI session from the Code Review module, so that conversational and direct code changes share one review surface.
38. As a bioinformatics engineer, I want a running Training Instance to continue using its frozen Code Revision after an edit, so that live changes cannot corrupt its evidence.
39. As a bioinformatics engineer, I want the Dataset Overview to show Pandas-style head and tail data, task semantics, splits, and metrics, so that I can validate inputs without loading the entire dataset.
40. As a bioinformatics engineer, I want Run Status to show the approved plan, state, round, elapsed time, optimization direction, performance curve, best instance, and target gap, so that I can supervise exploration in real time.
41. As a bioinformatics engineer, I want the current performance curve compared with a selected historical SOP baseline, so that the value of a new direction is visible.
42. As a project lead, I want SOP Overview to compare versions, strategy changes, datasets, performance, approvals, and Formal Models, so that team standards can be evaluated over time.
43. As an authorized reviewer, I want Experience Review to show confidence, evidence, conflicts, and supersession, so that review decisions are made with context.
44. As a project lead, I want Lineage Trace to navigate Dataset Versions, Runs, Training Instances, Experience, Notebooks, SOPs, and models, so that any formal result can be traced to direct evidence.
45. As a project lead, I want lineage edge types to distinguish source, evidence, version, approval, and supersession, so that the graph never implies that Experience generated an SOP.
46. As a team member, I want the Local Index rebuilt from an empty state, so that query acceleration never becomes a second source of truth.
47. As a team member, I want UI failure to leave Claude Code training and memory workflows usable, so that visualization is not a runtime dependency.
48. As a repository maintainer, I want files at or above 100 MB and repository growth beyond 20 GB blocked or surfaced, so that ordinary Git remains viable.

## Implementation Decisions

1. **Product boundary:** MLagent remains a local Claude Code plugin. It is not rebuilt as a standalone agent runtime or public SaaS.
2. **Primary application boundary:** one cohesive Domain Core public interface owns all commands and queries used by CLI, Hooks, and UI. Business rules must not be reimplemented in adapters.
3. **Workflow versus method:** Claude Code Skills orchestrate workflow and human gates. An SOP Version is a domain asset and is never represented as a Claude Code Skill.
4. **MVP Skills:** the plugin exposes `bootstrap-memory`, `intake-data`, `design-and-explore`, `retrain-from-sop`, `review-experience`, and `instance-to-sop`.
5. **Hook lifecycle:** `SessionStart` synchronizes and recovers state; `PreToolUse` enforces plan and write guards; `PostToolUse` captures only critical training actions; `Stop` seals the Run, extracts Experience Candidates, and safely synchronizes managed changes.
6. **Authoritative storage:** all domain truth is represented by structured, schema-versioned Git assets with stable IDs, explicit versions, timestamps, actors, states, and typed provenance references.
7. **Repository separation:** plugin source code and the Team Memory Repository have independent lifecycles. A workspace records how it connects to its team repository without committing private keys or local credentials.
8. **Asset immutability:** committed Authoritative Assets are not edited in place. Corrections, approvals, rejections, and supersessions create new records or versions.
9. **Dataset Version:** standardized features, labels, split, task, metric protocol, and content fingerprint form one immutable version. Changes to labels, split, or standardized content create another version.
10. **Task boundary:** v0.4 supports binary and multiclass classification only. Task type, labels, positive class where relevant, metric, split, target, and stop rules require user confirmation.
11. **Plan gate:** formal training commands require an explicitly approved Exploration Plan record whose current plan and candidate-code fingerprints still match the approval. Exploration Plans are ordinary workflow records, not reusable immutable SOP-style versions. The guard applies consistently through Claude Code, CLI, and UI.
12. **Training execution:** each Training Instance freezes Dataset Version, Code Revision, configuration, environment, split, seed, parent instance, and evaluation protocol before execution.
13. **Run retention:** metrics, predictions, errors, and model fingerprints remain traceable for every instance. Only baseline, stage-best, human-marked, and SOP-related model artifacts are retained by default.
14. **Minimal Raw Record:** full conversations, unrelated tool output, and complete stdout/stderr are excluded by default. Only evidence needed for reproduction, explanation, failure analysis, or human decisions is retained.
15. **Experience lifecycle:** session completion may create zero or more Experience Candidates with conclusion, applicability, recommended action, risk, and direct evidence. Pending candidates are low confidence; approval creates Trusted Experience.
16. **Experience boundary:** neither pending nor Trusted Experience can create, modify, or approve an SOP. Experience and SOP may independently reference the same Training Instance.
17. **SOP source:** exactly one specified successful Training Instance is the source of an SOP Candidate. Chat summaries, experience, scripts that have not run, and standalone models are invalid sources.
18. **Notebook import:** an imported Notebook and parse report are evidence. It must be normalized and executed into a successful Training Instance before the SOP lifecycle begins.
19. **Reproduction Gate:** the source and reproduction are distinct execution records under matching data, code, configuration, environment, split, and seed fingerprints. The primary metric, normalized to six decimal places, must be exactly equal.
20. **SOP approval:** one authorized reviewer may approve a candidate only after the Reproduction Gate passes. Approval creates an immutable SOP Version and preserves the source, reproduction, and approval evidence.
21. **Formal Model:** the default Formal Model is the independent reproduction output for an approved SOP Version. The source model remains in its Run package instead of being registered twice for the same version.
22. **SOP retraining:** execution on a new Dataset Version produces a new Run, Training Instances, and candidate model. It cannot automatically revise the SOP Version or Formal Model registry.
23. **Local Index:** search, status summaries, time playback, and lineage traversal use a derived Local Index that is never committed and can be rebuilt from Authoritative Assets.
24. **Lineage semantics:** provenance edges are typed. Source, evidence, version, approval, conflict, and supersession have distinct meanings; unsupported derivation edges are rejected.
25. **Git synchronization:** ordinary Git transfers only differences. Startup may fast-forward or merge disjoint additions; content conflicts stop automation. Shutdown stages only plugin-managed paths and retries one rejected push after fetching.
26. **Git safety:** force push, silent conflict resolution, full-workspace staging, and normal-session recloning are forbidden. Network failure creates Pending Sync state.
27. **Capacity:** managed files remain below 100 MB and the repository is maintained below 20 GB, with warning at 80% and a hard guard before automatic large-file commits.
28. **Code revision semantics:** every human or Claude save creates a Code Revision and audit record. A running Training Instance never hot-reloads a new revision.
29. **UI write model:** all six modules query and mutate through the Domain Core. The UI never edits authoritative Git files directly.
30. **UI concurrency:** one write-capable Claude Code UI session controls a workspace at a time. Other sessions are read-only or wait for an explicit handover.
31. **UI real-time contract:** code, round, and metric events are visible within two seconds when the UI is connected. Disconnection shows the last update and supports recovery without changing domain state.
32. **Dataset presentation:** previews use bounded head-and-tail rows with a visual omission marker. Unconfirmed inferred semantics are shown as pending, not as fact.
33. **Run presentation:** the performance curve annotates round-level direction changes and can overlay a compatible historical SOP metric baseline.
34. **Failure handling:** failed training, unsealed Runs, index corruption, UI outage, Notebook reproduction failure, SOP metric mismatch, and Git conflict each preserve the last valid authoritative state and expose an actionable recovery outcome.
35. **Optional legacy adapters:** mem0, MLflow, semantic/vector retrieval, AIDE, dream jobs, and literature research are not authoritative MVP dependencies. Existing prototype code may remain temporarily but cannot define v0.4 behavior.
36. **Migration approach:** replace parallel prototype rules through tracer-bullet slices that route complete user workflows through the new Domain Core while keeping the test suite green.

## Testing Decisions

1. **Test external behavior:** tests assert visible state transitions, authoritative assets, service responses, Hook decisions, CLI outcomes, and UI workflows. They do not assert private helper calls, internal class layout, or exact LLM prose.
2. **Primary seam:** the highest and preferred seam is the Domain Core public application boundary exercised against a temporary filesystem and real local Git repositories. Most domain behavior should be provable through this one seam.
3. **Deterministic collaborators:** training and time may use deterministic controllable collaborators when a test targets lifecycle behavior. Separate integration tests execute real lightweight classification training on fixed fixtures.
4. **Authoritative asset coverage:** schema validation, immutable versions, stable references, provenance edge types, retention decisions, approval audit, and index rebuild are tested through written and reloaded assets.
5. **Data and task coverage:** clear and ambiguous fixtures cover binary and multiclass recognition, required user confirmation, invalid labels, split validation, and bounded previews.
6. **Plan and Hook coverage:** a formal training attempt is rejected before plan approval and accepted after explicit confirmation, regardless of whether it enters through a Skill, CLI command, Hook, or UI action.
7. **Run coverage:** success, failure, timeout, user stop, target stop, unsealed recovery, Code Revision freeze, model retention, and minimal Raw Record behavior are tested as observable Run outcomes.
8. **Experience coverage:** extraction creates evidence-backed candidates only when justified; low-confidence use is labeled; approve, edit, reject, conflict, and supersede transitions preserve audit history; no experience state can produce an SOP.
9. **SOP coverage:** direct instance and Notebook paths converge on a real successful Training Instance. Incomplete evidence, failed execution, and metric mismatch cannot pass the gate or create a Formal Model.
10. **Exact reproduction coverage:** independent source and reproduction records must use matching fingerprints and equal six-decimal primary metrics. Tests explicitly allow different model hashes.
11. **Retraining coverage:** executing an SOP Version on a new Dataset Version creates candidate outputs only and leaves the approved SOP and Formal Model registry unchanged.
12. **Git coverage:** tests use local repositories and a local bare remote to prove incremental fetch/push, fast-forward, disjoint additions, rejected push retry, conflict stop, managed-path staging, Pending Sync, and no force push.
13. **Index coverage:** deleting or corrupting the Local Index and rebuilding it must restore search, status, timeline, and lineage without modifying authoritative files.
14. **Adapter contracts:** CLI, Hooks, service/API endpoints, and the UI event boundary receive contract tests showing that they delegate to the same Domain Core behavior.
15. **Browser acceptance:** focused browser tests cover the six navigation modules, code edit plus frozen revision display, dataset preview, live Run updates, experience review, SOP comparison, and Formal Model lineage. Visual details outside critical state semantics are not exhaustively snapshot-tested.
16. **Performance acceptance:** local tests or benchmarks verify the under-100-MB dataset first view within three seconds and 95% of connected code/round/metric UI updates within two seconds under the declared reference environment.
17. **Security coverage:** credentials and Local Index files remain untracked; writes outside managed roots are rejected; unauthorized users cannot approve Experience or SOP assets; Git conflicts never trigger force push.
18. **Prior art:** existing contract tests for mode guards, safety Hooks, service/API boundaries, storage, run state, and strict reproduction will be adapted. Existing integration tests for intake, real training, exploration traces, and CLI workflows provide the preferred style.
19. **Unit-test boundary:** fine-grained unit tests are reserved for deterministic algorithms such as metric calculation, threshold selection, fingerprint normalization, state transition validation, and capacity calculation.
20. **Completion gate:** each tracer-bullet ticket must pass its focused tests and the full suite. The final MVP additionally runs the complete Given/When/Then acceptance set from the PRD.

## Out of Scope

- Regression, deep learning, GPU clusters, distributed training, and general AutoML platform behavior.
- Processing raw sequencing formats such as FASTQ or BAM into feature matrices.
- Public multi-tenant SaaS, remote public UI hosting, or online Notebook hosting.
- Automatic approval of Experience, SOP Versions, or Formal Models.
- Treating mem0, MLflow, a vector database, AIDE, or any Local Index as the source of truth.
- Mandatory autonomous background experiments, dream jobs, or automated literature ingestion.
- Git LFS, object storage, multi-repository federation, or automatic repository-history rewriting.
- Saving complete chat transcripts, unrelated tool output, or complete stdout/stderr by default.
- Hot-reloading code into a running Training Instance or allowing concurrent write-capable UI Claude sessions.
- Replacing Claude Code with Pi, a standalone agent framework, or a custom general-purpose agent runtime.
- Implementing speculative cross-project semantic transfer before the authoritative v0.4 lifecycle is complete.

## Further Notes

- The v0.4 PRD remains the detailed product and acceptance reference. This Spec is the parent implementation
  contract used by `to-tickets`; it does not mark unimplemented prototype gaps as delivered.
- The domain vocabulary and accepted ADRs govern ticket titles, interfaces, test names, and UI wording.
- Formal SOP reproducibility means declared conditions and the six-decimal primary metric match. It does not
  promise bit-identical model serialization across platforms.
- Git assets are designed for expected files below 100 MB and repository size below 20 GB. Crossing those
  limits requires a new reviewed architecture decision rather than silently adding Git LFS.
- The MVP release is complete only when every Formal Model traces to an SOP Version and direct evidence,
  every completed Training Instance has required frozen inputs, no unversioned overwrite occurs, sync
  failures lose no local assets, and low-confidence Experience never crosses an approval boundary.
- `to-tickets` should prefer narrow end-to-end tracer bullets. The first frontier ticket should establish
  the Domain Core asset and command boundary with one demonstrable workflow, not build all storage or UI
  layers horizontally.
