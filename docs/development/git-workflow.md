# Git 分支管理规范

## 分支模型

项目采用 `main` 加短生命周期主题分支的轻量模式：

- `main`：始终保留可复现、通过当前测试的项目基线。
- `feature/<name>`：产品功能或较完整的设计变更。
- `fix/<name>`：缺陷修复。
- `docs/<name>`：纯文档修改。
- `chore/<name>`：依赖、工具和仓库维护。

当前记忆、SOP 和 UI 重设计在 `feature/mlagent-plugin-memory-sop` 上继续推进。

## 工作规则

1. 从最新 `main` 创建主题分支，不直接在 `main` 上开发功能。
2. 一个分支只处理一个清晰目标，提交保持可审查。
3. 提交前运行与改动范围匹配的测试，并检查暂存区不含密钥、大文件和本地配置。
4. 通过评审后将主题分支合并回 `main`，优先使用 squash merge 保持主线简洁。
5. 合并后删除已完成主题分支；需要长期维护的发布分支再单独建立。
6. 禁止向共享分支强推，冲突必须人工确认后处理。

## 提交格式

提交主题采用 Conventional Commits：

```text
<type>(<scope>): <summary>
```

常用类型包括 `feat`、`fix`、`docs`、`test`、`refactor` 和 `chore`。

## 敏感信息

以下内容只保存在本机，不进入 Git：

- `.env`
- `.mcp.json`
- `.codex/config.toml`
- `.claude/settings.local.json`
- `.venv/`、缓存、数据库和实验输出

仓库只提交脱敏示例配置。发现密钥进入提交历史时，应立即轮换密钥并清理历史。
