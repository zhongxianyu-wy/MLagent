"""Integration tests for notebook reproduction (Issue #9 Phase 2)."""
import json
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.memory_repository import MemoryRepository
from src.domain.models import (
    ImportNotebookCommand,
    ReproduceNotebookCommand,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "notebooks"


def _build_workspace(tmp_path: Path):
    repo_path = tmp_path / "team_memory"
    MemoryRepository(
        id_factory=lambda: "tmr_test",
        clock=lambda: "2026-07-20T00:00:00Z",
    ).bootstrap(repo_path, actor_id="tester")
    conn = tmp_path / ".mlagent_workspace.json"
    conn.write_text(json.dumps({
        "repository_path": str(repo_path),
        "actor_id": "tester",
        "workspace_name": "test",
        "remote_url": None,
    }), encoding="utf-8")
    code_root = tmp_path / "code"
    code_root.mkdir()
    return DomainCore(), conn, repo_path, code_root


def _import(core, conn, repo, nb_name):
    return core.import_notebook(ImportNotebookCommand(
        connection_path=conn,
        notebook_path=FIXTURES / nb_name,
        source_description="test",
        dataset_id="ds1",
        dataset_version="1",
        code_root=repo,
    ))


def test_reproduce_success_creates_instance_link(tmp_path):
    """A clean notebook with a working .py → state=reproduced + instance linked."""
    core, conn, repo, code_root = _build_workspace(tmp_path)

    # create a notebook that actually runs (prints metrics)
    nb_path = tmp_path / "working.ipynb"
    nb_path.write_text(json.dumps({
        "cells": [{
            "cell_type": "code",
            "source": ["import math\n", "print(f'AUC={0.9}')\n"],
            "metadata": {},
            "outputs": [],
            "execution_count": 1,
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }))

    snapshot = core.import_notebook(ImportNotebookCommand(
        connection_path=conn,
        notebook_path=nb_path,
        source_description="working notebook",
        dataset_id="ds1",
        dataset_version="1",
        code_root=repo,
    ))
    assert snapshot.state == "preserved"

    result = core.reproduce_notebook(ReproduceNotebookCommand(
        connection_path=conn,
        asset_id=snapshot.asset_id,
        code_root=code_root,
    ))
    assert result.state == "reproduced"
    assert result.training_instance_id is not None
    assert result.training_run_id is not None

    # extracted code exists
    entrypoint = code_root / "notebook_reproduce.py"
    assert entrypoint.exists()
    assert "print" in entrypoint.read_text()


def test_reproduce_failure_marks_execution_failed(tmp_path):
    """A notebook with a syntax error → state=execution_failed, no instance."""
    core, conn, repo, code_root = _build_workspace(tmp_path)

    nb_path = tmp_path / "broken.ipynb"
    nb_path.write_text(json.dumps({
        "cells": [{
            "cell_type": "code",
            "source": ["import this is not valid python\n"],
            "metadata": {},
            "outputs": [],
            "execution_count": 1,
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }))

    snapshot = core.import_notebook(ImportNotebookCommand(
        connection_path=conn,
        notebook_path=nb_path,
        source_description="broken notebook",
        dataset_id="ds1",
        dataset_version="1",
        code_root=repo,
    ))
    # this notebook has no model/split/randomness → no blocking warnings → preserved
    assert snapshot.state == "preserved"

    result = core.reproduce_notebook(ReproduceNotebookCommand(
        connection_path=conn,
        asset_id=snapshot.asset_id,
        code_root=code_root,
    ))
    assert result.state == "execution_failed"
    assert result.error_code == "execution_error"
    assert result.training_instance_id is None

    # log file exists
    log_path = code_root / "notebook_logs" / f"{snapshot.asset_id}.log"
    assert log_path.exists()


def test_reproduce_blocked_notebook_raises(tmp_path):
    """A parse_blocked notebook cannot be reproduced."""
    core, conn, repo, code_root = _build_workspace(tmp_path)

    snapshot = _import(core, conn, repo, "missing_deps.ipynb")
    assert snapshot.state == "parse_blocked"

    from src.domain.models import WorkspaceError
    with pytest.raises(WorkspaceError, match="Only 'preserved'"):
        core.reproduce_notebook(ReproduceNotebookCommand(
            connection_path=conn,
            asset_id=snapshot.asset_id,
            code_root=code_root,
        ))


def test_reproduce_missing_dependency(tmp_path):
    """A notebook importing a non-existent module → execution_failed."""
    core, conn, repo, code_root = _build_workspace(tmp_path)

    nb_path = tmp_path / "dep_missing.ipynb"
    nb_path.write_text(json.dumps({
        "cells": [{
            "cell_type": "code",
            "source": ["import nonexistent_pkg_xyz\n", "print('hello')\n"],
            "metadata": {},
            "outputs": [],
            "execution_count": 1,
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }))

    snapshot = core.import_notebook(ImportNotebookCommand(
        connection_path=conn,
        notebook_path=nb_path,
        source_description="dep missing",
        dataset_id="ds1",
        dataset_version="1",
        code_root=repo,
    ))
    # nonexistent_pkg_xyz is not in _MISSING_DEP_PACKAGES → not blocking
    assert snapshot.state == "preserved"

    result = core.reproduce_notebook(ReproduceNotebookCommand(
        connection_path=conn,
        asset_id=snapshot.asset_id,
        code_root=code_root,
    ))
    assert result.state == "execution_failed"
    assert result.training_instance_id is None


def test_extract_code_strips_magics(tmp_path):
    """extract_notebook_code removes %magic and !shell lines."""
    from src.domain.notebook_parser import extract_notebook_code

    nb_path = tmp_path / "with_magics.ipynb"
    nb_path.write_text(json.dumps({
        "cells": [{
            "cell_type": "code",
            "source": ["%matplotlib inline\n", "!pip install xgboost\n", "import pandas as pd\n", "print('ok')\n"],
            "metadata": {},
            "outputs": [],
            "execution_count": 1,
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }))

    code = extract_notebook_code(nb_path)
    assert "%matplotlib" not in code
    assert "!pip" not in code
    assert "import pandas" in code
    assert "print('ok')" in code
