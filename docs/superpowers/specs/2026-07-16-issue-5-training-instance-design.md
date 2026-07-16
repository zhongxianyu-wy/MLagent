# Issue #5 Frozen Training Instance Design

> Date: 2026-07-16
> Status: Approved v0.4 baseline carried forward for implementation
> Base: `feat/issue-4-exploration-plan`
> Scope: GitHub Issue #5

## 1. Decision

An approved Exploration Plan authorizes one governed Run. The Run executes its ordered rounds against the
exact approved Dataset Version and a frozen copy of the approved candidate code. Every attempted round is
sealed once as a Training Instance with immutable, fingerprinted evidence.

Exploration Plans remain ordinary workflow records. A Run and its Training Instances are historical facts,
not reusable strategy versions. No SOP, SOP Version, or Formal Model is created by this workflow. Those
assets remain gated by later independent reproduction and human approval.

## 2. Approaches Considered

### 2.1 Built-in trainer only

The Domain Core could ignore candidate code and run a fixed sklearn pipeline. This is easy to test, but it
would make the reviewed code differ from the code that produced the metric. That breaks the code-review and
lineage requirements.

### 2.2 Import candidate code into the Domain Core process

The Domain Core could import the approved Python file and invoke it directly. The metric would come from
the reviewed code, but an infinite loop or process-level failure could prevent deterministic timeout,
user-stop, and failure sealing.

### 2.3 Frozen code plus controlled subprocess contract

This design is selected. The Domain Core copies approved code into the Run package before execution. A
worker subprocess imports the frozen entrypoint, obtains an sklearn-compatible estimator from
`build_estimator(context)`, performs deterministic binary or multiclass evaluation, and writes a small
structured result package. The parent process controls timeout and user stop, validates all returned files,
and seals the Training Instance atomically.

This keeps the metric causally tied to reviewed code while preserving deterministic lifecycle handling.

## 3. Authoritative Layout

Issue #5 uses existing Team Memory managed roots and does not add a second database:

```text
raw-records/
  runs/<run-id>/<event-id>.json
runs/
  <run-id>/
    code-revisions/<code-fingerprint>/
      manifest.json
      files/<approved-relative-path>
    pending/<instance-id>/
      input.json
      environment.json
      split.csv
    instances/<instance-id>/
      manifest.json
      input.json
      environment.json
      split.csv
      metrics.json
      predictions.csv
      model.joblib              # only when retained
      error-evidence.txt        # bounded and only when needed
```

Run events are append-only Raw Records. A Training Instance is first prepared under `pending`, then renamed
to its final `instances` path after every required file and fingerprint has been validated. Final instance
paths are never overwritten by a Domain Core command. Load operations verify the manifest and referenced
file hashes, so manual in-place edits fail closed as tampering.

The Code Revision package is a frozen execution snapshot scoped to the Run. Issue #11 may add editable
candidate revision management, but it cannot replace or mutate this execution snapshot.

## 4. Run Event Model

Each Raw Record event contains only:

- event identity, actor, UTC time, and causal predecessor;
- Run, plan, approval, Dataset Version, and Training Instance references;
- event type and resulting Run state;
- round number, parent instance, hypothesis, and optimization direction when relevant;
- primary metric summary or bounded error summary when relevant;
- typed evidence references and a next action when recovery is required.

Events do not contain prompts, complete conversation history, repeated console output, full stack traces, or
unrelated tool activity. Event fingerprints cover their canonical content. Local writes are serialized by
an ignored lock file, and each new event points to the current causal head.

Run states are deterministic:

```text
created -> running -> completed
                   -> failed
                   -> timed_out
                   -> stopped
running without a terminal event -> recovery_required on the next query/startup
recovery_required -> running (explicit resume)
                  -> failed  (explicit close)
```

A stop request is an append-only event. The worker checks it while polling and between rounds. A recovery
action also appends an event; it never rewrites the original interrupted state.

## 5. Frozen Training Inputs

Before a round starts, the coordinator freezes and fingerprints:

- Dataset Version ID, integer version, content fingerprint, and version fingerprint;
- exact approved code files, per-file hashes, aggregate code fingerprint, and selected entrypoint;
- plan event, approval, hypothesis, optimization direction, and intended changes;
- declared worker contract, task type, label semantics, primary metric, target, and evaluation protocol;
- exact split bytes and split fingerprint;
- random seed and round number;
- parent Training Instance reference;
- runtime environment facts and environment fingerprint;
- timeout and retention request.

The worker runs from the frozen code path. A later edit in the workspace cannot affect an active Run.

## 6. Training Contract

The approved entrypoint is one of the frozen Python files and exposes:

```python
def build_estimator(context: dict):
    """Return an unfitted sklearn-compatible estimator."""
```

`context` contains task semantics, class labels, positive class, random seed, round number, hypothesis,
optimization direction, and intended changes. The worker rejects a missing function or a returned object
without sklearn `fit` and prediction capabilities.

The deterministic worker:

1. loads the immutable Dataset Version files and verifies sample alignment;
2. uses the exact frozen split;
3. performs stratified out-of-fold evaluation for `train_only`, or evaluates the frozen test partition for
   `stratified_random`;
4. supports binary metrics `roc_auc`, `accuracy`, and `f1`, and multiclass metrics `macro_f1`, `accuracy`,
   and `roc_auc_ovr`;
5. records the primary metric plus compatible secondary metrics;
6. writes sample-level predictions and fits a final model on the declared training partition;
7. serializes the final model with joblib and reports its fingerprint.

Metrics must be finite numbers in `[0, 1]`. A completed instance requires the declared primary metric,
predictions, a model fingerprint, and every frozen-input fingerprint. Technical validation does not score
or reject the scientific direction chosen by the user and Claude Code.

## 7. Instance States And Sealing

Every started round produces one terminal instance state:

- `completed`: all frozen evidence and required outputs validated; `reproducible_evidence=true`;
- `failed`: code, data, worker, validation, or serialization failure;
- `timed_out`: the declared timeout elapsed and the worker was terminated;
- `stopped`: an explicit user-stop request terminated or prevented the round.

Failure, timeout, and stopped instances are sealed with `reproducible_evidence=false`, no primary success
claim, a stable reason code, a concise error summary, and available frozen inputs. They are ineligible as
successful SOP sources. Full stdout and stderr are discarded; at most one bounded evidence fragment is
retained when it is necessary to explain the failure.

## 8. Model Retention

The worker creates a candidate model for every completed instance so its fingerprint can be recorded. The
Run package retains the binary only when one or more reasons apply:

- first successful round: `baseline`;
- a later round improves the Run's primary metric: `stage_best`;
- the user explicitly marks the round: `human_marked`.

Non-selected model files are removed before sealing, while their model fingerprint remains in the
instance manifest. A file at or above the Team Memory single-file limit is not retained and is recorded as
`rejected_too_large`; it never enters the Formal Model registry. Issue #5 writes nothing under the formal
`models` root.

## 9. Run Projection And UI

The Domain Core rebuilds Run Status from Run events and sealed instances. The projection contains:

- approved plan direction, stop conditions, state, current round, elapsed time, and last update;
- each round's hypothesis, optimization direction, parent instance, state, duration, and primary metric;
- ordered performance points, current best instance and value, target value, and target gap;
- model retention state and recovery/stop actions.

The existing Run Status module keeps its pre-run plan review. When Runs exist, it adds a Run selector,
summary metrics, performance curve, round table, best/target comparison, retained-model labels, and a Stop
action for an active Run. A Streamlit fragment polls the Domain Core every two seconds. The UI is only a
projection and remains optional for execution.

## 10. CLI Flow

The authoritative `explore` command continues to require the exact Dataset Version, plan, approval, and
code root. After authorization it calls the new Domain Core execution command rather than the legacy
prototype harness. The command may select an approved Python entrypoint; otherwise the first sorted
approved `.py` file is used.

One invocation executes the approved plan's ordered rounds from the frozen Code Revision. It stops on the
first failure, timeout, user stop, or target achievement. Unapproved `--max-rounds` input remains ignored.
The legacy `--manifest-path` route remains non-authoritative and cannot create governed assets.

## 11. Recovery

Run queries detect a started Run without a terminal event or an instance left under `pending` and report
`recovery_required`. The user may:

- resume, which seals an abandoned pending attempt as `interrupted` and retries that round as a new
  Training Instance from the already frozen Code Revision; or
- close, which seals any pending attempt as failed with reason `interrupted` and appends a failed terminal
  Run event.

Recovery never uses newly edited workspace code. A missing or tampered frozen snapshot blocks resume and
allows only an evidence-preserving close.

## 12. Testing

Tests exercise public behavior through the Domain Core, CLI, real subprocess worker, and Streamlit UI:

1. exact Issue #4 authorization is required before any Run asset is created;
2. binary and multiclass fixtures execute real sklearn estimators and record compatible metrics;
3. Dataset, code, configuration, environment, split, seed, plan, approval, and parent fingerprints reload;
4. final instances reject overwrite and tampering;
5. Raw Records contain only allowed fields and preserve causal event order;
6. success, failure, timeout, user stop, target stop, and interrupted recovery produce deterministic states;
7. failed instances cannot report reproducible success or become eligible SOP sources;
8. baseline, stage-best, human-marked, unselected, and oversized models follow retention rules;
9. workspace code edits after Run start do not change the frozen entrypoint used by later rounds;
10. Run Status shows plan, state, elapsed time, round directions, parent links, curve, best value, target, and
    model retention with a two-second polling contract;
11. existing Issue #2 through #4 tests remain green.

## 13. Non-Goals

- SOP Candidate creation, independent reproduction, SOP approval, or Formal Model registration.
- Experience extraction or review.
- Scientific scoring or automatic rejection of the approved exploration direction.
- General arbitrary-language execution, distributed jobs, GPU scheduling, or a full MLOps event service.
- Direct UI code editing or embedded Claude Code CLI, owned by Issues #11 and #12.
- Saving complete chat, console, stdout, stderr, or stack-trace history.
