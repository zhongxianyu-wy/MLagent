# MLagent v0.4 阶段性交接

> 更新日期：2026-07-17（Asia/Shanghai）  
> 当前阶段：Stage 1 - 权威记忆到正式 SOP 的核心闭环  
> 当前实现分支：`feat/issue-8-sop-promotion`  
> 已验证实现基线：`580e68831a10d71d43b9020bca32726c19958cd2`

## 1. 接手结论

MLagent v0.4 已经完成产品与架构定型，并实现第一条可运行、可测试、可审核的核心链路：

```text
Team Memory
  -> Dataset Version
  -> Exploration Plan + human approval
  -> frozen Training Instance
  -> incremental Git sync
  -> Experience extraction/review/reuse
  -> SOP Candidate
  -> independent Reproduction Gate
  -> human-approved SOP Version + Formal Model
```

GitHub Issue #2 至 #8 的工程实现已经完成并推送，当前统一处于 `ready-for-human`，尚未合并或
作为完整 MVP 发布。Issue #9 至 #16 尚待研发。不要从仓库根工作区的
`docs/v0.4-matt-workflow` 分支开始新功能；它只包含较早的文档基线。后续开发必须以
`feat/issue-8-sop-promotion` 的最新远程分支为起点。

## 2. 权威资料顺序

接手智能体必须按以下顺序阅读，并在内容冲突时使用靠前的资料：

1. `AGENTS.md`
2. 本文件 `HANDOFF.md`
3. `CONTEXT.md`
4. `specs/002-mlagent-plugin-memory-sop/prd.md`
5. `specs/002-mlagent-plugin-memory-sop/spec.md`
6. `docs/superpowers/specs/2026-07-14-mlagent-plugin-memory-sop-design.md`
7. 当前 Issue 对应的设计与实施计划
8. GitHub Issue 的 Acceptance criteria

`specs/001-ngs-ml-agent/`、根目录 `specs/plan.md`、根目录 `specs/tasks.md` 和未与 v0.4 对齐的
旧原型文档只能作为历史参考，不能覆盖上述基线。

后续总路线图见：

`docs/superpowers/plans/2026-07-17-v0.4-stage-2-roadmap.md`

## 3. 已确认且不得回退的产品边界

1. 产品入口保持为 Claude Code 插件，不替换为 Pi 或独立通用智能体框架。
2. 原始记录、Experience、SOP 和 Model 都由同一个团队 Team Memory Git 仓库管理。
3. Team Memory 中只保存关键事实和必要证据，不保存完整聊天、完整终端输出或重复日志。
4. Git 使用普通增量 fetch/pull/push 语义，只传输差异，不在正常会话中重新克隆仓库。
5. Local Index、MLflow、mem0、向量检索和 AIDE 类组件都不是权威数据源。
6. Experience 是帮助后续探索的专家知识；它不能创建、修改或批准 SOP。
7. SOP 只能来源于一个指定且成功的 Training Instance。
8. Notebook 必须先被解析并真实复现为 Training Instance，不能直接生成 SOP。
9. SOP 必须经过独立复现；相同声明条件下主指标按 `ROUND_HALF_UP` 保留六位后完全一致。
10. 只有授权人工可以批准 SOP。批准后形成不可原位修改的 SOP Version。
11. Formal Model 默认来自通过门禁的独立复现模型，并记录 SOP 策略和优化背景。
12. 普通 Exploration Plan 只是探索记录，不建立 SOP 式不可变方案版本库。
13. SOP 在新数据上重训练只能产生新 Run 和候选模型，不能自动覆盖正式 SOP 或 Formal Model。
14. UI 所有写入必须经过 Domain Core，不能直接修改 Team Memory 文件。
15. v0.4 只支持二分类和多分类；回归、深度学习、GPU 编排和原始 NGS 处理不在范围内。

## 4. Stage 1 交付状态

| Issue | 能力 | 工程状态 | 人工状态 |
| --- | --- | --- | --- |
| #2 | Team Memory 初始化、权威资产与可重建索引 | 已实现并推送 | `ready-for-human` |
| #3 | Dataset 检查、确认与不可变 Dataset Version | 已实现并推送 | `ready-for-human` |
| #4 | 探索方案记录、人工批准与训练门禁 | 已实现并推送 | `ready-for-human` |
| #5 | 冻结 Training Instance、真实分类训练和 Run Status | 已实现并推送 | `ready-for-human` |
| #6 | Git 增量同步、冲突保护和 Pending Sync | 已实现并推送 | `ready-for-human` |
| #7 | Experience 提取、审核、冲突、替代和复用 | 已实现并推送 | `ready-for-human` |
| #8 | 实例到 SOP、独立复现、人工批准和 Formal Model | 已实现并推送 | `ready-for-human` |

Issue #8 完整验证结果：

- `613 passed, 0 failed`
- Python `compileall` 通过
- `uv lock --check` 通过
- `git diff --check` 通过
- Streamlit 桌面端 `1440x1000` 验收通过
- Streamlit 移动端 `390x844` 验收通过
- 页面无横向溢出，浏览器控制台无 warning/error
- 已验证 SOP 通过/失败门禁、正式模型、冻结环境和版本趋势展示

上述数字是 `580e688` 上的已验证证据。后续修改后必须重新运行测试，不能沿用该结论。

## 5. 当前代码边界

新增 v0.4 行为优先进入以下位置：

- `src/domain/core.py`：CLI、Hooks 和 UI 共用的唯一应用边界
- `src/domain/models.py`：命令、快照、状态和错误契约
- `src/domain/*_repository.py`：权威 Git 资产的创建、读取和不可变约束
- `src/domain/run_execution.py`：受治理训练协调
- `src/domain/git_sync.py`：增量同步和冲突恢复
- `src/ui/shell.py`：六模块本地 UI
- `.claude/skills/`：Claude Code 工作流编排，不承载 SOP 方法本身
- `.claude/hooks/`：关键生命周期门禁和最小事实捕获
- `tests/unit/`：纯算法与状态校验
- `tests/integration/`：Domain Core、真实文件系统和本地 Git 工作流
- `tests/contract/`：CLI、Hook、服务和 UI 的公共契约

`src/memory/`、`src/skill_bridge/`、`src/aide_adapter/`、MLflow 和旧 API 中仍保留部分原型代码。
除非当前 Issue 明确需要，不要进行横向重构；新业务规则不能继续复制到这些旧适配层。

## 6. 下一阶段依赖顺序

推荐实施顺序：

```text
#9 Notebook import/reproduction ----\
                                      -> #14 Lineage --\
#10 SOP retraining -----------------/                 \
                                                         -> #15 Skills/Hooks -> #16 MVP acceptance
#11 Code Revision -> #12 real Claude CLI --------------/

#13 historical Run replay -------------------------------> #16 MVP acceptance
```

为了降低并行分支合并成本，默认按以下顺序串行叠加：

1. #9 Notebook 导入与复现
2. #10 SOP 新数据重训练
3. #11 Code Revision 审核与直接编辑
4. #12 真实 Claude Code CLI 接入
5. #13 历史 Run 回放和性能比较
6. #14 谱系图和时间线
7. #15 六 Skills 与四 Hooks 生命周期集成
8. #16 安全、恢复、容量、性能和全量 MVP 验收

#9、#10、#11、#13 在依赖上可并行，但只有在不同 worktree、文件所有权清晰并且预先约定集成
基线时才建议并行。`src/domain/core.py`、`src/domain/models.py` 和 `src/ui/shell.py` 是高冲突文件。

## 7. 下一位智能体的第一轮操作

```bash
cd /Volumes/exp/project/MLagent_v3
git fetch origin
git status --short --branch
git log -1 --oneline origin/feat/issue-8-sop-promotion
git worktree add .worktrees/issue-9-notebook-import \
  -b feat/issue-9-notebook-import origin/feat/issue-8-sop-promotion
cd .worktrees/issue-9-notebook-import
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q
```

预期基线：完整测试通过。若失败，先使用系统化调试确认是环境问题还是已有回归，不要直接在 #9
中顺手修改无关旧测试。

随后执行：

1. 阅读 GitHub Issue #9 和本交接文档中的固定边界。
2. 使用 brainstorming 对齐设计，但不要重新讨论已确认的产品决策。
3. 新建设计文档：`docs/superpowers/specs/YYYY-MM-DD-issue-9-notebook-import-design.md`。
4. 设计确认后使用 writing-plans 生成：
   `docs/superpowers/plans/YYYY-MM-DD-issue-9-notebook-import.md`。
5. 使用 test-driven-development，从 Domain Core 的失败验收测试开始实现。
6. 完成 focused tests、完整测试、静态检查和 UI 浏览器验收。
7. 进行需求一致性审查和代码质量审查，修复后重新验证。
8. 提交并推送 `feat/issue-9-notebook-import`。
9. 在 Issue #9 留下交付证据，并只在全部门禁通过后改为 `ready-for-human`。

## 8. 每个 Issue 的统一完成门槛

一个后续 Issue 只有同时满足以下条件，才可以声称工程完成：

- GitHub Acceptance criteria 每一条都有可指向的测试或人工验收证据。
- 新业务规则只在 Domain Core 和领域服务中实现一次。
- 先看到目标测试失败，再完成最小实现并使其通过。
- 权威资产具备 schema version、稳定 ID、actor、timestamp、状态和直接 provenance。
- 失败、中断和权限不足不会留下半正式资产。
- focused tests 与完整测试均通过。
- `compileall`、`uv lock --check` 和 `git diff --check` 通过。
- UI 变更完成桌面端和移动端真实浏览器验收，无横向溢出和控制台错误。
- 设计文档、实施计划、代码和测试一起提交。
- 分支推送到远程，工作区干净，并在 GitHub Issue 中记录 commit 与验证结果。
- 未经人工验收，不关闭 Issue、不合并为正式发布，也不宣称完整 MVP 完成。

统一验证命令：

```bash
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
git status --short --branch
```

## 9. Git 与集成注意事项

- Issue #2 至 #8 是按依赖逐层叠加的分支链，#8 分支已包含前序实现。
- 未确认 ancestry 前不要逐个合并 #2 至 #8，否则可能重复引入提交或制造无意义冲突。
- 后续每个 Issue 从最新已验收或最新交付分支创建，而不是从旧文档分支创建。
- 不允许 force push、`git reset --hard`、全工作区无差别 staging 或静默解决权威资产冲突。
- 不要提交 `.env`、密钥、Local Index、缓存、数据库、实验数据或本机连接文件。
- Team Memory 远端故障时保留本地提交和 Pending Sync，不以删除资产作为恢复方式。

## 10. 可直接交给下一位智能体的任务描述

```text
请接续 MLagent v0.4 开发。先阅读 AGENTS.md、HANDOFF.md、CONTEXT.md、v0.4 PRD、总设计和
Stage 2 roadmap。当前最新实现基线是 origin/feat/issue-8-sop-promotion，Issue #2-#8 已交付但
等待人工验收。请从该分支新建独立 worktree 实施 GitHub Issue #9，不要从根目录的
docs/v0.4-matt-workflow 开始。先完成 Issue #9 设计并对齐现有 Domain Core/权威 Git 资产约束，
再生成逐步实施计划，以测试驱动完成 Notebook 原件保留、解析报告、受控真实执行、成功转化为
Training Instance、失败不进入 SOP、UI/谱系引用和完整验收。禁止让 Notebook 直接成为 SOP，
禁止把 Experience 作为 SOP 来源，禁止在 UI 或 Hook 中复制领域规则。完成后运行完整测试和
静态检查，进行桌面/移动浏览器验收，提交、推送并把 Issue #9 标记为 ready-for-human。
```
