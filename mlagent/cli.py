"""mlagent CLI (Typer).

Deterministic operations live here; workflow judgment lives in the skills.
v0.3 slice-1 skeleton: only `version` for now; subsequent tasks add
init/status/record-raw/distill/convert-to-sop/approve-sop/list-sops/get-sop/
retrain/assemble-context/sync/ui.
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
    """mlagent — project-level ML modeling memory (raw/experience/Skill-SOP) + R&D asset visualization."""


@app.command()
def version() -> None:
    """Print the CLI version."""
    typer.echo(f"mlagent {__version__}")


@app.command()
def init(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    project_name: str = typer.Option(..., "--project-name"),
    primary_metric: str = typer.Option("auc", "--primary-metric"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Create a project memory repo (idempotent; --force overwrites seed files)."""
    init_memory_repo(memory_root, project_name=project_name, primary_metric=primary_metric, force=force)
    typer.echo(f"Initialized project memory repo: {memory_root}")


@app.command()
def status(memory_root: Path = typer.Option(Path("project_memory"), "--memory-root")) -> None:
    """Show project memory repo status."""
    try:
        data = memory_status(memory_root)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"Project: {data['project_name']}")
    typer.echo(f"Primary metric: {data['primary_metric']}")
    typer.echo(f"Raw memory records: {data['raw_memory_count']}")
    typer.echo(f"Experience records: {data['experience_count']}")
    typer.echo(f"Skill versions: {data['skill_version_count']}")


@app.command("record-raw")
def record_raw(
    record_path: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    replace: bool = typer.Option(False, "--replace"),
) -> None:
    """Add a raw memory YAML record (evidence + conclusion)."""
    try:
        record = add_raw_memory(memory_root, read_yaml(record_path), replace=replace)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"Recorded raw memory: {record.id}")


@app.command("add-experience")
def add_experience_command(
    record_path: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    replace: bool = typer.Option(False, "--replace"),
) -> None:
    """Add an experience YAML record (lesson/pitfall/pattern/direction/convention)."""
    try:
        record = add_experience(memory_root, read_yaml(record_path), replace=replace)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"Added experience: {record.id}")


@app.command("distill")
def distill_command(
    plan: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Apply a distill plan (produced by the distill-experience skill)."""
    try:
        ops = read_yaml(plan).get("ops", [])
        summary = apply_distill_plan(memory_root, ops)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    parts = [f"{k}={v}" for k, v in summary.items() if v]
    typer.echo(f"Distill applied: {', '.join(parts) or 'no changes'}")


@app.command("convert-to-sop")
def convert_to_sop(
    sop_name: str = typer.Option(..., "--sop-name"),
    version: str = typer.Option(..., "--version"),
    source_type: str = typer.Option("exploration", "--source-type"),
    source_evidence: list[str] = typer.Option([], "--source-evidence"),
    background: str = typer.Option("", "--background"),
    reason: str = typer.Option("", "--reason"),
    key_param: list[str] = typer.Option([], "--key-param", help="key=value (repeatable)"),
    key_optimization: list[str] = typer.Option([], "--key-optimization"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Create a pending SOP candidate (instance → candidate with gate)."""
    import json
    key_params = {}
    for kp in key_param:
        if "=" in kp:
            k, v = kp.split("=", 1)
            try:
                key_params[k] = json.loads(v)
            except json.JSONDecodeError:
                key_params[k] = v
    try:
        sv = create_candidate(memory_root, sop_name, version, source_type, source_evidence,
                              background=background, reason=reason,
                              key_params=key_params, key_optimizations=key_optimization)
    except MlagentError as exc:
        typer.echo(str(exc)); raise typer.Exit(2) from exc
    typer.echo(f"Created SOP candidate: {sop_name}/{version} (gate: tests_passed=False)")


@app.command("set-gate-result")
def set_gate_result_command(
    sop_name: str = typer.Option(..., "--sop-name"),
    version: str = typer.Option(..., "--version"),
    tests_passed: bool = typer.Option(True, "--tests-passed/--tests-failed"),
    test_log: str = typer.Option("", "--test-log"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Record the reproduction test result for a candidate."""
    try:
        set_gate_result(memory_root, sop_name, version, tests_passed, test_log)
    except MlagentError as exc:
        typer.echo(str(exc)); raise typer.Exit(2) from exc
    typer.echo(f"Gate result set: {sop_name}/{version} tests_passed={tests_passed}")


@app.command("approve-sop")
def approve_sop_command(
    sop_name: str = typer.Option(..., "--sop-name"),
    version: str = typer.Option(..., "--version"),
    reviewer: str = typer.Option(..., "--reviewer"),
    approval_note: str = typer.Option(..., "--approval-note"),
    performance_path: Path = typer.Option(..., "--performance-path"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Approve a SOP candidate after gate passed + human review."""
    try:
        perf = read_yaml(performance_path)
        approved = approve_sop(memory_root, sop_name, version, reviewer, approval_note, perf)
    except MlagentError as exc:
        typer.echo(str(exc)); raise typer.Exit(2) from exc
    typer.echo(f"Approved SOP: {sop_name}/{version}")


@app.command("list-sops")
def list_sops_command(memory_root: Path = typer.Option(Path("project_memory"), "--memory-root")) -> None:
    """List approved SOPs and pending candidates."""
    import json
    try:
        data = list_sops(memory_root)
    except MlagentError as exc:
        typer.echo(str(exc)); raise typer.Exit(2) from exc
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


@app.command("get-sop")
def get_sop_command(
    sop_name: str = typer.Argument(...),
    version: str = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    include_draft: bool = typer.Option(False, "--include-draft"),
) -> None:
    """Show a SOP version bundle."""
    import json
    try:
        bundle = get_sop(memory_root, sop_name, version, include_draft=include_draft)
    except MlagentError as exc:
        typer.echo(str(exc)); raise typer.Exit(2) from exc
    typer.echo(json.dumps({k: v for k, v in bundle.items() if k != "files"}, indent=2, ensure_ascii=False, default=str))


@app.command("retrain")
def retrain_command(
    sop_name: str = typer.Argument(...),
    version: str = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Load an approved SOP version for strict retraining (reads directly, no skill-router)."""
    import json
    try:
        bundle = get_sop(memory_root, sop_name, version)  # approved only (no include_draft)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    sop = bundle["sop"]
    typer.echo(f"Retraining from: {sop_name}/{version} (approved, immutable)")
    typer.echo(f"Background: {sop.get('background', '')}")
    typer.echo(f"Key params: {json.dumps(sop.get('key_params', {}), default=str)}")
    typer.echo(f"Key optimizations: {', '.join(sop.get('key_optimizations', []))}")
    typer.echo(f"Performance baseline: {json.dumps(sop.get('performance', {}), default=str)}")


@app.command("sync")
def sync_command(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """One-click commit + push (git sync to remote)."""
    try:
        sync_push(memory_root.parent)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"Synced (push): {memory_root.parent}")


@app.command("pull")
def pull_command(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Pull from remote (git pull --ff-only, at boot)."""
    try:
        sync_pull(memory_root.parent)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"Pulled: {memory_root.parent}")


@app.command("assemble-context")
def assemble_context_command(
    prompt: str = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Assemble exploration context (experience injection for explore-train)."""
    import json
    try:
        pack = assemble_context(memory_root, prompt)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(pack, indent=2, ensure_ascii=False, default=str))


def main() -> None:
    try:
        app()
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    main()
