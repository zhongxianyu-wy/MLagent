# Quickstart: NGS ML Experiment Agent

## 1. Initialize environment

```bash
uv sync
```

## 2. Standardize input data

The default entry is an interactive LLM shell:

```bash
uv run python -m src.agent.main
```

Example turns:

```text
mlagent> /ask AUC 和特定特异性下灵敏度有什么区别？
assistant> [streaming answer; no tools are called]

mlagent> /plan 我想验证二元化甲基化特征是否提升 95% 特异性下的灵敏度
assistant> 我先确认：是否已有独立测试集，还是需要从训练数据随机划分？

mlagent> /intake experiments/data/example_project
assistant> 我找到了 2 个候选矩阵和 1 个标签文件。样本 ID 列是否是 sample_id？
mlagent> 是
assistant> 已生成 DatasetManifest。下一步可以输入 /explore 或直接描述探索目标。

mlagent> /agent /train_type1 重点探索特征子集选择，目标 AUC，最多 10 轮
assistant> 我会参考记忆库和 Skill 库选择未完成方向，并优先做预处理后特征子集选择。
```

One-shot commands remain available for automation:

```bash
uv run python -m src.agent.main intake \
  experiments/data/example_project \
  --output-root experiments/standardized \
  --split-strategy random \
  --split-ratio 0.2 \
  --random-seed 42
```

Expected result:

- The agent inspects candidate files.
- If needed, it asks one clarification question at a time.
- A `manifest.json`, standardized train files, optional test files, and `intake_report.md` are written under `experiments/standardized/<dataset_id>/`.

## 3. Run feature exploration

```bash
uv run python -m src.agent.main explore \
  --manifest-path experiments/standardized/<dataset_id>/manifest.json \
  --max-rounds 10 \
  --output-root experiments/outputs
```

Expected result:

- Each round writes a structured trace.
- The run directory contains `run_summary.json`, `rounds.jsonl`, `best_config.json`, and `metrics.json`.
- Best result uses test performance when a labeled test set exists; otherwise k-fold validation mean.
- Threshold is selected from training k-fold validation predictions only.

## 4. Reproduce an approved Skill

```bash
uv run python -m src.agent.main reproduce \
  --dataset-id <dataset_id> \
  --skill ngs-xgboost-baseline \
  --strict
```

Expected result:

- The Skill workflow is followed without exploratory changes.
- Metrics and model artifact path are recorded.

## 5. Interactive validation

```bash
uv run python -m src.agent.main interact \
  --dataset-id <dataset_id> \
  --instruction "Test whether binarized methylation features improve sensitivity at 95% specificity"
```

Expected result:

- One experiment direction runs.
- The agent returns results and pauses for the next instruction.

## 6. Distill a SkillCandidate

```bash
uv run python -m src.agent.main distill \
  --from-best-run <experiment_id>
```

or:

```bash
uv run python -m src.agent.main distill \
  --notebook otherinfo/example.ipynb
```

Expected result:

- A SkillCandidate draft is created.
- It follows `skill-creator` structure.
- darwin-skill-style iteration runs.
- Candidate remains pending human review.

## 7. Research external methods

```bash
uv run python -m src.agent.main research \
  --target "https://github.com/example/project"
```

Expected result:

- Research uses local muyu-search-mcp planning workflow.
- Findings enter semantic memory as research artifacts, not approved Skills.
