"""mlagent CLI — 中文用户提示 + 英文结构化输出。

用户可见的 echo/help → 中文；机器读取的 JSON 字段名 / hook 注入 / skill 名 → 英文。
"""

from pathlib import Path

import typer

from mlagent import __version__
from mlagent.context import assemble_context
from mlagent.distill import apply_distill_plan
from mlagent.errors import MlagentError
from mlagent.experience import add_experience
from mlagent.io import read_yaml
from mlagent.raw import add_raw_memory
from mlagent.repo import init_memory_repo, memory_status
from mlagent.sop import approve_sop, create_candidate, get_sop, list_sops, set_gate_result
from mlagent.sync import sync_pull, sync_push

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _callback() -> None:
    """mlagent — 项目级 ML 建模记忆系统（raw/experience/Skill-SOP）+ 研发资产显化。"""


@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(f"mlagent {__version__}")


@app.command()
def init(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    project_name: str = typer.Option(..., "--project-name"),
    primary_metric: str = typer.Option("auc", "--primary-metric"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """初始化项目记忆库（幂等；--force 覆盖种子文件）。"""
    init_memory_repo(memory_root, project_name=project_name, primary_metric=primary_metric, force=force)
    typer.echo(f"已初始化项目记忆库: {memory_root}")


@app.command()
def status(memory_root: Path = typer.Option(Path("project_memory"), "--memory-root")) -> None:
    """查看记忆库状态。"""
    try:
        data = memory_status(memory_root)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"项目: {data['project_name']}")
    typer.echo(f"主指标: {data['primary_metric']}")
    typer.echo(f"原始记忆: {data['raw_memory_count']}")
    typer.echo(f"经验: {data['experience_count']}")
    typer.echo(f"SOP 版本: {data['skill_version_count']}")


@app.command("record-raw")
def record_raw(
    record_path: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    replace: bool = typer.Option(False, "--replace"),
) -> None:
    """记录一条原始记忆（证据 + 结论 conclusion）。"""
    try:
        record = add_raw_memory(memory_root, read_yaml(record_path), replace=replace)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"已记录原始记忆: {record.id}")


@app.command("add-experience")
def add_experience_command(
    record_path: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    replace: bool = typer.Option(False, "--replace"),
) -> None:
    """添加一条经验（lesson/pitfall/pattern/direction/convention）。"""
    try:
        record = add_experience(memory_root, read_yaml(record_path), replace=replace)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"已添加经验: {record.id}")


@app.command("distill")
def distill_command(
    plan: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """应用蒸馏计划（由 distill-experience skill 产出）。"""
    try:
        ops = read_yaml(plan).get("ops", [])
        summary = apply_distill_plan(memory_root, ops)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    parts = [f"{k}={v}" for k, v in summary.items() if v]
    typer.echo(f"蒸馏完成: {', '.join(parts) or '无变更'}")


@app.command("convert-to-sop")
def convert_to_sop(
    sop_name: str = typer.Option(..., "--sop-name"),
    version: str = typer.Option(..., "--version"),
    source_type: str = typer.Option("exploration", "--source-type"),
    source_evidence: list[str] = typer.Option([], "--source-evidence"),
    background: str = typer.Option("", "--background"),
    reason: str = typer.Option("", "--reason"),
    key_param: list[str] = typer.Option([], "--key-param", help="key=value（可重复）"),
    key_optimization: list[str] = typer.Option([], "--key-optimization"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """创建 SOP 候选版本（实例→候选，含门禁 gate）。"""
    import json
    key_params: dict = {}
    for kp in key_param:
        if "=" in kp:
            k, v = kp.split("=", 1)
            try:
                key_params[k] = json.loads(v)
            except json.JSONDecodeError:
                key_params[k] = v
    try:
        create_candidate(memory_root, sop_name, version, source_type, source_evidence,
                         background=background, reason=reason,
                         key_params=key_params, key_optimizations=key_optimization)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"已创建 SOP 候选: {sop_name}/{version}（门禁: 测试未通过）")


@app.command("set-gate-result")
def set_gate_result_command(
    sop_name: str = typer.Option(..., "--sop-name"),
    version: str = typer.Option(..., "--version"),
    tests_passed: bool = typer.Option(True, "--tests-passed/--tests-failed"),
    test_log: str = typer.Option("", "--test-log"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """记录复现测试结果。"""
    try:
        set_gate_result(memory_root, sop_name, version, tests_passed, test_log)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"门禁结果已记录: {sop_name}/{version} tests_passed={tests_passed}")


@app.command("approve-sop")
def approve_sop_command(
    sop_name: str = typer.Option(..., "--sop-name"),
    version: str = typer.Option(..., "--version"),
    reviewer: str = typer.Option(..., "--reviewer"),
    approval_note: str = typer.Option(..., "--approval-note"),
    performance_path: Path = typer.Option(..., "--performance-path"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """审批 SOP 候选（需门禁通过 + 人工确认）。"""
    try:
        perf = read_yaml(performance_path)
        approve_sop(memory_root, sop_name, version, reviewer, approval_note, perf)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"已批准 SOP: {sop_name}/{version}")


@app.command("list-sops")
def list_sops_command(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """列出已批准 SOP 和待审候选。"""
    import json
    try:
        data = list_sops(memory_root)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    if as_json:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return
    if data["approved"]:
        typer.echo("已批准 SOP:")
        for v in data["approved"]:
            typer.echo(f"  {v['name']}/{v['version']} ✓")
    if data["candidates"]:
        typer.echo("待审候选:")
        for v in data["candidates"]:
            typer.echo(f"  {v['name']}/{v['version']} ({v['state']})")
    if not data["approved"] and not data["candidates"]:
        typer.echo("暂无 SOP。")


@app.command("get-sop")
def get_sop_command(
    sop_name: str = typer.Argument(...),
    version: str = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    include_draft: bool = typer.Option(False, "--include-draft"),
) -> None:
    """查看 SOP 版本详情。"""
    try:
        bundle = get_sop(memory_root, sop_name, version, include_draft=include_draft)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    sop = bundle["sop"]
    typer.echo(f"SOP: {sop_name}/{version} ({bundle['source']})")
    typer.echo(f"背景: {sop.get('background', '')}")
    typer.echo(f"原因: {sop.get('reason', '')}")
    if sop.get("key_optimizations"):
        typer.echo(f"关键优化: {', '.join(sop['key_optimizations'])}")


@app.command("retrain")
def retrain_command(
    sop_name: str = typer.Argument(...),
    version: str = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """加载已批准 SOP 进行严格重训（直读，不走路由）。"""
    import json
    try:
        bundle = get_sop(memory_root, sop_name, version)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    sop = bundle["sop"]
    typer.echo(f"重训来源: {sop_name}/{version}（已批准，不可变）")
    typer.echo(f"背景: {sop.get('background', '')}")
    typer.echo(f"关键参数: {json.dumps(sop.get('key_params', {}), default=str)}")
    typer.echo(f"关键优化: {', '.join(sop.get('key_optimizations', []))}")
    typer.echo(f"性能基线: {json.dumps(sop.get('performance', {}), default=str)}")


@app.command("assemble-context")
def assemble_context_command(
    prompt: str = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    full: bool = typer.Option(False, "--full"),
    limit: int = typer.Option(5, "--limit"),
) -> None:
    """组装探索上下文（经验/规范注入，供 explore-train 使用）。--full 显示完整字段。"""
    import json
    try:
        pack = assemble_context(memory_root, prompt, summary=not full, limit=limit)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(pack, indent=2, ensure_ascii=False, default=str))


@app.command("sync")
def sync_command(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """一键提交+推送（git 同步到远程）。"""
    try:
        sync_push(memory_root.parent)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"已同步（推送）: {memory_root.parent}")


@app.command("pull")
def pull_command(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """从远程拉取（git pull --ff-only，开机时同步）。"""
    try:
        sync_pull(memory_root.parent)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"已拉取: {memory_root.parent}")


# --- UI 子系统 ---

ui_app = typer.Typer(help="UI 子系统（本地浏览器界面）")
app.add_typer(ui_app, name="ui")


@ui_app.command("start")
def ui_start(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    port: int = typer.Option(0, "--port"),
) -> None:
    """启动本地 UI 服务器（detached，自动开浏览器）。"""
    import webbrowser
    from mlagent.ui.launch import launch
    try:
        p = launch(memory_root, port or None)
    except Exception as exc:
        typer.echo(f"UI 启动失败: {exc}")
        raise typer.Exit(2) from exc
    typer.echo(f"UI 已启动: http://127.0.0.1:{p}")
    webbrowser.open(f"http://127.0.0.1:{p}")


@ui_app.command("stop")
def ui_stop() -> None:
    """停止 UI 服务器。"""
    from mlagent.ui.launch import stop
    if stop():
        typer.echo("UI 已停止。")
    else:
        typer.echo("UI 未运行。")


def main() -> None:
    try:
        app()
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    main()
