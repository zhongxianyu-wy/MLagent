from pathlib import Path

import typer

from mlagent_memory import __version__
from mlagent_memory.errors import MemoryRepoNotFound

app = typer.Typer(no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the CLI version."""
    typer.echo(f"mlagent-memory {__version__}")


@app.command()
def status(memory_root: Path = typer.Option(Path("project_memory"), "--memory-root")) -> None:
    """Show project memory repo status."""
    try:
        if not memory_root.exists():
            raise MemoryRepoNotFound(f"Project memory repo does not exist: {memory_root}")
        typer.echo(f"Project memory repo: {memory_root}")
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
