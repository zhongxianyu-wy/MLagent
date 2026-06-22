# MLagent MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local-first MLagent Claude Code plugin MVP: project memory repo, lightweight CLI, FTS5 search, knowledge import, raw memory, experience, Context Packs, SkillVersion approval, plugin skills, and conservative hooks.

**Architecture:** Use a file-first Python package under `mlagent_memory/` and expose deterministic operations through `bin/mlagent-memory`. Durable assets live in each project's `project_memory/` as Markdown/YAML/original files; `indexes/memory.sqlite` is rebuildable. Claude Code plugin files live at the repo root with `.claude-plugin/`, `skills/`, `hooks/`, and `bin/`.

**Tech Stack:** Python 3.10+, Typer, Pydantic v2, PyYAML, pypdf, langchain-text-splitters, sqlite-utils, pytest, SQLite FTS5. No vector DB, graph DB, MLflow, DVC, Optuna, workflow orchestrator, or memory runtime.

---

## File Structure

Create these implementation files:

```text
pyproject.toml
mlagent_memory/
  __init__.py
  cli.py
  constants.py
  errors.py
  io.py
  schemas.py
  repo.py
  index.py
  knowledge.py
  raw.py
  experience.py
  context.py
  skill_versions.py
  hooks.py
bin/
  mlagent-memory
.claude-plugin/
  plugin.json
skills/
  start-modeling-session/SKILL.md
  explore-optimization/SKILL.md
  retrain-from-memory/SKILL.md
  distill-run-to-memory/SKILL.md
  promote-memory-to-skill/SKILL.md
hooks/
  hooks.json
  session-start
  post-tool-use
  post-tool-batch
  stop
tests/
  conftest.py
  test_schemas.py
  test_repo.py
  test_index.py
  test_knowledge.py
  test_raw_experience.py
  test_context.py
  test_skill_versions.py
  test_cli.py
```

Responsibilities:

- `schemas.py`: Pydantic models for project profile, knowledge registry items, raw memory, experience, SkillVersion, and Context Packs.
- `io.py`: YAML, Markdown, JSON, hashing, timestamp, and path helpers.
- `repo.py`: initialize and inspect `project_memory/`.
- `index.py`: SQLite FTS5 rebuild and search.
- `knowledge.py`: copy/import TXT, Markdown, and basic PDF knowledge files.
- `raw.py`: write raw memory records.
- `experience.py`: write schema-checked experience records.
- `context.py`: generate exploration, retraining, distillation, and SkillVersion candidate packs.
- `skill_versions.py`: create candidate SkillVersions and approve them after explicit human performance review.
- `hooks.py`: parse hook stdin JSON and call CLI-safe record writers.
- `cli.py`: Typer command surface.
- `bin/mlagent-memory`: plugin PATH wrapper.

## Task 1: Python Package and CLI Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `mlagent_memory/__init__.py`
- Create: `mlagent_memory/constants.py`
- Create: `mlagent_memory/errors.py`
- Create: `mlagent_memory/cli.py`
- Create: `bin/mlagent-memory`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI smoke tests**

Create `tests/test_cli.py`:

```python
from typer.testing import CliRunner

from mlagent_memory.cli import app


runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "mlagent-memory 0.1.0" in result.stdout


def test_cli_status_requires_existing_memory_repo(tmp_path):
    missing = tmp_path / "project_memory"
    result = runner.invoke(app, ["status", "--memory-root", str(missing)])
    assert result.exit_code == 2
    assert "Project memory repo does not exist" in result.stdout
```

- [ ] **Step 2: Run the smoke tests and verify they fail**

Run:

```bash
python -m pytest tests/test_cli.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'mlagent_memory'`.

- [ ] **Step 3: Add package metadata and dependencies**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "mlagent-memory"
version = "0.1.0"
description = "Local-first ML modeling memory system for Claude Code"
requires-python = ">=3.10"
dependencies = [
  "typer>=0.12",
  "pydantic>=2.7",
  "pyyaml>=6.0",
  "pypdf>=5.0",
  "langchain-text-splitters>=0.3",
  "sqlite-utils>=3.36",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
mlagent-memory = "mlagent_memory.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 4: Add initial package files**

Create `mlagent_memory/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `mlagent_memory/constants.py`:

```python
from pathlib import Path

MEMORY_DIRNAME = "project_memory"
DEFAULT_MEMORY_ROOT = Path(MEMORY_DIRNAME)
INDEX_RELATIVE_PATH = Path("indexes") / "memory.sqlite"
```

Create `mlagent_memory/errors.py`:

```python
class MlagentError(Exception):
    """Base error for user-facing MLagent failures."""


class MemoryRepoNotFound(MlagentError):
    """Raised when a command needs an initialized project memory repo."""
```

Create `mlagent_memory/cli.py`:

```python
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
    if not memory_root.exists():
        raise MemoryRepoNotFound(f"Project memory repo does not exist: {memory_root}")
    typer.echo(f"Project memory repo: {memory_root}")


def main() -> None:
    try:
        app()
    except MemoryRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
```

Create `bin/mlagent-memory`:

```python
#!/usr/bin/env python3
from mlagent_memory.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Make the wrapper executable**

Run:

```bash
chmod +x bin/mlagent-memory
```

Expected: exit 0.

- [ ] **Step 6: Run the smoke tests and verify they pass**

Run:

```bash
python -m pytest tests/test_cli.py -q
```

Expected: 2 passed.

- [ ] **Step 7: Commit Task 1**

```bash
git add pyproject.toml mlagent_memory bin tests/test_cli.py
git commit -m "feat: add mlagent memory cli skeleton"
```

## Task 2: Schemas and YAML I/O

**Files:**
- Create: `mlagent_memory/io.py`
- Create: `mlagent_memory/schemas.py`
- Create: `tests/test_schemas.py`

- [ ] **Step 1: Write failing schema and YAML tests**

Create `tests/test_schemas.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from mlagent_memory.io import read_yaml, sha256_file, write_yaml
from mlagent_memory.schemas import ExperienceRecord, RawMemoryRecord, SkillVersion


def test_raw_memory_requires_known_type():
    record = RawMemoryRecord(
        id="raw_20260622_001",
        type="run",
        created_at="2026-06-22T10:00:00+08:00",
        session_id="session_20260622_001",
        goal="Improve AUC",
    )
    assert record.type == "run"


def test_experience_requires_confidence_and_source():
    record = ExperienceRecord(
        id="exp_20260622_001",
        type="pitfall",
        summary="Leakage appeared when target-derived fields were kept.",
        detail="Remove target-derived fields before feature selection.",
        confidence="medium",
        needs_review=True,
        source_raw_records=["raw_memory/runs/raw_20260622_001.yaml"],
        created_at="2026-06-22T10:30:00+08:00",
    )
    assert record.object_type == "experience"


def test_skill_version_rejects_unreviewed_approved_state():
    with pytest.raises(ValidationError):
        SkillVersion(
            version="v001",
            name="baseline",
            object_type="skill_version",
            state="approved",
            source_type="best_run",
            source_evidence=[],
            human_review={"reviewed": False},
            performance={"primary_metric": {"name": "auc", "value": 0.91}},
            reproducibility={"entrypoint": "train.py"},
        )


def test_yaml_round_trip_and_hash(tmp_path):
    path = tmp_path / "record.yaml"
    write_yaml(path, {"id": "abc", "items": [1, 2]})
    assert read_yaml(path) == {"id": "abc", "items": [1, 2]}
    assert len(sha256_file(path)) == 64
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest tests/test_schemas.py -q
```

Expected: FAIL because `mlagent_memory.io` and `mlagent_memory.schemas` do not exist.

- [ ] **Step 3: Implement YAML and hash helpers**

Create `mlagent_memory/io.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

- [ ] **Step 4: Implement Pydantic schemas**

Create `mlagent_memory/schemas.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ProjectProfile(BaseModel):
    project_name: str
    task_type: str = "tabular_ml"
    primary_metric: str = "auc"
    memory_version: str = "0.1.0"


class RawCommand(BaseModel):
    command: str
    summary: str
    status: Literal["success", "failed"]


class RawMemoryRecord(BaseModel):
    id: str
    type: Literal["session", "exploration", "run", "human_note"]
    created_at: str
    session_id: str | None = None
    goal: str | None = None
    hypothesis: str | None = None
    actions: list[str] = Field(default_factory=list)
    changed_files: list[dict[str, str]] = Field(default_factory=list)
    commands: list[RawCommand] = Field(default_factory=list)
    results: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None
    human_interventions: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ExperienceRecord(BaseModel):
    id: str
    type: Literal["lesson", "pitfall", "successful_pattern", "failed_direction"]
    object_type: Literal["experience"] = "experience"
    summary: str
    detail: str
    confidence: Literal["low", "medium", "high"]
    needs_review: bool
    source_raw_records: list[str]
    applies_when: list[str] = Field(default_factory=list)
    avoid_when: list[str] = Field(default_factory=list)
    related_data_fields: list[str] = Field(default_factory=list)
    related_methods: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    superseded_by: str | None = None
    created_at: str


class KnowledgeItem(BaseModel):
    id: str
    type: Literal["project_doc", "paper", "method_note", "data_doc"]
    title: str
    original_filename: str
    stored_path: str
    source_path: str
    sha256: str
    imported_at: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    index_status: Literal["pending", "indexed"] = "pending"


class HumanReview(BaseModel):
    reviewed: bool
    reviewer: str | None = None
    reviewed_at: str | None = None
    approval_note: str | None = None


class SkillVersion(BaseModel):
    version: str
    name: str
    object_type: Literal["skill_version"] = "skill_version"
    state: Literal["draft", "pending_review", "approved", "rejected", "archived"]
    source_type: Literal["best_run", "ipynb_import"]
    source_evidence: list[str]
    artifacts: list[dict[str, str]] = Field(default_factory=list)
    requirements: dict[str, Any] = Field(default_factory=dict)
    human_review: HumanReview
    performance: dict[str, Any]
    reproducibility: dict[str, Any]
    valid_from: str | None = None
    superseded_by: str | None = None

    @model_validator(mode="after")
    def approved_requires_review(self) -> "SkillVersion":
        if self.state == "approved" and not self.human_review.reviewed:
            raise ValueError("approved SkillVersion requires human_review.reviewed=true")
        return self


class ContextPack(BaseModel):
    pack_type: Literal["exploration", "retraining", "distillation", "skill_candidate"]
    prompt: str
    sections: list[dict[str, Any]]
```

- [ ] **Step 5: Run schema tests and verify they pass**

Run:

```bash
python -m pytest tests/test_schemas.py -q
```

Expected: 4 passed.

- [ ] **Step 6: Commit Task 2**

```bash
git add mlagent_memory/io.py mlagent_memory/schemas.py tests/test_schemas.py
git commit -m "feat: add memory schemas and yaml io"
```

## Task 3: Project Memory Repo Init and Status

**Files:**
- Create: `mlagent_memory/repo.py`
- Modify: `mlagent_memory/cli.py`
- Create: `tests/test_repo.py`

- [ ] **Step 1: Write failing repo initialization tests**

Create `tests/test_repo.py`:

```python
from mlagent_memory.io import read_yaml
from mlagent_memory.repo import init_memory_repo, memory_status


def test_init_memory_repo_creates_standard_structure(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")

    expected_dirs = [
        "project_profile",
        "data_understanding",
        "project_knowledge/docs",
        "project_knowledge/papers",
        "project_knowledge/notes",
        "project_knowledge/originals",
        "raw_memory/sessions",
        "raw_memory/explorations",
        "raw_memory/runs",
        "raw_memory/human_notes",
        "experience/lessons",
        "experience/pitfalls",
        "experience/successful_patterns",
        "experience/failed_directions",
        "skill_versions",
        "indexes",
    ]
    for relative in expected_dirs:
        assert (root / relative).is_dir()

    profile = read_yaml(root / "project_profile/project.yaml")
    assert profile["project_name"] == "demo"
    assert profile["primary_metric"] == "auc"
    assert (root / "skill_versions/registry.yaml").exists()


def test_memory_status_counts_assets(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    status = memory_status(root)
    assert status["project_name"] == "demo"
    assert status["raw_memory_count"] == 0
    assert status["experience_count"] == 0
    assert status["skill_version_count"] == 0
```

- [ ] **Step 2: Run repo tests and verify they fail**

Run:

```bash
python -m pytest tests/test_repo.py -q
```

Expected: FAIL because `mlagent_memory.repo` does not exist.

- [ ] **Step 3: Implement repo initialization**

Create `mlagent_memory/repo.py`:

```python
from __future__ import annotations

from pathlib import Path

from mlagent_memory.io import read_yaml, write_text, write_yaml


STANDARD_DIRS = [
    "project_profile",
    "data_understanding",
    "project_knowledge/docs",
    "project_knowledge/papers",
    "project_knowledge/notes",
    "project_knowledge/originals",
    "raw_memory/sessions",
    "raw_memory/explorations",
    "raw_memory/runs",
    "raw_memory/human_notes",
    "experience/lessons",
    "experience/pitfalls",
    "experience/successful_patterns",
    "experience/failed_directions",
    "skill_versions",
    "indexes",
]


def init_memory_repo(root: Path, project_name: str, primary_metric: str) -> None:
    for relative in STANDARD_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)

    write_yaml(
        root / "project_profile/project.yaml",
        {
            "project_name": project_name,
            "task_type": "tabular_ml",
            "primary_metric": primary_metric,
            "memory_version": "0.1.0",
        },
    )
    write_text(root / "project_profile/objectives.md", f"# {project_name} Objectives\n")
    write_text(root / "data_understanding/dataset_card.md", "# Dataset Card\n")
    write_yaml(root / "data_understanding/schema.yaml", {"fields": []})
    write_text(root / "data_understanding/label_definition.md", "# Label Definition\n")
    write_yaml(root / "data_understanding/data_versions.yaml", {"versions": []})
    write_yaml(root / "project_knowledge/registry.yaml", {"items": []})
    write_yaml(root / "skill_versions/registry.yaml", {"versions": []})


def require_memory_repo(root: Path) -> None:
    if not root.exists():
        from mlagent_memory.errors import MemoryRepoNotFound

        raise MemoryRepoNotFound(f"Project memory repo does not exist: {root}")
    if not (root / "project_profile/project.yaml").exists():
        from mlagent_memory.errors import MemoryRepoNotFound

        raise MemoryRepoNotFound(f"Invalid project memory repo: {root}")


def _count_yaml(root: Path, relative: str) -> int:
    folder = root / relative
    if not folder.exists():
        return 0
    return sum(1 for path in folder.rglob("*.yaml") if path.is_file())


def memory_status(root: Path) -> dict[str, object]:
    require_memory_repo(root)
    profile = read_yaml(root / "project_profile/project.yaml")
    registry = read_yaml(root / "skill_versions/registry.yaml")
    return {
        "project_name": profile["project_name"],
        "primary_metric": profile["primary_metric"],
        "raw_memory_count": _count_yaml(root, "raw_memory"),
        "experience_count": _count_yaml(root, "experience"),
        "skill_version_count": len(registry.get("versions", [])),
    }
```

- [ ] **Step 4: Wire init and status into CLI**

Modify `mlagent_memory/cli.py`:

```python
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
    data = memory_status(memory_root)
    typer.echo(f"Project: {data['project_name']}")
    typer.echo(f"Primary metric: {data['primary_metric']}")
    typer.echo(f"Raw memory records: {data['raw_memory_count']}")
    typer.echo(f"Experience records: {data['experience_count']}")
    typer.echo(f"Skill versions: {data['skill_version_count']}")


def main() -> None:
    try:
        app()
    except MemoryRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
```

- [ ] **Step 5: Update CLI tests for new status output**

Modify `tests/test_cli.py`:

```python
from typer.testing import CliRunner

from mlagent_memory.cli import app


runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "mlagent-memory 0.1.0" in result.stdout


def test_cli_status_requires_existing_memory_repo(tmp_path):
    missing = tmp_path / "project_memory"
    result = runner.invoke(app, ["status", "--memory-root", str(missing)])
    assert result.exit_code == 2
    assert "Project memory repo does not exist" in result.stdout


def test_cli_init_then_status(tmp_path):
    root = tmp_path / "project_memory"
    init_result = runner.invoke(
        app,
        [
            "init",
            "--memory-root",
            str(root),
            "--project-name",
            "demo",
            "--primary-metric",
            "auc",
        ],
    )
    assert init_result.exit_code == 0

    status_result = runner.invoke(app, ["status", "--memory-root", str(root)])
    assert status_result.exit_code == 0
    assert "Project: demo" in status_result.stdout
    assert "Skill versions: 0" in status_result.stdout
```

- [ ] **Step 6: Run repo and CLI tests**

Run:

```bash
python -m pytest tests/test_repo.py tests/test_cli.py -q
```

Expected: 5 passed.

- [ ] **Step 7: Commit Task 3**

```bash
git add mlagent_memory/repo.py mlagent_memory/cli.py tests/test_repo.py tests/test_cli.py
git commit -m "feat: initialize project memory repos"
```

## Task 4: SQLite FTS5 Index and Search

**Files:**
- Create: `mlagent_memory/index.py`
- Modify: `mlagent_memory/cli.py`
- Create: `tests/test_index.py`

- [ ] **Step 1: Write failing FTS index tests**

Create `tests/test_index.py`:

```python
from mlagent_memory.index import rebuild_index, search_index
from mlagent_memory.io import write_text, write_yaml
from mlagent_memory.repo import init_memory_repo


def test_rebuild_index_and_search_experience(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_yaml(
        root / "experience/pitfalls/exp_001.yaml",
        {
            "id": "exp_001",
            "type": "pitfall",
            "object_type": "experience",
            "summary": "Target leakage from post outcome fields",
            "detail": "Remove post outcome fields before training.",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-06-22T10:00:00+08:00",
        },
    )

    rebuild_index(root)
    hits = search_index(root, "leakage", asset_type="experience")
    assert len(hits) == 1
    assert hits[0]["asset_id"] == "exp_001"


def test_rebuild_index_and_search_knowledge_note(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_text(root / "project_knowledge/notes/know_001.md", "# Transformer\nAttention method note")

    rebuild_index(root)
    hits = search_index(root, "attention", asset_type="knowledge")
    assert len(hits) == 1
    assert hits[0]["asset_type"] == "knowledge"
```

- [ ] **Step 2: Run index tests and verify they fail**

Run:

```bash
python -m pytest tests/test_index.py -q
```

Expected: FAIL because `mlagent_memory.index` does not exist.

- [ ] **Step 3: Implement FTS5 index rebuild and search**

Create `mlagent_memory/index.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlite_utils import Database

from mlagent_memory.constants import INDEX_RELATIVE_PATH
from mlagent_memory.io import read_text, read_yaml
from mlagent_memory.repo import require_memory_repo


def fts5_available() -> bool:
    with sqlite3.connect(":memory:") as conn:
        options = {row[0] for row in conn.execute("PRAGMA compile_options")}
    return "ENABLE_FTS5" in options


def _index_path(root: Path) -> Path:
    return root / INDEX_RELATIVE_PATH


def _collect_documents(root: Path) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []

    for path in (root / "experience").rglob("*.yaml"):
        data = read_yaml(path)
        docs.append(
            {
                "asset_id": str(data["id"]),
                "asset_type": "experience",
                "source_path": str(path.relative_to(root)),
                "title": str(data.get("summary", data["id"])),
                "content": f"{data.get('summary', '')}\n{data.get('detail', '')}",
            }
        )

    for path in (root / "project_knowledge/notes").rglob("*.md"):
        docs.append(
            {
                "asset_id": path.stem,
                "asset_type": "knowledge",
                "source_path": str(path.relative_to(root)),
                "title": path.stem,
                "content": read_text(path),
            }
        )

    return docs


def rebuild_index(root: Path) -> None:
    require_memory_repo(root)
    if not fts5_available():
        raise RuntimeError("SQLite FTS5 is not available in this Python build")

    index_path = _index_path(root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if index_path.exists():
        index_path.unlink()

    db = Database(index_path)
    db["documents"].create(
        {
            "asset_id": str,
            "asset_type": str,
            "source_path": str,
            "title": str,
            "content": str,
        },
        pk=("asset_id", "asset_type"),
    )
    documents = _collect_documents(root)
    if documents:
        db["documents"].insert_all(documents, pk=("asset_id", "asset_type"), replace=True)
    db["documents"].enable_fts(["title", "content"], create_triggers=True)


def search_index(root: Path, query: str, asset_type: str | None = None, limit: int = 10) -> list[dict[str, str]]:
    require_memory_repo(root)
    db = Database(_index_path(root))
    where = "asset_type = ?" if asset_type else None
    where_args = [asset_type] if asset_type else None
    rows = db["documents"].search(query, where=where, where_args=where_args, limit=limit)
    return [dict(row) for row in rows]
```

- [ ] **Step 4: Add CLI commands for index and search**

Modify `mlagent_memory/cli.py` by adding imports:

```python
from mlagent_memory.index import rebuild_index, search_index
```

Add commands before `main()`:

```python
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
```

- [ ] **Step 5: Run index tests**

Run:

```bash
python -m pytest tests/test_index.py -q
```

Expected: 2 passed.

- [ ] **Step 6: Run full current test suite**

Run:

```bash
python -m pytest -q
```

Expected: all current tests passed.

- [ ] **Step 7: Commit Task 4**

```bash
git add mlagent_memory/index.py mlagent_memory/cli.py tests/test_index.py
git commit -m "feat: add sqlite fts memory index"
```

## Task 5: Knowledge Import

**Files:**
- Create: `mlagent_memory/knowledge.py`
- Modify: `mlagent_memory/index.py`
- Modify: `mlagent_memory/cli.py`
- Create: `tests/test_knowledge.py`

- [ ] **Step 1: Write failing knowledge import tests**

Create `tests/test_knowledge.py`:

```python
from mlagent_memory.io import read_yaml
from mlagent_memory.knowledge import import_knowledge_file
from mlagent_memory.repo import init_memory_repo


def test_import_markdown_copies_original_and_creates_note(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    source = tmp_path / "method.md"
    source.write_text("# Method\nFeature selection notes", encoding="utf-8")

    item = import_knowledge_file(root, source, item_type="method_note", tags=["feature"])

    assert item.type == "method_note"
    assert (root / item.stored_path).exists()
    assert (root / "project_knowledge/notes" / f"{item.id}.md").exists()
    registry = read_yaml(root / "project_knowledge/registry.yaml")
    assert registry["items"][0]["id"] == item.id


def test_import_rejects_unsupported_suffix(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    source = tmp_path / "data.xlsx"
    source.write_text("binary", encoding="utf-8")

    try:
        import_knowledge_file(root, source, item_type="data_doc", tags=[])
    except ValueError as exc:
        assert "Unsupported knowledge file type" in str(exc)
    else:
        raise AssertionError("Expected unsupported file type failure")
```

- [ ] **Step 2: Run knowledge tests and verify they fail**

Run:

```bash
python -m pytest tests/test_knowledge.py -q
```

Expected: FAIL because `mlagent_memory.knowledge` does not exist.

- [ ] **Step 3: Implement knowledge import**

Create `mlagent_memory/knowledge.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2

from pypdf import PdfReader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from mlagent_memory.io import read_text, read_yaml, sha256_file, write_text, write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import KnowledgeItem


SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        return read_text(path)
    if suffix == ".pdf":
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"Unsupported knowledge file type: {path.suffix}")


def _split_text(path: Path, text: str) -> list[str]:
    if path.suffix.lower() in {".md", ".markdown"}:
        splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")])
        documents = splitter.split_text(text)
        return [doc.page_content for doc in documents if doc.page_content.strip()]
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def import_knowledge_file(root: Path, source: Path, item_type: str, tags: list[str]) -> KnowledgeItem:
    require_memory_repo(root)
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported knowledge file type: {source.suffix}")

    digest = sha256_file(source)
    stored_name = f"{digest[:12]}_{source.name}"
    stored_path = root / "project_knowledge/originals" / stored_name
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    copy2(source, stored_path)

    text = _extract_text(stored_path)
    chunks = _split_text(stored_path, text)
    item_id = f"know_{digest[:12]}"
    summary = (chunks[0][:240] if chunks else "").replace("\n", " ").strip()

    note_path = root / "project_knowledge/notes" / f"{item_id}.md"
    write_text(
        note_path,
        "\n".join(
            [
                f"# {source.stem}",
                "",
                f"- id: {item_id}",
                f"- type: {item_type}",
                f"- source: {source}",
                f"- sha256: {digest}",
                "",
                "## Summary",
                summary,
                "",
                "## Extracted Text",
                text,
            ]
        ),
    )

    item = KnowledgeItem(
        id=item_id,
        type=item_type,
        title=source.stem,
        original_filename=source.name,
        stored_path=str(stored_path.relative_to(root)),
        source_path=str(source),
        sha256=digest,
        imported_at=_now(),
        summary=summary,
        tags=tags,
        index_status="pending",
    )

    registry_path = root / "project_knowledge/registry.yaml"
    registry = read_yaml(registry_path)
    items = [entry for entry in registry.get("items", []) if entry.get("id") != item.id]
    items.append(item.model_dump())
    write_yaml(registry_path, {"items": items})
    return item
```

- [ ] **Step 4: Ensure index collects knowledge notes**

Confirm `mlagent_memory/index.py` already indexes `project_knowledge/notes/*.md`. If it does not, add this exact block inside `_collect_documents`:

```python
    for path in (root / "project_knowledge/notes").rglob("*.md"):
        docs.append(
            {
                "asset_id": path.stem,
                "asset_type": "knowledge",
                "source_path": str(path.relative_to(root)),
                "title": path.stem,
                "content": read_text(path),
            }
        )
```

- [ ] **Step 5: Add CLI import-knowledge command**

Modify `mlagent_memory/cli.py` by adding import:

```python
from mlagent_memory.knowledge import import_knowledge_file
```

Add command before `main()`:

```python
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
```

- [ ] **Step 6: Run knowledge tests**

Run:

```bash
python -m pytest tests/test_knowledge.py -q
```

Expected: 2 passed.

- [ ] **Step 7: Commit Task 5**

```bash
git add mlagent_memory/knowledge.py mlagent_memory/index.py mlagent_memory/cli.py tests/test_knowledge.py
git commit -m "feat: import project knowledge files"
```

## Task 6: Raw Memory and Experience Records

**Files:**
- Create: `mlagent_memory/raw.py`
- Create: `mlagent_memory/experience.py`
- Modify: `mlagent_memory/cli.py`
- Create: `tests/test_raw_experience.py`

- [ ] **Step 1: Write failing raw and experience tests**

Create `tests/test_raw_experience.py`:

```python
from mlagent_memory.experience import add_experience
from mlagent_memory.io import read_yaml
from mlagent_memory.raw import add_raw_memory
from mlagent_memory.repo import init_memory_repo


def test_add_raw_memory_writes_record_to_type_directory(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    record = add_raw_memory(
        root,
        {
            "id": "raw_001",
            "type": "run",
            "created_at": "2026-06-22T10:00:00+08:00",
            "session_id": "session_001",
            "goal": "Improve AUC",
        },
    )
    path = root / "raw_memory/runs/raw_001.yaml"
    assert path.exists()
    assert read_yaml(path)["id"] == record.id


def test_add_experience_writes_record_to_type_directory(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    record = add_experience(
        root,
        {
            "id": "exp_001",
            "type": "lesson",
            "summary": "Remove leakage fields",
            "detail": "Post outcome fields must be excluded.",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-06-22T10:30:00+08:00",
        },
    )
    path = root / "experience/lessons/exp_001.yaml"
    assert path.exists()
    assert read_yaml(path)["id"] == record.id
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest tests/test_raw_experience.py -q
```

Expected: FAIL because `mlagent_memory.raw` and `mlagent_memory.experience` do not exist.

- [ ] **Step 3: Implement raw memory writer**

Create `mlagent_memory/raw.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent_memory.io import write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import RawMemoryRecord


RAW_DIRS = {
    "session": "sessions",
    "exploration": "explorations",
    "run": "runs",
    "human_note": "human_notes",
}


def add_raw_memory(root: Path, data: dict[str, Any]) -> RawMemoryRecord:
    require_memory_repo(root)
    record = RawMemoryRecord(**data)
    relative_dir = RAW_DIRS[record.type]
    write_yaml(root / "raw_memory" / relative_dir / f"{record.id}.yaml", record.model_dump(exclude_none=True))
    return record
```

- [ ] **Step 4: Implement experience writer**

Create `mlagent_memory/experience.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent_memory.io import write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import ExperienceRecord


EXPERIENCE_DIRS = {
    "lesson": "lessons",
    "pitfall": "pitfalls",
    "successful_pattern": "successful_patterns",
    "failed_direction": "failed_directions",
}


def add_experience(root: Path, data: dict[str, Any]) -> ExperienceRecord:
    require_memory_repo(root)
    record = ExperienceRecord(**data)
    relative_dir = EXPERIENCE_DIRS[record.type]
    write_yaml(root / "experience" / relative_dir / f"{record.id}.yaml", record.model_dump(exclude_none=True))
    return record
```

- [ ] **Step 5: Add CLI commands for raw and experience**

Modify `mlagent_memory/cli.py` by adding imports:

```python
from mlagent_memory.experience import add_experience
from mlagent_memory.io import read_yaml
from mlagent_memory.raw import add_raw_memory
```

Add commands before `main()`:

```python
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
```

- [ ] **Step 6: Run raw and experience tests**

Run:

```bash
python -m pytest tests/test_raw_experience.py -q
```

Expected: 2 passed.

- [ ] **Step 7: Commit Task 6**

```bash
git add mlagent_memory/raw.py mlagent_memory/experience.py mlagent_memory/cli.py tests/test_raw_experience.py
git commit -m "feat: add raw memory and experience records"
```

## Task 7: Context Pack Generation

**Files:**
- Create: `mlagent_memory/context.py`
- Modify: `mlagent_memory/cli.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write failing Context Pack tests**

Create `tests/test_context.py`:

```python
from mlagent_memory.context import create_context_pack
from mlagent_memory.experience import add_experience
from mlagent_memory.index import rebuild_index
from mlagent_memory.io import write_text
from mlagent_memory.repo import init_memory_repo


def test_exploration_pack_orders_sections_by_confirmed_priority(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_text(root / "data_understanding/dataset_card.md", "Fields include age and tumor_stage.")
    add_experience(
        root,
        {
            "id": "exp_001",
            "type": "pitfall",
            "summary": "Leakage risk",
            "detail": "Do not keep post outcome fields.",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-06-22T10:30:00+08:00",
        },
    )
    write_text(root / "project_knowledge/notes/know_001.md", "AUC optimization knowledge")
    rebuild_index(root)

    pack = create_context_pack(root, pack_type="exploration", prompt="Improve AUC")
    names = [section["name"] for section in pack.sections]
    assert names[:5] == [
        "current_prompt",
        "data_understanding",
        "experience",
        "project_knowledge",
        "skill_versions",
    ]


def test_retraining_pack_requires_skill_version(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    try:
        create_context_pack(root, pack_type="retraining", prompt="Retrain", skill_version="v999")
    except FileNotFoundError as exc:
        assert "SkillVersion not found" in str(exc)
    else:
        raise AssertionError("Expected missing SkillVersion failure")
```

- [ ] **Step 2: Run Context Pack tests and verify they fail**

Run:

```bash
python -m pytest tests/test_context.py -q
```

Expected: FAIL because `mlagent_memory.context` does not exist.

- [ ] **Step 3: Implement Context Pack generator**

Create `mlagent_memory/context.py`:

```python
from __future__ import annotations

from pathlib import Path

from mlagent_memory.index import search_index
from mlagent_memory.io import read_text, read_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import ContextPack


def _safe_text(path: Path) -> str:
    return read_text(path) if path.exists() else ""


def _skill_versions_list(root: Path) -> list[dict[str, object]]:
    registry_path = root / "skill_versions/registry.yaml"
    if not registry_path.exists():
        return []
    return list(read_yaml(registry_path).get("versions", []))


def _exploration_pack(root: Path, prompt: str) -> ContextPack:
    sections = [
        {"name": "current_prompt", "content": prompt},
        {
            "name": "data_understanding",
            "content": "\n\n".join(
                [
                    _safe_text(root / "data_understanding/dataset_card.md"),
                    _safe_text(root / "data_understanding/label_definition.md"),
                ]
            ).strip(),
        },
        {"name": "experience", "content": search_index(root, prompt, asset_type="experience", limit=5)},
        {"name": "project_knowledge", "content": search_index(root, prompt, asset_type="knowledge", limit=5)},
        {"name": "skill_versions", "content": _skill_versions_list(root)},
    ]
    return ContextPack(pack_type="exploration", prompt=prompt, sections=sections)


def _retraining_pack(root: Path, prompt: str, skill_version: str) -> ContextPack:
    version_dir = root / "skill_versions" / skill_version
    if not version_dir.exists():
        raise FileNotFoundError(f"SkillVersion not found: {skill_version}")
    sections = [
        {"name": "current_prompt", "content": prompt},
        {"name": "skill_version", "content": _safe_text(version_dir / "reproduce.md")},
        {"name": "constraints", "content": _safe_text(version_dir / "constraints.md")},
        {"name": "validation_checklist", "content": _safe_text(version_dir / "validation_checklist.md")},
        {"name": "data_understanding", "content": _safe_text(root / "data_understanding/dataset_card.md")},
    ]
    return ContextPack(pack_type="retraining", prompt=prompt, sections=sections)


def create_context_pack(
    root: Path,
    pack_type: str,
    prompt: str,
    skill_version: str | None = None,
) -> ContextPack:
    require_memory_repo(root)
    if pack_type == "exploration":
        return _exploration_pack(root, prompt)
    if pack_type == "retraining":
        if not skill_version:
            raise ValueError("Retraining Context Pack requires skill_version")
        return _retraining_pack(root, prompt, skill_version)
    if pack_type in {"distillation", "skill_candidate"}:
        return ContextPack(pack_type=pack_type, prompt=prompt, sections=[{"name": "current_prompt", "content": prompt}])
    raise ValueError(f"Unknown context pack type: {pack_type}")
```

- [ ] **Step 4: Add CLI create-context-pack command**

Modify `mlagent_memory/cli.py` by adding imports:

```python
import json
from mlagent_memory.context import create_context_pack
```

Add command before `main()`:

```python
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
```

- [ ] **Step 5: Run Context Pack tests**

Run:

```bash
python -m pytest tests/test_context.py -q
```

Expected: 2 passed.

- [ ] **Step 6: Commit Task 7**

```bash
git add mlagent_memory/context.py mlagent_memory/cli.py tests/test_context.py
git commit -m "feat: generate mlagent context packs"
```

## Task 8: SkillVersion Candidate and Approval

**Files:**
- Create: `mlagent_memory/skill_versions.py`
- Modify: `mlagent_memory/cli.py`
- Create: `tests/test_skill_versions.py`

- [ ] **Step 1: Write failing SkillVersion tests**

Create `tests/test_skill_versions.py`:

```python
from mlagent_memory.io import read_yaml, write_yaml
from mlagent_memory.repo import init_memory_repo
from mlagent_memory.skill_versions import approve_skill_candidate, create_skill_candidate


def test_create_skill_candidate_is_not_approved(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")

    candidate = create_skill_candidate(
        root,
        version="v001_baseline",
        name="baseline",
        source_type="best_run",
        source_evidence=["raw_memory/runs/raw_001.yaml"],
    )

    assert candidate.state == "pending_review"
    path = root / "skill_versions/.candidates/v001_baseline/skill.yaml"
    assert path.exists()
    assert read_yaml(path)["human_review"]["reviewed"] is False


def test_approve_skill_candidate_requires_performance(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(
        root,
        version="v001_baseline",
        name="baseline",
        source_type="ipynb_import",
        source_evidence=["evidence/notebooks/baseline.ipynb"],
    )
    performance_path = tmp_path / "performance.yaml"
    write_yaml(
        performance_path,
        {
            "primary_metric": {"name": "auc", "value": 0.91},
            "benchmark_metric": {"name": "baseline_auc", "value": 0.86},
            "dataset_version": "data_v001",
            "validation_protocol": "holdout",
        },
    )

    approved = approve_skill_candidate(
        root,
        version="v001_baseline",
        reviewer="human",
        approval_note="Performance meets target.",
        performance_path=performance_path,
    )

    assert approved.state == "approved"
    assert (root / "skill_versions/v001_baseline/skill.yaml").exists()
    registry = read_yaml(root / "skill_versions/registry.yaml")
    assert registry["versions"][0]["version"] == "v001_baseline"
```

- [ ] **Step 2: Run SkillVersion tests and verify they fail**

Run:

```bash
python -m pytest tests/test_skill_versions.py -q
```

Expected: FAIL because `mlagent_memory.skill_versions` does not exist.

- [ ] **Step 3: Implement candidate and approval workflow**

Create `mlagent_memory/skill_versions.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import copytree, rmtree

from mlagent_memory.io import read_yaml, write_text, write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import SkillVersion


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_skill_candidate(
    root: Path,
    version: str,
    name: str,
    source_type: str,
    source_evidence: list[str],
) -> SkillVersion:
    require_memory_repo(root)
    candidate_dir = root / "skill_versions/.candidates" / version
    candidate_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "version": version,
        "name": name,
        "object_type": "skill_version",
        "state": "pending_review",
        "source_type": source_type,
        "source_evidence": source_evidence,
        "artifacts": [],
        "requirements": {},
        "human_review": {"reviewed": False},
        "performance": {"primary_metric": {"name": "", "value": 0.0}},
        "reproducibility": {"entrypoint": "", "required_inputs": [], "expected_outputs": []},
        "valid_from": None,
        "superseded_by": None,
    }
    candidate = SkillVersion(**data)
    write_yaml(candidate_dir / "skill.yaml", candidate.model_dump())
    write_text(candidate_dir / "reproduce.md", f"# Reproduce {name}\n")
    write_text(candidate_dir / "constraints.md", "# Constraints\n")
    write_text(candidate_dir / "validation_checklist.md", "# Validation Checklist\n")
    write_yaml(candidate_dir / "source_evidence.yaml", {"source_evidence": source_evidence})
    return candidate


def approve_skill_candidate(
    root: Path,
    version: str,
    reviewer: str,
    approval_note: str,
    performance_path: Path,
) -> SkillVersion:
    require_memory_repo(root)
    candidate_dir = root / "skill_versions/.candidates" / version
    approved_dir = root / "skill_versions" / version
    if not candidate_dir.exists():
        raise FileNotFoundError(f"SkillVersion candidate not found: {version}")
    performance = read_yaml(performance_path)
    data = read_yaml(candidate_dir / "skill.yaml")
    data["state"] = "approved"
    data["human_review"] = {
        "reviewed": True,
        "reviewer": reviewer,
        "reviewed_at": _now(),
        "approval_note": approval_note,
    }
    data["performance"] = performance
    data["valid_from"] = data["human_review"]["reviewed_at"]
    approved = SkillVersion(**data)

    if approved_dir.exists():
        rmtree(approved_dir)
    copytree(candidate_dir, approved_dir)
    write_yaml(approved_dir / "skill.yaml", approved.model_dump(exclude_none=True))
    write_yaml(approved_dir / "performance.yaml", performance)

    registry_path = root / "skill_versions/registry.yaml"
    registry = read_yaml(registry_path)
    versions = [entry for entry in registry.get("versions", []) if entry.get("version") != version]
    versions.append(
        {
            "version": version,
            "name": approved.name,
            "state": approved.state,
            "reviewer": reviewer,
            "reviewed_at": approved.human_review.reviewed_at,
            "primary_metric": performance.get("primary_metric", {}),
        }
    )
    write_yaml(registry_path, {"versions": versions})
    return approved
```

- [ ] **Step 4: Add CLI commands**

Modify `mlagent_memory/cli.py` by adding imports:

```python
from mlagent_memory.skill_versions import approve_skill_candidate, create_skill_candidate
```

Add commands before `main()`:

```python
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
    approved = approve_skill_candidate(memory_root, version, reviewer, approval_note, performance_path)
    typer.echo(f"Approved SkillVersion: {approved.version}")
```

- [ ] **Step 5: Run SkillVersion tests**

Run:

```bash
python -m pytest tests/test_skill_versions.py -q
```

Expected: 2 passed.

- [ ] **Step 6: Commit Task 8**

```bash
git add mlagent_memory/skill_versions.py mlagent_memory/cli.py tests/test_skill_versions.py
git commit -m "feat: add skillversion approval workflow"
```

## Task 9: Claude Code Plugin Manifest and Skills

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `skills/start-modeling-session/SKILL.md`
- Create: `skills/explore-optimization/SKILL.md`
- Create: `skills/retrain-from-memory/SKILL.md`
- Create: `skills/distill-run-to-memory/SKILL.md`
- Create: `skills/promote-memory-to-skill/SKILL.md`

- [ ] **Step 1: Write plugin manifest**

Create `.claude-plugin/plugin.json`:

```json
{
  "name": "mlagent",
  "description": "Project-level machine learning modeling memory and workflow guidance for Claude Code",
  "version": "0.1.0",
  "author": {
    "name": "MLagent"
  },
  "license": "MIT",
  "keywords": ["machine-learning", "memory", "modeling", "claude-code", "skills"]
}
```

- [ ] **Step 2: Add start-modeling-session skill**

Create `skills/start-modeling-session/SKILL.md`:

```markdown
---
description: Use when starting ML modeling work in a project that should use MLagent project memory. Requires choosing a Project Memory Repo before exploration or retraining.
---

# Start Modeling Session

Load only the project manifest and a small startup context.

Procedure:

1. Ask the user to confirm the target `project_memory/` path if it is not explicit.
2. Run `mlagent-memory status --memory-root <path>`.
3. Ask for the current modeling goal or use the user's current prompt.
4. Run `mlagent-memory create-context-pack "<goal>" --pack-type exploration --memory-root <path>`.
5. Treat the returned pack as guidance, not as a replacement for the user's current goal.

Do not load full `raw_memory/` or full project documents during startup.
```

- [ ] **Step 3: Add explore-optimization skill**

Create `skills/explore-optimization/SKILL.md`:

```markdown
---
description: Use when the user asks Claude Code to explore model optimization directions using MLagent memory context.
---

# Explore Optimization

Claude Code performs the modeling exploration. MLagent supplies memory context and records evidence.

Procedure:

1. Preserve the user's current prompt as the highest-priority objective.
2. Run `mlagent-memory create-context-pack "<prompt>" --pack-type exploration --memory-root <path>`.
3. Use context in this order: current prompt, data understanding, high/medium confidence experience, project knowledge, SkillVersion list.
4. Explore through the project code and commands.
5. Record important run summaries through `mlagent-memory add-raw <record.yaml> --memory-root <path>`.

Do not force an existing SkillVersion unless the user explicitly asks for strict retraining.
```

- [ ] **Step 4: Add retrain-from-memory skill**

Create `skills/retrain-from-memory/SKILL.md`:

```markdown
---
description: Use when the user asks to retrain using a specific approved MLagent SkillVersion.
---

# Retrain From Memory

Strict retraining uses an approved SkillVersion as the controlling procedure.

Procedure:

1. Require the user to specify a SkillVersion.
2. Run `mlagent-memory create-context-pack "<prompt>" --pack-type retraining --skill-version <version> --memory-root <path>`.
3. Follow `reproduce.md`, `constraints.md`, and `validation_checklist.md`.
4. Do not apply exploration advice unless the user explicitly asks to optimize while retraining.
5. Record the retraining run through `mlagent-memory add-raw <record.yaml> --memory-root <path>`.

Candidate SkillVersions are not approved retraining assets unless the user explicitly asks to inspect a draft.
```

- [ ] **Step 5: Add distill-run-to-memory skill**

Create `skills/distill-run-to-memory/SKILL.md`:

```markdown
---
description: Use after an ML modeling exploration or retraining session to distill raw records into MLagent experience entries.
---

# Distill Run To Memory

Distill experience from raw memory while keeping source links.

Procedure:

1. Read the current session's relevant `raw_memory/` records.
2. Extract lessons, pitfalls, successful patterns, and failed directions.
3. Assign `confidence` as low, medium, or high.
4. Set `needs_review` to true unless the user explicitly confirms the lesson.
5. Write each entry as YAML and add it with `mlagent-memory add-experience <record.yaml> --memory-root <path>`.

Experience guides future exploration. It is not a strict retraining procedure.
```

- [ ] **Step 6: Add promote-memory-to-skill skill**

Create `skills/promote-memory-to-skill/SKILL.md`:

```markdown
---
description: Use when the user asks to turn a best run or an existing notebook into a new MLagent SkillVersion.
---

# Promote Memory To Skill

Only humans can approve a formal SkillVersion.

Procedure:

1. Confirm whether the source is `best_run` or `ipynb_import`.
2. Generate a candidate with `mlagent-memory create-skill-candidate`.
3. Ask the user to review performance, reproducibility, inputs, outputs, and evidence.
4. Require a performance YAML file before approval.
5. Run `mlagent-memory approve-skill` only after explicit human confirmation.

Claude Code may create candidates. It must not approve a SkillVersion without explicit human review of benchmark performance.
```

- [ ] **Step 7: Validate plugin file paths**

Run:

```bash
test -f .claude-plugin/plugin.json
test -f skills/start-modeling-session/SKILL.md
test -f skills/explore-optimization/SKILL.md
test -f skills/retrain-from-memory/SKILL.md
test -f skills/distill-run-to-memory/SKILL.md
test -f skills/promote-memory-to-skill/SKILL.md
```

Expected: exit 0.

- [ ] **Step 8: Commit Task 9**

```bash
git add .claude-plugin skills
git commit -m "feat: add mlagent plugin skills"
```

## Task 10: Conservative Hooks

**Files:**
- Create: `hooks/hooks.json`
- Create: `hooks/session-start`
- Create: `hooks/post-tool-use`
- Create: `hooks/post-tool-batch`
- Create: `hooks/stop`
- Create: `mlagent_memory/hooks.py`

- [ ] **Step 1: Implement hook helper module**

Create `mlagent_memory/hooks.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path


def read_hook_input() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return data


def hook_output(event_name: str, additional_context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event_name,
                    "additionalContext": additional_context[:10000],
                }
            }
        )
    )


def cwd_memory_root(data: dict) -> Path:
    cwd = Path(data.get("cwd") or ".")
    return cwd / "project_memory"
```

- [ ] **Step 2: Add hooks configuration**

Create `hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/session-start\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/post-tool-use\""
          }
        ]
      }
    ],
    "PostToolBatch": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/post-tool-batch\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/stop\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Add session-start hook**

Create `hooks/session-start`:

```python
#!/usr/bin/env python3
from mlagent_memory.hooks import cwd_memory_root, hook_output, read_hook_input

data = read_hook_input()
root = cwd_memory_root(data)
if root.exists():
    message = f"MLagent project memory detected at {root}. Use /mlagent:start-modeling-session before modeling work."
else:
    message = "MLagent project memory not initialized in this cwd. Run mlagent-memory init when starting a new modeling memory repo."
hook_output("SessionStart", message)
```

- [ ] **Step 4: Add post-tool-use hook**

Create `hooks/post-tool-use`:

```python
#!/usr/bin/env python3
from mlagent_memory.hooks import hook_output, read_hook_input

data = read_hook_input()
tool_name = data.get("tool_name", "unknown")
hook_output("PostToolUse", f"MLagent observed tool use: {tool_name}. Record only meaningful modeling evidence, not full logs.")
```

- [ ] **Step 5: Add post-tool-batch hook**

Create `hooks/post-tool-batch`:

```python
#!/usr/bin/env python3
from mlagent_memory.hooks import hook_output, read_hook_input

data = read_hook_input()
calls = data.get("tool_calls", [])
hook_output("PostToolBatch", f"MLagent observed a tool batch with {len(calls)} calls. Summarize only important modeling changes.")
```

- [ ] **Step 6: Add stop hook**

Create `hooks/stop`:

```python
#!/usr/bin/env python3
from mlagent_memory.hooks import hook_output

hook_output("Stop", "MLagent reminder: distill useful modeling findings into raw_memory and experience before ending the session.")
```

- [ ] **Step 7: Make hook scripts executable**

Run:

```bash
chmod +x hooks/session-start hooks/post-tool-use hooks/post-tool-batch hooks/stop
```

Expected: exit 0.

- [ ] **Step 8: Smoke test hook output JSON**

Run:

```bash
printf '{"cwd":"."}' | hooks/session-start
```

Expected: JSON output containing `hookSpecificOutput` and `SessionStart`.

- [ ] **Step 9: Commit Task 10**

```bash
git add hooks mlagent_memory/hooks.py
git commit -m "feat: add conservative claude code hooks"
```

## Task 11: End-to-End MVP Verification

**Files:**
- Create: `tests/test_cli.py` additions
- Modify: `README.md`

- [ ] **Step 1: Add CLI end-to-end test**

Append to `tests/test_cli.py`:

```python
def test_cli_end_to_end_memory_flow(tmp_path):
    root = tmp_path / "project_memory"
    source = tmp_path / "note.md"
    source.write_text("# AUC\nAvoid leakage", encoding="utf-8")

    assert runner.invoke(app, ["init", "--memory-root", str(root), "--project-name", "demo"]).exit_code == 0
    assert runner.invoke(app, ["import-knowledge", str(source), "--memory-root", str(root), "--type", "method_note"]).exit_code == 0
    assert runner.invoke(app, ["index", "--memory-root", str(root)]).exit_code == 0
    search = runner.invoke(app, ["search", "leakage", "--memory-root", str(root)])
    assert search.exit_code == 0
    assert "knowledge" in search.stdout
```

- [ ] **Step 2: Run the full test suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests passed.

- [ ] **Step 3: Add README usage**

Create `README.md`:

````markdown
# MLagent

MLagent is a local-first Claude Code plugin for project-level machine learning modeling memory.

It does not train models or optimize parameters itself. Claude Code performs exploration and retraining through the project code. MLagent stores memory assets, builds context packs, indexes project knowledge, and governs human-approved SkillVersions.

## MVP Commands

```bash
mlagent-memory init --project-name demo --primary-metric auc
mlagent-memory status
mlagent-memory import-knowledge docs/paper.md --type paper
mlagent-memory index
mlagent-memory search leakage
mlagent-memory create-context-pack "Improve AUC" --pack-type exploration
mlagent-memory create-skill-candidate --version v001_baseline --name baseline --source-type best_run --source-evidence raw_memory/runs/raw_001.yaml
mlagent-memory approve-skill --version v001_baseline --reviewer human --approval-note "Performance meets target" --performance-path performance.yaml
```

## MVP Boundaries

- No vector database by default.
- No graph database.
- No MLflow, DVC, Optuna, or workflow orchestrator.
- No automatic formal SkillVersion approval.
- No full log, full diff, training data, or model binary capture by default.
````

- [ ] **Step 4: Run final verification commands**

Run:

```bash
python -m pytest -q
python -m mlagent_memory.cli version
bin/mlagent-memory version
```

Expected:

```text
all tests passed
mlagent-memory 0.1.0
mlagent-memory 0.1.0
```

- [ ] **Step 5: Commit Task 11**

```bash
git add README.md tests/test_cli.py
git commit -m "test: verify mlagent mvp flow"
```

## Plan Self-Review Checklist

- Spec coverage: The plan covers plugin skeleton, CLI, project memory repo, knowledge import, FTS5, raw memory, experience, Context Packs, SkillVersion approval, skills, hooks, and final verification.
- Research-fit constraints: The plan keeps memory runtimes, vector DBs, graph DBs, ML training frameworks, and workflow orchestrators out of the MVP.
- Approval boundary: SkillVersion approval requires explicit `approve-skill`, reviewer, approval note, and performance YAML.
- Ordering: hooks are implemented after storage and CLI paths exist.
- Test discipline: each implementation task starts with tests or smoke checks and ends with a commit.
