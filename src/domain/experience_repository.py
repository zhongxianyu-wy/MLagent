from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.models import (
    CapacityStatus,
    ExperienceContent,
    ExperienceEvidence,
    ExperienceSearchResult,
    ExperienceSnapshot,
    ReviewExperienceCommand,
    SessionExperienceOutcome,
    WorkspaceError,
)


EXPERIENCE_SCHEMA_VERSION = 1
EXPERIENCE_ROOT = Path("experiences")
SESSION_ROOT = Path("raw-records/sessions")
RUN_EVENT_ROOT = Path("raw-records/runs")
RUN_ROOT = Path("runs")
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
ALLOWED_TRANSITIONS = {
    "pending": frozenset({"approve", "reject", "conflict"}),
    "conflict": frozenset({"approve", "reject"}),
    "trusted": frozenset({"supersede"}),
    "rejected": frozenset(),
    "superseded": frozenset(),
}
DECISION_STATE = {
    "approve": "trusted",
    "reject": "rejected",
    "conflict": "conflict",
    "supersede": "superseded",
}
DECISION_RELATION = {
    "conflict": "conflicts_with",
    "supersede": "superseded_by",
}


class ExperienceRepository:
    def __init__(
        self,
        repository_path: Path,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.repository_path = repository_path.expanduser().resolve()
        self.clock = clock or _utc_now

    def start_session(
        self,
        session_id: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> SessionExperienceOutcome:
        self._validate_id(session_id, "session ID")
        self._validate_actor(actor_id)
        relative = SESSION_ROOT / session_id / "start.json"
        target = self.repository_path / relative
        with self._lock():
            if not target.exists():
                payload = {
                    "asset_type": "experience_session_start",
                    "asset_id": f"experience-session-start:{session_id}",
                    "schema_version": EXPERIENCE_SCHEMA_VERSION,
                    "session_id": session_id,
                    "baseline_event_ids": sorted(self._run_events()),
                    "baseline_instance_ids": sorted(self._instances()),
                    "created_at": self._timestamp(),
                    "created_by": actor_id,
                }
                self._write_new(relative, payload, capacity)
            else:
                self._load_session_start(session_id)
        return SessionExperienceOutcome(
            session_id=session_id,
            outcome="started",
            candidate_ids=(),
            new_event_ids=(),
            new_instance_ids=(),
            pending_review_count=self.pending_count(),
            sync=None,
        )

    def complete_session(
        self,
        session_id: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> SessionExperienceOutcome:
        self._validate_id(session_id, "session ID")
        self._validate_actor(actor_id)
        with self._lock():
            stop_path = self.repository_path / SESSION_ROOT / session_id / "stop.json"
            if stop_path.exists():
                self._load_session_stop(session_id)
                return SessionExperienceOutcome(
                    session_id=session_id,
                    outcome="already_completed",
                    candidate_ids=(),
                    new_event_ids=(),
                    new_instance_ids=(),
                    pending_review_count=self.pending_count(),
                    sync=None,
                )
            start = self._load_session_start(session_id)
            events = self._run_events()
            instances = self._instances()
            new_event_ids = tuple(
                sorted(set(events) - set(start["baseline_event_ids"]))
            )
            new_instance_ids = tuple(
                sorted(set(instances) - set(start["baseline_instance_ids"]))
            )
            candidate_ids = []
            for instance_id in new_instance_ids:
                candidate = self._extract_candidate(
                    session_id,
                    instance_id,
                    new_event_ids,
                    events,
                    instances,
                    actor_id,
                    capacity,
                )
                if candidate is not None:
                    candidate_ids.append(candidate.asset_id)
            outcome = "created" if candidate_ids else "no_op"
            payload = {
                "asset_type": "experience_session_stop",
                "asset_id": f"experience-session-stop:{session_id}",
                "schema_version": EXPERIENCE_SCHEMA_VERSION,
                "session_id": session_id,
                "outcome": outcome,
                "candidate_ids": candidate_ids,
                "new_event_ids": list(new_event_ids),
                "new_instance_ids": list(new_instance_ids),
                "created_at": self._timestamp(),
                "created_by": actor_id,
            }
            self._write_new(
                SESSION_ROOT / session_id / "stop.json",
                payload,
                capacity,
            )
        return SessionExperienceOutcome(
            session_id=session_id,
            outcome=outcome,
            candidate_ids=tuple(candidate_ids),
            new_event_ids=new_event_ids,
            new_instance_ids=new_instance_ids,
            pending_review_count=self.pending_count(),
            sync=None,
        )

    def current(self, experience_id: str) -> ExperienceSnapshot:
        history = self.history(experience_id)
        return history[-1]

    def history(
        self,
        experience_id: str,
    ) -> tuple[ExperienceSnapshot, ...]:
        self._validate_id(experience_id, "Experience ID")
        family = self.repository_path / EXPERIENCE_ROOT / experience_id
        self._validate_path(family)
        if not family.is_dir():
            raise WorkspaceError(
                code="experience_not_found",
                message=f"Experience does not exist: {experience_id}.",
                next_action="Select an Experience from the current Team Memory index.",
            )
        events = [
            self._load_experience(path, experience_id)
            for path in sorted(family.glob("*.json"))
        ]
        if not events:
            self._invalid_experience(experience_id)
        by_id = {event.event_id: event for event in events}
        if len(by_id) != len(events):
            self._invalid_experience(experience_id)
        roots = [event for event in events if event.previous_event_id is None]
        predecessors = {
            event.previous_event_id
            for event in events
            if event.previous_event_id is not None
        }
        heads = [event for event in events if event.event_id not in predecessors]
        if len(roots) != 1 or len(heads) != 1:
            raise WorkspaceError(
                code="experience_conflict",
                message=f"Experience history has concurrent heads: {experience_id}.",
                next_action="Restore or reconcile the Experience event history.",
            )
        reverse = []
        visited = set()
        cursor: ExperienceSnapshot | None = heads[0]
        while cursor is not None:
            if cursor.event_id in visited:
                self._invalid_experience(experience_id)
            visited.add(cursor.event_id)
            reverse.append(cursor)
            predecessor = cursor.previous_event_id
            if predecessor is None:
                cursor = None
            elif predecessor not in by_id:
                self._invalid_experience(experience_id)
            else:
                cursor = by_id[predecessor]
        if len(visited) != len(events) or reverse[-1].state != "pending":
            self._invalid_experience(experience_id)
        return tuple(reversed(reverse))

    def list_current(
        self,
        states: tuple[str, ...] | None = None,
    ) -> tuple[ExperienceSnapshot, ...]:
        root = self.repository_path / EXPERIENCE_ROOT
        self._validate_path(root)
        if not root.is_dir():
            return ()
        selected = set(states) if states is not None else None
        items = []
        for family in sorted(root.iterdir()):
            if not family.is_dir() or SAFE_ID_PATTERN.fullmatch(family.name) is None:
                raise WorkspaceError(
                    code="invalid_experience",
                    message="Experience directory contains an invalid identity.",
                    next_action="Restore the Experience assets from Git.",
                )
            current = self.current(family.name)
            if selected is None or current.state in selected:
                items.append(current)
        return tuple(
            sorted(
                items,
                key=lambda item: (item.created_at, item.asset_id),
                reverse=True,
            )
        )

    def review(
        self,
        command: ReviewExperienceCommand,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> ExperienceSnapshot:
        self._validate_actor(actor_id)
        with self._lock():
            current = self.current(command.experience_id)
            allowed = ALLOWED_TRANSITIONS[current.state]
            if command.decision not in allowed:
                raise WorkspaceError(
                    code="invalid_experience_transition",
                    message=(
                        f"Experience transition from {current.state} through "
                        f"{command.decision} is not allowed."
                    ),
                    next_action="Choose an action allowed for the current Experience state.",
                )
            related = None
            if command.related_experience_id is not None:
                related = self.current(command.related_experience_id)
                if command.decision == "supersede" and related.state != "trusted":
                    raise WorkspaceError(
                        code="invalid_experience_replacement",
                        message="An Experience can be superseded only by a current Trusted Experience.",
                        next_action="Approve the replacement Experience before superseding the old one.",
                    )
                if command.decision == "conflict" and related.state in {
                    "rejected",
                    "superseded",
                }:
                    raise WorkspaceError(
                        code="invalid_experience_relation",
                        message="A conflict must reference a current reviewable Experience.",
                        next_action="Choose a Pending, Conflict, or Trusted Experience.",
                    )
            reviewed_at = self._timestamp()
            event_id = f"experience-event-{uuid.uuid4()}"
            next_state = DECISION_STATE[command.decision]
            payload = {
                "asset_type": "experience_event",
                "asset_id": event_id,
                "experience_id": current.asset_id,
                "schema_version": EXPERIENCE_SCHEMA_VERSION,
                "previous_event_id": current.event_id,
                "state": next_state,
                "content": command.content.to_dict(),
                "evidence": [item.to_dict() for item in current.evidence],
                "extraction_session_id": current.extraction_session_id,
                "source_kind": current.source_kind,
                "relation_type": DECISION_RELATION.get(command.decision),
                "related_experience_id": (
                    None if related is None else related.asset_id
                ),
                "created_at": reviewed_at,
                "created_by": actor_id,
                "reviewed_at": reviewed_at,
                "reviewed_by": actor_id,
                "decision": command.decision,
            }
            relative = (
                EXPERIENCE_ROOT
                / current.asset_id
                / f"{event_id}.json"
            )
            self._write_new(relative, payload, capacity)
            return self._snapshot(payload, relative)

    def search(
        self,
        query: str,
        *,
        dataset_id: str | None = None,
        include_pending: bool = False,
        top_k: int = 5,
    ) -> tuple[
        tuple[ExperienceSearchResult, ...],
        tuple[ExperienceSearchResult, ...],
    ]:
        if not isinstance(query, str) or not query.strip():
            raise WorkspaceError(
                code="invalid_experience_query",
                message="Experience retrieval requires a non-empty query.",
                next_action="Describe the Dataset, metric, or optimization direction.",
            )
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise WorkspaceError(
                code="invalid_experience_query",
                message="Experience retrieval top_k must be positive.",
                next_action="Use a positive result limit.",
            )
        if dataset_id is not None and (
            not isinstance(dataset_id, str) or not dataset_id.strip()
        ):
            raise WorkspaceError(
                code="invalid_experience_query",
                message="Experience retrieval Dataset ID is invalid.",
                next_action="Use a confirmed Dataset ID or omit the filter.",
            )
        query_terms = _terms(query)
        groups: dict[str, list[ExperienceSearchResult]] = {
            "trusted": [],
            "pending": [],
        }
        states = ("trusted", "pending") if include_pending else ("trusted",)
        for experience in self.list_current(states):
            dataset_evidence = next(
                item
                for item in experience.evidence
                if item.role == "dataset"
            )
            dataset_matches = (
                dataset_id is None
                or dataset_id in dataset_evidence.asset_id
                or dataset_id in dataset_evidence.asset_path
            )
            if not dataset_matches:
                continue
            searchable = " ".join(
                (
                    experience.content.conclusion,
                    experience.content.applicability,
                    experience.content.recommended_action,
                    experience.content.failure_boundary,
                    experience.content.risk,
                    experience.source_kind.replace("_", " "),
                    dataset_evidence.asset_id,
                )
            )
            matched = sorted(query_terms & _terms(searchable))
            if not matched and dataset_id is None:
                continue
            score = len(matched) + (3 if dataset_id is not None else 0)
            reasons = []
            if dataset_id is not None:
                reasons.append(f"Dataset {dataset_id} matches direct evidence")
            if matched:
                reasons.append("matched " + ", ".join(matched[:6]))
            result = ExperienceSearchResult(
                experience=experience,
                why_applicable="; ".join(reasons) + ".",
                score=score,
            )
            groups[experience.state].append(result)
        for values in groups.values():
            values.sort(
                key=lambda item: (
                    item.score,
                    item.experience.created_at,
                    item.experience.asset_id,
                ),
                reverse=True,
            )
        return (
            tuple(groups["trusted"][:top_k]),
            tuple(groups["pending"][:top_k]),
        )

    def pending_count(self) -> int:
        return len(self.list_current(("pending",)))

    def _extract_candidate(
        self,
        session_id: str,
        instance_id: str,
        new_event_ids: tuple[str, ...],
        events: dict[str, tuple[Path, dict[str, Any]]],
        instances: dict[str, tuple[Path, dict[str, Any]]],
        actor_id: str,
        capacity: CapacityStatus,
    ) -> ExperienceSnapshot | None:
        manifest_path, manifest = instances[instance_id]
        parent_id = manifest.get("parent_instance_id")
        if not isinstance(parent_id, str) or parent_id not in instances:
            return None
        state = manifest.get("state")
        if state not in {"completed", "failed"}:
            return None
        parent = instances[parent_id][1]
        source_kind: str
        confidence: float
        metric_name = manifest.get("primary_metric_name")
        direction = manifest.get("optimization_direction")
        if not isinstance(direction, str) or not direction.strip():
            input_payload = self._instance_input(manifest_path)
            direction = input_payload.get("optimization_direction")
        if not isinstance(direction, str) or not direction.strip():
            return None
        direction = " ".join(direction.split())[:500]
        if state == "completed":
            current_value = manifest.get("primary_metric_value")
            parent_value = parent.get("primary_metric_value")
            if (
                isinstance(current_value, bool)
                or isinstance(parent_value, bool)
                or not isinstance(current_value, (int, float))
                or not isinstance(parent_value, (int, float))
                or float(current_value) <= float(parent_value)
                or not isinstance(metric_name, str)
                or not metric_name.strip()
            ):
                return None
            delta = float(current_value) - float(parent_value)
            source_kind = "metric_improvement"
            confidence = min(0.7, 0.5 + delta)
            conclusion = (
                f"{direction} improved {metric_name} from "
                f"{float(parent_value):.6f} to {float(current_value):.6f} "
                f"(+{delta:.6f})."
            )
            recommended = (
                f"Re-evaluate {direction} under matching Dataset and "
                "evaluation conditions."
            )
            failure_boundary = (
                "Observed in one parent-child comparison on one frozen split; "
                "validate before transfer."
            )
            risk = "The measured improvement may depend on this split or Dataset."
        else:
            error_code = manifest.get("error_code")
            error_summary = manifest.get("error_summary")
            if (
                not isinstance(error_code, str)
                or not error_code.strip()
                or not isinstance(error_summary, str)
                or not error_summary.strip()
            ):
                return None
            source_kind = "training_failure"
            confidence = 0.45
            bounded_error = " ".join(error_summary.split())[:1000]
            conclusion = (
                f"{direction} failed with {error_code.strip()[:200]}."
            )
            recommended = (
                f"Check the {error_code.strip()[:200]} boundary before "
                f"reusing {direction}."
            )
            failure_boundary = bounded_error
            risk = "The same configuration may reproduce this training failure."
        terminal = self._terminal_event(
            instance_id,
            state,
            new_event_ids,
            events,
        )
        if terminal is None:
            return None
        terminal_path, terminal_payload = terminal
        run_id = manifest.get("run_id")
        if not isinstance(run_id, str):
            return None
        run_start = self._run_start(run_id, events)
        if run_start is None:
            return None
        run_path, _ = run_start
        input_payload = self._instance_input(manifest_path)
        dataset_relative = input_payload.get("dataset_asset_path")
        if not isinstance(dataset_relative, str):
            return None
        dataset_path = self.repository_path / dataset_relative
        dataset = self._load_json(dataset_path, "invalid_experience_evidence")
        evidence = (
            self._evidence(
                "dataset",
                str(dataset.get("asset_id", "")),
                dataset_path,
            ),
            self._evidence("run", run_id, run_path),
            self._evidence("training_instance", instance_id, manifest_path),
            self._evidence(
                "raw_record",
                str(terminal_payload.get("asset_id", "")),
                terminal_path,
            ),
        )
        evidence_digest = hashlib.sha256(
            json.dumps(
                {
                    "session_id": session_id,
                    "instance_id": instance_id,
                    "raw_event_id": terminal_payload["asset_id"],
                    "source_kind": source_kind,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        experience_id = f"experience-{evidence_digest[:24]}"
        event_id = f"experience-event-{evidence_digest[24:48]}"
        content = ExperienceContent(
            conclusion=conclusion,
            applicability=(
                f"Direct evidence uses Dataset {dataset.get('asset_id')} and "
                f"optimization direction {direction}."
            ),
            recommended_action=recommended,
            failure_boundary=failure_boundary,
            risk=risk,
            confidence=confidence,
        )
        payload = {
            "asset_type": "experience_event",
            "asset_id": event_id,
            "experience_id": experience_id,
            "schema_version": EXPERIENCE_SCHEMA_VERSION,
            "previous_event_id": None,
            "state": "pending",
            "content": content.to_dict(),
            "evidence": [item.to_dict() for item in evidence],
            "extraction_session_id": session_id,
            "source_kind": source_kind,
            "relation_type": None,
            "related_experience_id": None,
            "created_at": self._timestamp(),
            "created_by": actor_id,
            "reviewed_at": None,
            "reviewed_by": None,
            "decision": None,
        }
        relative = EXPERIENCE_ROOT / experience_id / f"{event_id}.json"
        self._write_new(relative, payload, capacity)
        return self._snapshot(payload, relative)

    def _terminal_event(
        self,
        instance_id: str,
        state: str,
        new_event_ids: tuple[str, ...],
        events: dict[str, tuple[Path, dict[str, Any]]],
    ) -> tuple[Path, dict[str, Any]] | None:
        matches = [
            events[event_id]
            for event_id in new_event_ids
            if event_id in events
            and events[event_id][1].get("instance_id") == instance_id
            and events[event_id][1].get("event_type") == f"instance_{state}"
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _run_start(
        run_id: str,
        events: dict[str, tuple[Path, dict[str, Any]]],
    ) -> tuple[Path, dict[str, Any]] | None:
        matches = [
            item
            for item in events.values()
            if item[1].get("run_id") == run_id
            and item[1].get("event_type") == "run_started"
        ]
        return matches[0] if len(matches) == 1 else None

    def _instance_input(self, manifest_path: Path) -> dict[str, Any]:
        return self._load_json(
            manifest_path.parent / "input.json",
            "invalid_experience_evidence",
        )

    def _evidence(
        self,
        role: str,
        asset_id: str,
        path: Path,
    ) -> ExperienceEvidence:
        self._validate_path(path)
        if not asset_id.strip() or not path.is_file():
            self._invalid_evidence(path)
        raw = path.read_bytes()
        return ExperienceEvidence(
            role=role,
            asset_id=asset_id,
            asset_path=path.relative_to(self.repository_path).as_posix(),
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    def _run_events(self) -> dict[str, tuple[Path, dict[str, Any]]]:
        root = self.repository_path / RUN_EVENT_ROOT
        self._validate_path(root)
        result: dict[str, tuple[Path, dict[str, Any]]] = {}
        if not root.is_dir():
            return result
        for path in sorted(root.glob("*/*.json")):
            payload = self._load_json(path, "invalid_run_event")
            event_id = payload.get("asset_id")
            if (
                payload.get("asset_type") != "run_event"
                or not isinstance(event_id, str)
                or not event_id.strip()
                or event_id in result
            ):
                raise WorkspaceError(
                    code="invalid_run_event",
                    message="Run Raw Records contain missing or duplicate event IDs.",
                    next_action="Restore the append-only Run records from Git.",
                )
            result[event_id] = (path, payload)
        return result

    def _instances(self) -> dict[str, tuple[Path, dict[str, Any]]]:
        root = self.repository_path / RUN_ROOT
        self._validate_path(root)
        result: dict[str, tuple[Path, dict[str, Any]]] = {}
        if not root.is_dir():
            return result
        for path in sorted(root.glob("*/instances/*/manifest.json")):
            payload = self._load_json(path, "invalid_training_instance")
            instance_id = payload.get("asset_id")
            if (
                payload.get("asset_type") != "training_instance"
                or not isinstance(instance_id, str)
                or not instance_id.strip()
                or instance_id in result
            ):
                raise WorkspaceError(
                    code="invalid_training_instance",
                    message="Training Instance evidence contains missing or duplicate IDs.",
                    next_action="Restore the sealed Training Instances from Git.",
                )
            result[instance_id] = (path, payload)
        return result

    def _load_session_start(self, session_id: str) -> dict[str, Any]:
        path = self.repository_path / SESSION_ROOT / session_id / "start.json"
        if not path.is_file():
            raise WorkspaceError(
                code="experience_session_not_started",
                message=f"Experience extraction has no SessionStart boundary for {session_id}.",
                next_action="Run SessionStart before retrying Stop extraction.",
            )
        payload = self._load_json(path, "invalid_experience_session")
        if (
            payload.get("asset_type") != "experience_session_start"
            or payload.get("session_id") != session_id
            or not self._id_list(payload.get("baseline_event_ids"))
            or not self._id_list(payload.get("baseline_instance_ids"))
        ):
            raise WorkspaceError(
                code="invalid_experience_session",
                message="Experience SessionStart evidence boundary is invalid.",
                next_action="Restore the session boundary from Git.",
            )
        return payload

    def _load_session_stop(self, session_id: str) -> dict[str, Any]:
        path = self.repository_path / SESSION_ROOT / session_id / "stop.json"
        payload = self._load_json(path, "invalid_experience_session")
        if (
            payload.get("asset_type") != "experience_session_stop"
            or payload.get("session_id") != session_id
            or payload.get("outcome") not in {"created", "no_op"}
        ):
            raise WorkspaceError(
                code="invalid_experience_session",
                message="Experience Stop outcome is invalid.",
                next_action="Restore the session outcome from Git.",
            )
        return payload

    @staticmethod
    def _id_list(value: object) -> bool:
        return (
            isinstance(value, list)
            and len(value) == len(set(value))
            and all(isinstance(item, str) and item.strip() for item in value)
        )

    def _load_experience(
        self,
        path: Path,
        experience_id: str,
    ) -> ExperienceSnapshot:
        payload = self._load_json(path, "invalid_experience")
        if (
            payload.get("asset_type") != "experience_event"
            or payload.get("experience_id") != experience_id
            or payload.get("asset_id") != path.stem
        ):
            self._invalid_experience(experience_id)
        snapshot = self._snapshot(
            payload,
            path.relative_to(self.repository_path),
        )
        for item in snapshot.evidence:
            evidence_path = self.repository_path / item.asset_path
            self._validate_path(evidence_path)
            if (
                not evidence_path.is_file()
                or hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                != item.sha256
            ):
                self._invalid_evidence(evidence_path)
        return snapshot

    @staticmethod
    def _snapshot(
        payload: dict[str, Any],
        relative: Path,
    ) -> ExperienceSnapshot:
        try:
            return ExperienceSnapshot(
                asset_id=payload["experience_id"],
                asset_path=relative.as_posix(),
                event_id=payload["asset_id"],
                previous_event_id=payload["previous_event_id"],
                state=payload["state"],
                content=ExperienceContent(**payload["content"]),
                evidence=tuple(
                    ExperienceEvidence(**item) for item in payload["evidence"]
                ),
                extraction_session_id=payload["extraction_session_id"],
                source_kind=payload["source_kind"],
                relation_type=payload["relation_type"],
                related_experience_id=payload["related_experience_id"],
                created_at=payload["created_at"],
                created_by=payload["created_by"],
                reviewed_at=payload["reviewed_at"],
                reviewed_by=payload["reviewed_by"],
                decision=payload["decision"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkspaceError(
                code="invalid_experience",
                message="Experience event does not match the governed schema.",
                next_action="Restore the Experience event from Git.",
            ) from error

    def _write_new(
        self,
        relative: Path,
        payload: dict[str, Any],
        capacity: CapacityStatus,
    ) -> None:
        target = self.repository_path / relative
        self._validate_path(target)
        raw = (
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
            + "\n"
        ).encode("utf-8")
        self._validate_capacity(target, raw, capacity)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise WorkspaceError(
                code="experience_asset_exists",
                message=f"Experience asset already exists: {relative.as_posix()}.",
                next_action="Load the existing immutable asset.",
            )
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, target)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise WorkspaceError(
                code="experience_write_failed",
                message="Experience evidence could not be written atomically.",
                next_action="Check Team Memory permissions and retry.",
            ) from error

    def _validate_capacity(
        self,
        target: Path,
        raw: bytes,
        capacity: CapacityStatus,
    ) -> None:
        if len(raw) >= capacity.max_file_bytes:
            raise WorkspaceError(
                code="experience_file_too_large",
                message=f"Experience asset exceeds the file limit: {target.name}.",
                next_action="Reduce the bounded Experience content and retry.",
            )
        used = sum(
            path.stat().st_size
            for path in self.repository_path.rglob("*")
            if path.is_file() and ".git" not in path.parts
        )
        if used + len(raw) >= capacity.max_repository_bytes:
            raise WorkspaceError(
                code="repository_capacity_exceeded",
                message="Team Memory has no capacity for the Experience asset.",
                next_action="Archive approved large assets before retrying.",
            )

    def _load_json(self, path: Path, code: str) -> dict[str, Any]:
        self._validate_path(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code=code,
                message=f"Governed JSON evidence is unavailable: {path.name}.",
                next_action="Restore the evidence from Git.",
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceError(
                code=code,
                message=f"Governed JSON evidence is not an object: {path.name}.",
                next_action="Restore the evidence from Git.",
            )
        return payload

    def _validate_path(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self.repository_path)
        except ValueError as error:
            raise WorkspaceError(
                code="unsafe_experience_path",
                message="Experience evidence resolved outside Team Memory.",
                next_action="Use only managed repository-relative evidence paths.",
            ) from error

    @staticmethod
    def _validate_id(value: str, label: str) -> None:
        if not isinstance(value, str) or SAFE_ID_PATTERN.fullmatch(value) is None:
            raise WorkspaceError(
                code="invalid_experience_id",
                message=f"{label} is invalid.",
                next_action="Use 1-100 letters, digits, dots, underscores, or hyphens.",
            )

    @staticmethod
    def _validate_actor(actor_id: str) -> None:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise WorkspaceError(
                code="missing_actor",
                message="Experience actions require a team member identity.",
                next_action="Reconnect Team Memory with a non-empty actor.",
            )

    def _timestamp(self) -> str:
        value = self.clock()
        if not isinstance(value, str) or not value.strip():
            raise WorkspaceError(
                code="invalid_clock",
                message="Experience timestamp source returned an invalid value.",
                next_action="Retry with a valid UTC clock.",
            )
        return value

    @contextmanager
    def _lock(self) -> Iterator[None]:
        path = self.repository_path / ".mlagent-local/experience.lock"
        self._validate_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _invalid_experience(experience_id: str) -> None:
        raise WorkspaceError(
            code="invalid_experience",
            message=f"Experience history is invalid: {experience_id}.",
            next_action="Restore or reconcile the Experience events from Git.",
        )

    @staticmethod
    def _invalid_evidence(path: Path) -> None:
        raise WorkspaceError(
            code="invalid_experience_evidence",
            message=f"Experience evidence is missing or changed: {path.name}.",
            next_action="Restore the exact cited evidence from Git.",
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _terms(value: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9_]+", value.lower())
        if len(term) > 1
    }
