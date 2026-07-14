import json
import subprocess

from src.domain.local_index import LocalIndex
from src.domain.memory_repository import MemoryRepository


def bootstrap_repository(tmp_path):
    repository_path = tmp_path / "team-memory"
    MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    ).bootstrap(repository_path, actor_id="alice")
    experience_path = repository_path / "experiences/experience-1/v1.json"
    experience_path.parent.mkdir(parents=True)
    experience_path.write_text(
        json.dumps(
            {
                "asset_type": "experience",
                "asset_id": "experience-1",
                "version": 1,
                "status": "pending",
                "created_at": "2026-07-14T00:01:00Z",
            }
        )
    )
    return repository_path


def authoritative_bytes(repository_path):
    return {
        str(path.relative_to(repository_path)): path.read_bytes()
        for path in repository_path.rglob("*.json")
        if ".mlagent-local" not in path.parts
    }


def test_deleted_index_rebuilds_without_changing_authoritative_assets(tmp_path):
    repository_path = bootstrap_repository(tmp_path)
    index = LocalIndex(repository_path)
    before = authoritative_bytes(repository_path)

    first = index.rebuild()
    index.path.unlink()
    rebuilt = index.rebuild()

    assert first.asset_count == rebuilt.asset_count == 2
    assert authoritative_bytes(repository_path) == before
    assert [row["asset_id"] for row in index.list_assets()] == [
        "tmr-1",
        "experience-1",
    ]


def test_corrupt_index_is_replaced_from_authoritative_assets(tmp_path):
    repository_path = bootstrap_repository(tmp_path)
    index = LocalIndex(repository_path)
    index.path.parent.mkdir(parents=True)
    index.path.write_bytes(b"not a sqlite database")

    rebuilt = index.rebuild()

    assert rebuilt.asset_count == 2
    assert len(index.list_assets()) == 2


def test_local_index_never_appears_in_git_status(tmp_path):
    repository_path = bootstrap_repository(tmp_path)

    LocalIndex(repository_path).rebuild()

    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert ".mlagent-local" not in result.stdout
