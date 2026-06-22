from pathlib import Path

import typer

from mlagent_memory import __version__
from mlagent_memory.errors import MemoryRepoNotFound
from mlagent_memory.repo import init_memory_repo, memory_status

app = typer.Typer(no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the CLI version."""
    typer.echo(f"mlagent-memory {__version__}")


@app.command()
def init(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    project_name: str = typer.Option(..., "--project-name"),
    primary_metric: str = typer.Option("auc", "--primary-metric"),
) -> None:
    """Create a project memory repo."""
    init_memory_repo(memory_root, project_name=project_name, primary_metric=primary_metric)
    typer.echo(f"Initialized project memory repo: {memory_root}")


@app.command()
def status(memory_root: Path = typer.Option(Path("project_memory"), "--memory-root")) -> None:
    """Show project memory repo status."""
    try:
        data = memory_status(memory_root)
        typer.echo(f"Project: {data['project_name']}")
        typer.echo(f"Primary metric: {data['primary_metric']}")
        typer.echo(f"Raw memory records: {data['raw_memory_count']}")
        typer.echo(f"Experience records: {data['experience_count']}")
        typer.echo(f"Skill versions: {data['skill_version_count']}")
    except MemoryRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc


def main() -> None:
    try:
        app()
    except MemoryRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    main()
