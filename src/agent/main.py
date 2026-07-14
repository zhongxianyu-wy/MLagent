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
) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        shell = shell_factory or _default_shell
        return shell()
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
        dataset_id = _option(args, "--dataset-id", None)
        if manifest_path is not None and dataset_id is None:
            dataset_id = json.loads(Path(manifest_path).read_text())["dataset_id"]
        if dataset_id is None:
            return 2
        max_rounds = int(_option(args, "--max-rounds", "1"))
        output_root = _option(args, "--output-root", "experiments/outputs")
        request = {
            "mode": "exploration",
            "dataset_id": dataset_id,
            "max_rounds": max_rounds,
        }
        if manifest_path is not None:
            request["manifest_path"] = manifest_path
            request["experiment_id"] = f"explore-{dataset_id}"
        if explore_factory is not None:
            return explore_factory(request)

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


def _default_shell() -> int:
    from src.agent.chat_shell import ChatShell

    return ChatShell().run()


if __name__ == "__main__":
    raise SystemExit(main())
