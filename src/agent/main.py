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
        if not legacy_manifest:
            authoritative_reference = _guard_authoritative_dataset(
                args,
                dataset_id,
                domain_core_factory=domain_core_factory,
            )
            if authoritative_reference is None:
                return 2
        max_rounds = int(_option(args, "--max-rounds", "1"))
        output_root = _option(args, "--output-root", "experiments/outputs")
        request = {
            "mode": "exploration",
            "dataset_id": dataset_id,
            "max_rounds": max_rounds,
        }
        if authoritative_reference is not None:
            snapshot = authoritative_reference.snapshot
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
                }
            )
        elif manifest_path is not None:
            request["manifest_path"] = manifest_path
            request["experiment_id"] = f"explore-{dataset_id}"
        if explore_factory is not None:
            return explore_factory(request)

        if authoritative_reference is not None:
            _print_workspace_error(
                code="plan_required",
                message="Formal exploration requires an approved Exploration Plan.",
                next_action=(
                    "Create and approve an Exploration Plan before starting "
                    "this Dataset Version."
                ),
            )
            return 2

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
        core = domain_core_factory() if domain_core_factory else DomainCore()
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
    return reference


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


def _default_shell() -> int:
    from src.agent.chat_shell import ChatShell

    return ChatShell().run()


if __name__ == "__main__":
    raise SystemExit(main())
