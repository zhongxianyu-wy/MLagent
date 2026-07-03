"""Test git sync (push/pull) with a local bare repo as the remote."""
import subprocess
from pathlib import Path

from mlagent.sync import sync_pull, sync_push


def _setup_git_repo(project: Path, bare: Path):
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "test"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "-C", str(project), "remote", "add", "origin", str(bare)], check=True)
    (project / "README").write_text("init")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-q", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(project), "branch", "-M", "main"], check=True)
    subprocess.run(["git", "-C", str(project), "push", "-q", "-u", "origin", "main"], check=True)


def test_sync_push_then_clone_verifies(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    bare = tmp_path / "remote.git"
    _setup_git_repo(project, bare)

    # add memory + push
    (project / "project_memory").mkdir()
    (project / "project_memory/data.yaml").write_text("id: test")
    sync_push(project)

    # clone bare → data present
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    assert (clone / "project_memory/data.yaml").read_text() == "id: test"


def test_sync_pull_no_changes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    bare = tmp_path / "remote.git"
    _setup_git_repo(project, bare)
    # pull (no remote changes → ff-only OK)
    sync_pull(project)
