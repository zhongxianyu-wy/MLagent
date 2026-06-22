from pathlib import Path

import typer

from mlagent_memory import __version__
from mlagent_memory.errors import MemoryRepoNotFound
from mlagent_memory.index import rebuild_index, search_index
from mlagent_memory.knowledge import import_knowledge_file
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


@app.command()
def index(memory_root: Path = typer.Option(Path("project_memory"), "--memory-root")) -> None:
    """Rebuild the SQLite FTS5 index."""
    rebuild_index(memory_root)
    typer.echo(f"Rebuilt index: {memory_root / 'indexes' / 'memory.sqlite'}")


@app.command()
def search(
    query: str = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    asset_type: str | None = typer.Option(None, "--asset-type"),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """Search indexed memory assets."""
    hits = search_index(memory_root, query=query, asset_type=asset_type, limit=limit)
    for hit in hits:
        typer.echo(f"{hit['asset_type']} {hit['asset_id']} {hit['source_path']} {hit['title']}")


@app.command("import-knowledge")
def import_knowledge(
    source: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    item_type: str = typer.Option("project_doc", "--type"),
    tag: list[str] = typer.Option([], "--tag"),
) -> None:
    """Import a knowledge file into project_knowledge."""
    item = import_knowledge_file(memory_root, source=source, item_type=item_type, tags=tag)
    typer.echo(f"Imported knowledge: {item.id} {item.stored_path}")


def main() -> None:
    try:
        app()
    except MemoryRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    main()
