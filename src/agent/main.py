from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path


def main(
    argv: list[str] | None = None,
    shell_factory: Callable[[], int] | None = None,
    explore_factory: Callable[[dict], int] | None = None,
    reproduce_factory: Callable[[dict], int] | None = None,
    interact_factory: Callable[[dict], int] | None = None,
    distill_factory: Callable[[dict], int] | None = None,
    research_factory: Callable[[dict], int] | None = None,
    domain_core_factory: Callable[[], object] | None = None,
) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        shell = shell_factory or _default_shell
        return shell()
    if args[0] == "bootstrap-memory":
        return _bootstrap_memory(args, domain_core_factory=domain_core_factory)
    if args[0] == "intake-data":
        return _intake_data(args, domain_core_factory=domain_core_factory)
    if args[0] == "design-and-explore":
        return _design_and_explore(args, domain_core_factory=domain_core_factory)
    if args[0] == "experience":
        return _experience(args, domain_core_factory=domain_core_factory)
    if args[0] == "status":
        return 0
    if args[0] == "intake":
        from src.frontend_api.dataset_service import DatasetService

        path = args[1]
        output_root = "experiments/standardized"
        if "--output-root" in args:
            output_root = args[args.index("--output-root") + 1]
        split_strategy = _option(args, "--split-strategy", "train_only")
        split_ratio = _optional_float(args, "--split-ratio")
        random_seed = _optional_int(args, "--random-seed")
        service = DatasetService(output_root=output_root)
        inspection = service.inspect_path(path)
        if not inspection.ready:
            return 2
        service.build_manifest(
            inspection.session_id,
            split_strategy=split_strategy,
            split_ratio=split_ratio,
            random_seed=random_seed,
        )
        return 0
    if args[0] == "explore":
        manifest_path = _option(args, "--manifest-path")
        explicit_dataset_id = _option(args, "--dataset-id", None)
        legacy_manifest = manifest_path is not None and explicit_dataset_id is None
        dataset_id = explicit_dataset_id
        if legacy_manifest:
            dataset_id = json.loads(Path(manifest_path).read_text())["dataset_id"]
        if dataset_id is None:
            return 2
        authoritative_reference = None
        authoritative_core = None
        if not legacy_manifest:
            from src.domain.core import DomainCore

            authoritative_core = (
                domain_core_factory() if domain_core_factory else DomainCore()
            )
            authoritative_reference = _guard_authoritative_dataset(
                args,
                dataset_id,
                domain_core_factory=domain_core_factory,
                domain_core=authoritative_core,
            )
            if authoritative_reference is None:
                return 2
        output_root = _option(args, "--output-root", "experiments/outputs")
        request = {
            "mode": "exploration",
            "dataset_id": dataset_id,
        }
        if authoritative_reference is not None:
            snapshot = authoritative_reference.snapshot
            authorization = _guard_exploration_approval(
                args,
                dataset_id=dataset_id,
                dataset_version=snapshot.version,
                domain_core=authoritative_core,
            )
            if authorization is None:
                return 2
            request.update(
                {
                    "dataset_version": snapshot.version,
                    "dataset_content_fingerprint": snapshot.content_fingerprint,
                    "dataset_version_fingerprint": snapshot.version_fingerprint,
                    "manifest_path": str(authoritative_reference.manifest_path),
                    "experiment_id": (
                        f"explore-{dataset_id}-v{snapshot.version:04d}"
                    ),
                    "guidance_metric_name": _training_metric_name(
                        snapshot.primary_metric
                    ),
                    "random_seed": snapshot.random_seed,
                    "max_rounds": authorization.round_count,
                    "authorization": authorization.to_dict(),
                }
            )
        elif manifest_path is not None:
            request["max_rounds"] = int(_option(args, "--max-rounds", "1"))
            request["manifest_path"] = manifest_path
            request["experiment_id"] = f"explore-{dataset_id}"
        if explore_factory is not None:
            return explore_factory(request)

        if authoritative_reference is not None:
            from src.domain.models import ExecuteExplorationCommand, WorkspaceError

            try:
                status = authoritative_core.execute_exploration(
                    ExecuteExplorationCommand(
                        connection_path=Path(
                            _option(
                                args,
                                "--workspace-config",
                                ".mlagent-workspace.json",
                            )
                        ),
                        code_root=Path(_option(args, "--code-root", ".")),
                        dataset_id=dataset_id,
                        dataset_version=authoritative_reference.snapshot.version,
                        plan_id=authorization.plan_id,
                        approval_id=authorization.approval_id,
                        entrypoint_path=_option(args, "--entrypoint", None),
                    )
                )
            except WorkspaceError as error:
                print(
                    json.dumps(
                        {"status": "Failed", "error": error.to_dict()},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                return 2
            except (TypeError, ValueError) as error:
                _print_workspace_error(
                    code="invalid_arguments",
                    message=str(error),
                    next_action="Check governed exploration arguments and retry.",
                )
                return 2
            print(
                json.dumps(
                    status.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0 if status.state == "completed" else 2

        from src.agent.harness import ExplorationHarness
        from src.frontend_api.run_service import RunService

        service = RunService(exploration_harness=ExplorationHarness(output_root=output_root))
        try:
            service.start_run(request)
        except ValueError:
            return 2
        return 0
    if args[0] == "reproduce":
        request = {
            "skill_id": args[args.index("--skill-id") + 1],
            "dataset_id": args[args.index("--dataset-id") + 1],
            "strict": True,
        }
        authoritative_reference = _guard_authoritative_dataset(
            args,
            request["dataset_id"],
            domain_core_factory=domain_core_factory,
        )
        if authoritative_reference is None:
            return 2
        snapshot = authoritative_reference.snapshot
        request.update(
            {
                "dataset_version": snapshot.version,
                "dataset_content_fingerprint": snapshot.content_fingerprint,
                "dataset_version_fingerprint": snapshot.version_fingerprint,
                "manifest_path": str(authoritative_reference.manifest_path),
            }
        )
        if reproduce_factory is not None:
            return reproduce_factory(request)
        return 2
    if args[0] == "interact":
        from src.agent.control_center import instruction_to_validation_request

        request = instruction_to_validation_request(
            dataset_id=args[args.index("--dataset-id") + 1],
            instruction=args[args.index("--instruction") + 1],
        )
        if interact_factory is not None:
            return interact_factory(request)
        return 2
    if args[0] == "distill":
        request = {
            "source_type": "notebook",
            "source": args[args.index("--notebook") + 1],
        }
        if distill_factory is not None:
            return distill_factory(request)
        return 2
    if args[0] == "research":
        request = {"mode": "target", "target": args[args.index("--target") + 1]}
        if research_factory is not None:
            return research_factory(request)
        return 2
    return 2


def _option(args: list[str], name: str, default: str | None = None) -> str | None:
    if name not in args:
        return default
    index = args.index(name) + 1
    if index >= len(args):
        raise ValueError(f"{name} requires a value")
    return args[index]


def _optional_float(args: list[str], name: str) -> float | None:
    value = _option(args, name, None)
    return None if value is None else float(value)


def _optional_int(args: list[str], name: str) -> int | None:
    value = _option(args, name, None)
    return None if value is None else int(value)


def _guard_authoritative_dataset(
    args: list[str],
    dataset_id: str,
    domain_core_factory: Callable[[], object] | None,
    domain_core: object | None = None,
):
    from src.domain.core import DomainCore
    from src.domain.models import WorkspaceError

    try:
        dataset_version = _optional_int(args, "--dataset-version")
        if dataset_version is None:
            raise WorkspaceError(
                code="missing_dataset_version",
                message="Formal execution requires an explicit Dataset Version.",
                next_action=(
                    "Pass --dataset-version with a confirmed immutable "
                    "version number."
                ),
            )
        core = domain_core or (
            domain_core_factory() if domain_core_factory else DomainCore()
        )
        reference = core.require_confirmed_dataset_reference(
            Path(_option(args, "--workspace-config", ".mlagent-workspace.json")),
            dataset_id,
            dataset_version,
        )
    except WorkspaceError as error:
        print(
            json.dumps(
                {"status": "Failed", "error": error.to_dict()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return None
    except (TypeError, ValueError) as error:
        _print_workspace_error(
            code="invalid_arguments",
            message=str(error),
            next_action="Check Dataset Version arguments and retry.",
        )
        return None
    return reference


def _guard_exploration_approval(
    args: list[str],
    dataset_id: str,
    dataset_version: int,
    domain_core: object,
):
    from src.domain.models import AuthorizeTrainingCommand, WorkspaceError

    try:
        authorization = domain_core.authorize_training(
            AuthorizeTrainingCommand(
                connection_path=Path(
                    _option(
                        args,
                        "--workspace-config",
                        ".mlagent-workspace.json",
                    )
                ),
                code_root=Path(_option(args, "--code-root", ".")),
                entry_point="cli_explore",
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                plan_id=_option(args, "--plan-id", None),
                approval_id=_option(args, "--approval-id", None),
            )
        )
    except WorkspaceError as error:
        print(
            json.dumps(
                {"status": "Failed", "error": error.to_dict()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return None
    except (TypeError, ValueError) as error:
        _print_workspace_error(
            code="invalid_arguments",
            message=str(error),
            next_action="Check plan approval arguments and retry.",
        )
        return None
    return authorization


def _training_metric_name(primary_metric: str) -> str:
    return "auc" if primary_metric == "roc_auc" else primary_metric


def _print_workspace_error(code: str, message: str, next_action: str) -> None:
    print(
        json.dumps(
            {
                "status": "Failed",
                "error": {
                    "code": code,
                    "message": message,
                    "next_action": next_action,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _bootstrap_memory(
    args: list[str],
    domain_core_factory: Callable[[], object] | None = None,
) -> int:
    from src.domain.core import DomainCore
    from src.domain.models import BootstrapMemoryCommand, WorkspaceError

    try:
        if len(args) < 2 or args[1].startswith("--"):
            raise WorkspaceError(
                code="missing_repository_path",
                message="A Team Memory Repository path is required.",
                next_action="Run bootstrap-memory <path> --actor <team-member>.",
            )
        actor_id = _option(args, "--actor", None)
        if actor_id is None or not actor_id.strip():
            raise WorkspaceError(
                code="missing_actor",
                message="A non-empty team member identity is required.",
                next_action="Pass --actor with the identity used for repository audit records.",
            )
        connection_value = _option(
            args,
            "--workspace-config",
            ".mlagent-workspace.json",
        )
        core = domain_core_factory() if domain_core_factory else DomainCore()
        snapshot = core.bootstrap_memory(
            BootstrapMemoryCommand(
                repository_path=Path(args[1]),
                actor_id=actor_id,
                remote_url=_option(args, "--remote", None),
                connection_path=Path(connection_value),
            )
        )
    except WorkspaceError as error:
        print(
            json.dumps(
                {"ready": False, "error": error.to_dict()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    except (TypeError, ValueError) as error:
        problem = WorkspaceError(
            code="invalid_arguments",
            message=str(error),
            next_action="Check bootstrap-memory arguments and retry.",
        )
        print(
            json.dumps(
                {"ready": False, "error": problem.to_dict()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if snapshot.ready else 2


def _intake_data(
    args: list[str],
    domain_core_factory: Callable[[], object] | None = None,
) -> int:
    from src.domain.core import DomainCore
    from src.domain.models import (
        ConfirmDatasetCommand,
        InspectDatasetCommand,
        WorkspaceError,
    )

    try:
        if len(args) < 3 or args[1].startswith("--") or args[2].startswith("--"):
            raise WorkspaceError(
                code="missing_dataset_paths",
                message="Feature and label CSV paths are required.",
                next_action="Run intake-data <features.csv> <labels.csv> and review the pending confirmation.",
            )
        core = domain_core_factory() if domain_core_factory else DomainCore()
        feature_path = Path(args[1])
        label_path = Path(args[2])
        if "--confirm" not in args:
            result = core.inspect_dataset(
                InspectDatasetCommand(
                    feature_path=feature_path,
                    label_path=label_path,
                    sample_id_col=_option(args, "--sample-id", None),
                    label_col=_option(args, "--label-column", None),
                )
            )
        else:
            required_options = {
                "sample_id_col": _option(args, "--sample-id", None),
                "label_col": _option(args, "--label-column", None),
                "task_type": _option(args, "--task", None),
                "primary_metric": _option(args, "--metric", None),
                "split_strategy": _option(args, "--split-strategy", None),
                "target_metric": _optional_float(args, "--target"),
            }
            missing = [
                name
                for name, value in required_options.items()
                if value is None or (isinstance(value, str) and not value.strip())
            ]
            if missing:
                raise WorkspaceError(
                    code="missing_confirmation",
                    message=f"Dataset confirmation fields are missing: {', '.join(missing)}",
                    next_action="Confirm sample ID, label, task, metric, split, and target before creating a Dataset Version.",
                )
            random_seed = _optional_int(args, "--random-seed")
            result = core.confirm_dataset(
                ConfirmDatasetCommand(
                    connection_path=Path(
                        _option(
                            args,
                            "--workspace-config",
                            ".mlagent-workspace.json",
                        )
                    ),
                    feature_path=feature_path,
                    label_path=label_path,
                    sample_id_col=required_options["sample_id_col"],
                    label_col=required_options["label_col"],
                    task_type=required_options["task_type"],
                    positive_class=_option(args, "--positive-class", None),
                    primary_metric=required_options["primary_metric"],
                    split_strategy=required_options["split_strategy"],
                    target_metric=required_options["target_metric"],
                    test_ratio=_optional_float(args, "--test-ratio"),
                    random_seed=42 if random_seed is None else random_seed,
                    dataset_id=_option(args, "--dataset-id", None),
                )
            )
    except WorkspaceError as error:
        print(
            json.dumps(
                {"status": "Failed", "error": error.to_dict()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    except (TypeError, ValueError) as error:
        problem = WorkspaceError(
            code="invalid_arguments",
            message=str(error),
            next_action="Check intake-data arguments and retry.",
        )
        print(
            json.dumps(
                {"status": "Failed", "error": problem.to_dict()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 2 if getattr(result, "status", None) == "Failed" else 0


def _design_and_explore(
    args: list[str],
    domain_core_factory: Callable[[], object] | None = None,
) -> int:
    from src.domain.core import DomainCore
    from src.domain.models import (
        ApproveExplorationPlanCommand,
        ExplorationRound,
        RecordExplorationPlanCommand,
        WorkspaceError,
    )

    try:
        if len(args) < 2 or args[1] not in {"record", "approve"}:
            raise WorkspaceError(
                code="invalid_design_action",
                message="design-and-explore requires record or approve.",
                next_action="Record Claude's plan first, then approve it only after human review.",
            )
        core = domain_core_factory() if domain_core_factory else DomainCore()
        connection_path = Path(
            _option(args, "--workspace-config", ".mlagent-workspace.json")
        )
        code_root = Path(_required_option(args, "--code-root"))
        if args[1] == "approve":
            result = core.approve_exploration_plan(
                ApproveExplorationPlanCommand(
                    connection_path=connection_path,
                    code_root=code_root,
                    plan_id=_required_option(args, "--plan-id"),
                )
            )
        else:
            plan = _load_exploration_plan_file(
                Path(_required_option(args, "--plan-file"))
            )
            result = core.record_exploration_plan(
                RecordExplorationPlanCommand(
                    connection_path=connection_path,
                    code_root=code_root,
                    dataset_id=_required_option(args, "--dataset-id"),
                    dataset_version=int(
                        _required_option(args, "--dataset-version")
                    ),
                    plan_id=plan["plan_id"],
                    planning_session_id=plan["planning_session_id"],
                    user_direction=plan["user_direction"],
                    baseline_hypothesis=plan["baseline_hypothesis"],
                    rounds=tuple(
                        ExplorationRound(
                            round_number=item["round_number"],
                            hypothesis=item["hypothesis"],
                            optimization_direction=item[
                                "optimization_direction"
                            ],
                            intended_changes=tuple(item["intended_changes"]),
                        )
                        for item in plan["rounds"]
                    ),
                    stop_conditions=tuple(plan["stop_conditions"]),
                    risks=tuple(plan["risks"]),
                    resource_limits=dict(plan["resource_limits"]),
                    trusted_experience_ids=tuple(
                        plan["trusted_experience_ids"]
                    ),
                    pending_experience_ids=tuple(
                        plan["pending_experience_ids"]
                    ),
                    excluded_pending_experience_ids=tuple(
                        plan["excluded_pending_experience_ids"]
                    ),
                    experience_applicability=dict(
                        plan["experience_applicability"]
                    ),
                    candidate_code_paths=tuple(plan["candidate_code_paths"]),
                )
            )
    except WorkspaceError as error:
        _print_workspace_error(error.code, error.message, error.next_action)
        return 2
    except (KeyError, TypeError, ValueError) as error:
        problem = WorkspaceError(
            code="invalid_plan_file",
            message=f"Exploration plan JSON has invalid fields: {error}.",
            next_action="Regenerate the structurally complete plan JSON and retry recording.",
        )
        _print_workspace_error(
            problem.code,
            problem.message,
            problem.next_action,
        )
        return 2

    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _experience(
    args: list[str],
    domain_core_factory: Callable[[], object] | None = None,
) -> int:
    from src.domain.core import DomainCore
    from src.domain.models import WorkspaceError

    try:
        if len(args) < 2 or args[1] != "search":
            raise WorkspaceError(
                code="invalid_experience_action",
                message="experience requires the search action.",
                next_action="Run experience search with a non-empty query.",
            )
        top_k = int(_option(args, "--top-k", "5"))
        core = domain_core_factory() if domain_core_factory else DomainCore()
        trusted, pending = core.search_experiences(
            Path(
                _option(
                    args,
                    "--workspace-config",
                    ".mlagent-workspace.json",
                )
            ),
            _required_option(args, "--query"),
            dataset_id=_option(args, "--dataset-id", None),
            include_pending="--include-pending" in args,
            top_k=top_k,
        )
    except WorkspaceError as error:
        _print_workspace_error(error.code, error.message, error.next_action)
        return 2
    except (TypeError, ValueError) as error:
        _print_workspace_error(
            "invalid_arguments",
            str(error),
            "Check Experience search arguments and retry.",
        )
        return 2
    print(
        json.dumps(
            {
                "trusted": [item.to_dict() for item in trusted],
                "pending": [item.to_dict() for item in pending],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _required_option(args: list[str], name: str) -> str:
    from src.domain.models import WorkspaceError

    value = _option(args, name, None)
    if value is None or not value.strip():
        raise WorkspaceError(
            code="missing_argument",
            message=f"Required argument is missing: {name}.",
            next_action=f"Pass {name} with a non-empty value.",
        )
    return value


def _load_exploration_plan_file(path: Path) -> dict:
    from src.domain.models import WorkspaceError

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkspaceError(
            code="invalid_plan_file",
            message=f"Exploration plan JSON cannot be read: {path}.",
            next_action="Write one UTF-8 JSON object containing the completed plan.",
        ) from error
    if not isinstance(payload, dict):
        raise WorkspaceError(
            code="invalid_plan_file",
            message="Exploration plan JSON must be one object.",
            next_action="Regenerate the completed plan as one JSON object.",
        )
    required = {
        "plan_id",
        "planning_session_id",
        "user_direction",
        "baseline_hypothesis",
        "rounds",
        "stop_conditions",
        "risks",
        "resource_limits",
        "trusted_experience_ids",
        "pending_experience_ids",
        "excluded_pending_experience_ids",
        "experience_applicability",
        "candidate_code_paths",
    }
    if not required.issubset(payload):
        missing = ", ".join(sorted(required - set(payload)))
        raise WorkspaceError(
            code="invalid_plan_file",
            message=f"Exploration plan JSON is missing fields: {missing}.",
            next_action="Complete every review section before recording the plan.",
        )
    if not isinstance(payload["rounds"], list) or not all(
        isinstance(item, dict)
        and {
            "round_number",
            "hypothesis",
            "optimization_direction",
            "intended_changes",
        }.issubset(item)
        for item in payload["rounds"]
    ):
        raise WorkspaceError(
            code="invalid_plan_file",
            message="Exploration plan rounds have invalid structure.",
            next_action="Give every round its number, hypothesis, direction, and intended changes.",
        )
    return payload


def _default_shell() -> int:
    from src.agent.chat_shell import ChatShell

    return ChatShell().run()


if __name__ == "__main__":
    raise SystemExit(main())
