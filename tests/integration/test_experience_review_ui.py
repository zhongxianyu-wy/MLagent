import hashlib
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.domain.core import DomainCore
from src.domain.models import (
    BootstrapMemoryCommand,
    ReviewExperienceCommand,
)


def test_experience_review_ui_edits_and_approves_with_immutable_history(
    tmp_path,
    monkeypatch,
):
    connection_path = tmp_path / ".mlagent-workspace.json"
    memory_root = tmp_path / "team-memory"
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-17T00:00:00Z",
    )
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=memory_root,
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    seed_pending_experience(memory_root, "experience-pending")
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=5,
    ).run()
    app = app.sidebar.radio[0].set_value("Experience Review").run()

    assert not app.exception
    assert app.subheader[0].value == "Experience Review"
    assert [tab.label for tab in app.tabs] == [
        "Pending (1)",
        "Trusted (0)",
        "Rejected (0)",
        "Conflict (0)",
        "Superseded (0)",
    ]
    assert {area.label for area in app.text_area} >= {
        "Conclusion",
        "Applicability",
        "Recommended action",
        "Failure boundary",
        "Risk",
    }
    evidence_tables = [
        table.value
        for table in app.dataframe
        if "Role" in table.value.columns
    ]
    assert len(evidence_tables) == 1
    assert set(evidence_tables[0]["Role"]) == {
        "dataset",
        "run",
        "training_instance",
        "raw_record",
    }
    assert find_button(app, "Approve") is not None
    assert find_button(app, "Reject") is not None
    assert find_button(app, "Mark conflict") is not None

    conclusion = next(
        area for area in app.text_area if area.label == "Conclusion"
    )
    app = conclusion.set_value("").run()
    app = find_button(app, "Approve").click().run()

    assert not app.exception
    assert any("conclusion" in error.value.lower() for error in app.error)
    assert core.list_experiences(connection_path)[0].state == "pending"

    conclusion = next(
        area for area in app.text_area if area.label == "Conclusion"
    )
    app = conclusion.set_value(
        "Reviewed filtering improved roc_auc under the frozen split."
    ).run()
    app = find_button(app, "Approve").click().run()

    assert not app.exception
    current = core.list_experiences(connection_path)
    assert len(current) == 1
    assert current[0].state == "trusted"
    assert current[0].content.conclusion.startswith("Reviewed filtering")
    history = core.get_experience_history(
        connection_path,
        "experience-pending",
    )
    assert [item.state for item in history] == ["pending", "trusted"]
    assert history[0].evidence == history[1].evidence
    assert [tab.label for tab in app.tabs] == [
        "Pending (0)",
        "Trusted (1)",
        "Rejected (0)",
        "Conflict (0)",
        "Superseded (0)",
    ]
    assert find_button(app, "Supersede") is not None


def test_experience_review_ui_renders_all_governed_state_groups(
    tmp_path,
    monkeypatch,
):
    connection_path = tmp_path / ".mlagent-workspace.json"
    memory_root = tmp_path / "team-memory"
    core = DomainCore(id_factory=lambda: "tmr-state-groups")
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=memory_root,
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    for experience_id in (
        "experience-pending",
        "experience-trusted",
        "experience-rejected",
        "experience-conflict",
        "experience-replacement",
        "experience-superseded",
    ):
        seed_pending_experience(memory_root, experience_id)
    review(core, connection_path, "experience-trusted", "approve")
    review(core, connection_path, "experience-rejected", "reject")
    review(
        core,
        connection_path,
        "experience-conflict",
        "conflict",
        "experience-pending",
    )
    review(core, connection_path, "experience-replacement", "approve")
    review(core, connection_path, "experience-superseded", "approve")
    review(
        core,
        connection_path,
        "experience-superseded",
        "supersede",
        "experience-replacement",
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=5,
    ).run()
    app = app.sidebar.radio[0].set_value("Experience Review").run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "Pending (1)",
        "Trusted (2)",
        "Rejected (1)",
        "Conflict (1)",
        "Superseded (1)",
    ]


def seed_pending_experience(memory_root: Path, experience_id: str) -> None:
    evidence = []
    evidence_specs = (
        (
            "dataset",
            "dataset-1:v1",
            memory_root / "datasets/dataset-1/v0001/manifest.json",
            {
                "asset_type": "dataset_version",
                "asset_id": "dataset-1:v1",
                "dataset_id": "dataset-1",
            },
        ),
        (
            "run",
            "run-1",
            memory_root / "raw-records/evidence/run-1-event-start.json",
            {
                "asset_type": "run_event",
                "asset_id": "event-start",
                "run_id": "run-1",
                "event_type": "run_started",
            },
        ),
        (
            "training_instance",
            "instance-1",
            memory_root / "runs/run-1/instances/instance-1/manifest.json",
            {
                "asset_type": "training_instance",
                "asset_id": "instance-1",
                "run_id": "run-1",
            },
        ),
        (
            "raw_record",
            "event-completed",
            memory_root / "raw-records/evidence/run-1-event-completed.json",
            {
                "asset_type": "run_event",
                "asset_id": "event-completed",
                "run_id": "run-1",
                "event_type": "instance_completed",
            },
        ),
    )
    for role, asset_id, path, payload in evidence_specs:
        write_json(
            path,
            {
                **payload,
                "created_at": "2026-07-17T00:00:00Z",
            },
        )
        evidence.append(
            {
                "role": role,
                "asset_id": asset_id,
                "asset_path": path.relative_to(memory_root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    event_id = f"{experience_id}-pending"
    payload = {
            "asset_type": "experience_event",
            "asset_id": event_id,
            "experience_id": experience_id,
            "schema_version": 1,
            "previous_event_id": None,
            "previous_event_fingerprint": None,
            "state": "pending",
            "content": {
                "conclusion": "Feature filtering improved roc_auc.",
                "applicability": "Same Dataset Version and label definition.",
                "recommended_action": "Retest feature filtering.",
                "failure_boundary": "Observed on one frozen split.",
                "risk": "The improvement may not transfer.",
                "confidence": 0.6,
            },
            "evidence": evidence,
            "extraction_session_id": "session-seed",
            "source_kind": "metric_improvement",
            "relation_type": None,
            "related_experience_id": None,
            "created_at": "2026-07-17T00:00:00Z",
            "created_by": "agent",
            "reviewed_at": None,
            "reviewed_by": None,
            "decision": None,
        }
    payload["event_fingerprint"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    write_json(
        memory_root / "experiences" / experience_id / f"{event_id}.json",
        payload,
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def find_button(app, label):
    return next(button for button in app.button if button.label == label)


def review(core, connection_path, experience_id, decision, related=None):
    current = next(
        item
        for item in core.list_experiences(connection_path)
        if item.asset_id == experience_id
    )
    return core.review_experience(
        ReviewExperienceCommand(
            connection_path=connection_path,
            experience_id=experience_id,
            decision=decision,
            content=current.content,
            related_experience_id=related,
        )
    )
