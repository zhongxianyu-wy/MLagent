import json
from pathlib import Path

import typer

from mlagent_memory import __version__
from mlagent_memory.context import create_context_pack
from mlagent_memory.errors import MemoryRepoNotFound, MlagentError
from mlagent_memory.experience import add_experience
from mlagent_memory.index import rebuild_index, search_index
from mlagent_memory.io import read_yaml
from mlagent_memory.knowledge import import_knowledge_file
from mlagent_memory.raw import add_raw_memory
from mlagent_memory.repo import init_memory_repo, memory_status
from mlagent_memory.skill_versions import approve_skill_candidate, create_skill_candidate, get_skill, list_skills

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


@app.command("add-raw")
def add_raw(
    record_path: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Add a raw memory YAML record."""
    record = add_raw_memory(memory_root, read_yaml(record_path))
    typer.echo(f"Added raw memory: {record.id}")


@app.command("add-experience")
def add_experience_command(
    record_path: Path = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Add an experience YAML record."""
    record = add_experience(memory_root, read_yaml(record_path))
    typer.echo(f"Added experience: {record.id}")


@app.command("create-context-pack")
def create_context_pack_command(
    prompt: str = typer.Argument(...),
    pack_type: str = typer.Option("exploration", "--pack-type"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    skill_version: str | None = typer.Option(None, "--skill-version"),
) -> None:
    """Create a task-specific Context Pack."""
    pack = create_context_pack(memory_root, pack_type=pack_type, prompt=prompt, skill_version=skill_version)
    typer.echo(json.dumps(pack.model_dump(), indent=2, ensure_ascii=True))


@app.command("create-skill-candidate")
def create_skill_candidate_command(
    version: str = typer.Option(..., "--version"),
    name: str = typer.Option(..., "--name"),
    source_type: str = typer.Option(..., "--source-type"),
    source_evidence: list[str] = typer.Option([], "--source-evidence"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Create a pending SkillVersion candidate."""
    candidate = create_skill_candidate(memory_root, version, name, source_type, source_evidence)
    typer.echo(f"Created SkillVersion candidate: {candidate.version}")


@app.command("approve-skill")
def approve_skill_command(
    version: str = typer.Option(..., "--version"),
    reviewer: str = typer.Option(..., "--reviewer"),
    approval_note: str = typer.Option(..., "--approval-note"),
    performance_path: Path = typer.Option(..., "--performance-path"),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """Approve a SkillVersion candidate after human performance review."""
    try:
        approved = approve_skill_candidate(memory_root, version, reviewer, approval_note, performance_path)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(f"Approved SkillVersion: {approved.version}")


@app.command("list-skills")
def list_skills_command(
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
) -> None:
    """List approved SkillVersions from the registry."""
    versions = list_skills(memory_root)
    if not versions:
        typer.echo("No approved SkillVersions.")
        return
    for entry in versions:
        metric = entry.get("primary_metric", {}) or {}
        typer.echo(
            f"{entry.get('version')} | {entry.get('state')} | {entry.get('name')} | "
            f"reviewer={entry.get('reviewer')} | {metric.get('name')}={metric.get('value')}"
        )


@app.command("get-skill")
def get_skill_command(
    version: str = typer.Argument(...),
    memory_root: Path = typer.Option(Path("project_memory"), "--memory-root"),
    include_draft: bool = typer.Option(False, "--include-draft"),
) -> None:
    """Show a SkillVersion bundle. Approved by default; --include-draft for candidates."""
    try:
        bundle = get_skill(memory_root, version, include_draft=include_draft)
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(bundle, indent=2, ensure_ascii=True))


def main() -> None:
    try:
        app()
    except MlagentError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    main()
