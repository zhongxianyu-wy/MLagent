# Issue #14 — 谱系图 实施计划

> 分支：`feat/issue-14-lineage`（基于 issue-13 `f537f7a`）
> 设计：`docs/superpowers/specs/2026-07-24-issue-14-lineage-design.md`

## 顺序（TDD）
1. models：`LineageNode`/`LineageEdge`/`LineageGraph` + frozenset
2. core：`get_lineage` + `verify_lineage_integrity` + `_verify_candidate_lineage`（review hook）
3. ui：`_render_lineage` + dispatch 分支 → AppTest
4. 验证 + 推送

## 测试（AC#8）
- 完整链：`test_lineage_links_dataset_through_run_instance_to_sop_and_model`
- AC#5 经验非 SOP 源：`test_experience_only_used_never_sop_source`
- AC#6 候选分支：`test_retrain_run_branches_not_merges_into_sop_version`
- AC#7 损坏/阻止审批：`test_broken_ref_detected_and_review_blocked`
- UI：`test_lineage_trace_renders_graph_and_timeline`、`test_lineage_trace_filter_changes_visible_nodes`

## 验证
```bash
cd /Volumes/exp/project/MLagent_v3/.claude/worktrees/issue-14
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
```
