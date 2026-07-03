"""mlagent CLI (Typer).

Deterministic operations live here; workflow judgment lives in the skills.
v0.3 slice-1 skeleton: only `version` for now; subsequent tasks add
init/status/record-raw/distill/convert-to-sop/approve-sop/list-sops/get-sop/
retrain/assemble-context/sync/ui.
"""

from pathlib import Path

import typer

from mlagent import __version__
from mlagent.errors import MlagentError
from mlagent.repo import init_memory_repo, memory_status

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


def main() -> None:
    try:
        app()
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    main()
