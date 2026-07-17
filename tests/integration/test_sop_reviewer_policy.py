import json

import pytest

from src.domain.memory_repository import (
    REVIEWER_POLICY_PATH,
    MemoryRepository,
    load_authorized_reviewers,
)
from src.domain.models import WorkspaceError


def manager() -> MemoryRepository:
    return MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-17T00:00:00Z",
    )


def test_bootstrap_configures_creator_as_authorized_reviewer(tmp_path):
    root = tmp_path / "memory"

    manager().bootstrap(root, actor_id="alice")

    policy = json.loads((root / REVIEWER_POLICY_PATH).read_text())
    assert policy == {
        "asset_id": "reviewer-policy",
        "asset_type": "reviewer_policy",
        "created_at": "2026-07-17T00:00:00Z",
        "created_by": "alice",
        "policy_fingerprint": policy["policy_fingerprint"],
        "reviewer_ids": ["alice"],
        "schema_version": 1,
    }
    assert len(policy["policy_fingerprint"]) == 64
    assert load_authorized_reviewers(root) == ("alice",)


def test_schema_one_repository_without_policy_uses_creator_only(tmp_path):
    root = tmp_path / "memory"
    manager().bootstrap(root, actor_id="alice")
    (root / REVIEWER_POLICY_PATH).unlink()

    assert load_authorized_reviewers(root) == ("alice",)


def test_policy_rejects_tampered_fingerprint(tmp_path):
    root = tmp_path / "memory"
    manager().bootstrap(root, actor_id="alice")
    policy_path = root / REVIEWER_POLICY_PATH
    policy = json.loads(policy_path.read_text())
    policy["reviewer_ids"] = ["alice", "bob"]
    policy_path.write_text(json.dumps(policy))

    with pytest.raises(WorkspaceError) as caught:
        load_authorized_reviewers(root)

    assert caught.value.code == "invalid_reviewer_policy"
    assert "fingerprint" in caught.value.message.lower()


@pytest.mark.parametrize(
    "reviewer_ids",
    (["bob", "alice"], ["alice", "alice"], [], ["alice", ""]),
)
def test_policy_requires_sorted_unique_nonempty_reviewer_ids(
    tmp_path,
    reviewer_ids,
):
    root = tmp_path / "memory"
    manager().bootstrap(root, actor_id="alice")
    policy_path = root / REVIEWER_POLICY_PATH
    policy = json.loads(policy_path.read_text())
    policy["reviewer_ids"] = reviewer_ids
    policy.pop("policy_fingerprint")
    policy["policy_fingerprint"] = MemoryRepository.reviewer_policy_fingerprint(
        policy
    )
    policy_path.write_text(json.dumps(policy))

    with pytest.raises(WorkspaceError) as caught:
        load_authorized_reviewers(root)

    assert caught.value.code == "invalid_reviewer_policy"
    assert "reviewer" in caught.value.message.lower()
