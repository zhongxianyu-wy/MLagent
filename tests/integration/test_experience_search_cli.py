import json
from dataclasses import dataclass
from pathlib import Path

from src.agent.main import main


@dataclass(frozen=True)
class StubSearchResult:
    experience_id: str
    state: str
    why_applicable: str

    def to_dict(self):
        return {
            "experience": {
                "asset_id": self.experience_id,
                "state": self.state,
            },
            "why_applicable": self.why_applicable,
            "score": 4,
        }


class SearchCore:
    call = None

    def search_experiences(
        self,
        connection_path,
        query,
        *,
        dataset_id,
        include_pending,
        top_k,
    ):
        type(self).call = {
            "connection_path": connection_path,
            "query": query,
            "dataset_id": dataset_id,
            "include_pending": include_pending,
            "top_k": top_k,
        }
        return (
            (
                StubSearchResult(
                    "experience-trusted",
                    "trusted",
                    "Dataset and metric match.",
                ),
            ),
            (
                StubSearchResult(
                    "experience-pending",
                    "pending",
                    "Optimization direction matches.",
                ),
            ),
        )


def test_experience_search_cli_returns_separate_confidence_groups(capsys):
    exit_code = main(
        [
            "experience",
            "search",
            "--query",
            "feature filtering roc_auc",
            "--dataset-id",
            "ds-1",
            "--include-pending",
            "--top-k",
            "7",
            "--workspace-config",
            "workspace.json",
        ],
        domain_core_factory=SearchCore,
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["trusted"][0]["experience"]["state"] == "trusted"
    assert output["pending"][0]["experience"]["state"] == "pending"
    assert output["trusted"][0]["why_applicable"]
    assert str(SearchCore.call["connection_path"]) == "workspace.json"
    assert SearchCore.call["query"] == "feature filtering roc_auc"
    assert SearchCore.call["dataset_id"] == "ds-1"
    assert SearchCore.call["include_pending"] is True
    assert SearchCore.call["top_k"] == 7


def test_design_skill_retrieves_experience_before_recording_plan():
    skill = Path(".claude/skills/design-and-explore/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "experience search" in skill
    assert "--include-pending" in skill
    assert "why_applicable" in skill
    assert "current claude code session id" in skill.lower()
