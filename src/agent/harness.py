from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from src.evaluation.cv import cross_validate
from src.models import EvaluationConfig
from src.models import ExperimentRoundTrace
from src.training.dataset_loader import load_dataset_from_manifest
from src.training.feature_selection import plan_feature_subset_strategy
from src.training.modeling import SklearnModelTrainer
from src.training.preprocessing import plan_preprocessing_strategy


class ExplorationHarness:
    def __init__(
        self,
        output_root: str = "experiments/outputs",
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.clock = clock or (lambda: int(time.time()))

    def start(self, request: dict) -> list[ExperimentRoundTrace]:
        if request.get("manifest_path"):
            return self._start_real(request)
        return self._start_mock(request)

    def _start_mock(self, request: dict) -> list[ExperimentRoundTrace]:
        experiment_id = request["experiment_id"]
        max_rounds = int(request.get("max_rounds", 1))
        metric_name = request.get("guidance_metric_name", "auc")
        traces = []
        for round_num in range(1, max_rounds + 1):
            preprocessing = plan_preprocessing_strategy(round_num)
            subset = plan_feature_subset_strategy(round_num)
            direction = request.get("direction") or f"{preprocessing} + {subset}"
            traces.append(
                ExperimentRoundTrace(
                    round_id=f"{experiment_id}-round-{round_num}",
                    experiment_id=experiment_id,
                    round_num=round_num,
                    mode="exploration",
                    exploration_direction=direction,
                    hypothesis=f"round {round_num} tests {subset}",
                    preprocessing_strategy=preprocessing,
                    feature_subset_strategy=subset,
                    selected_features_json=json.dumps(["f1", "f2"]),
                    model_type="mock_sklearn",
                    params_json=json.dumps({"round": round_num}),
                    cv_metrics_json=json.dumps({metric_name: 0.8}),
                    threshold_policy="youden",
                    selected_threshold=0.5,
                    test_metrics_json=None,
                    guidance_metric_name=metric_name,
                    guidance_metric_value=0.8,
                    status="completed",
                    stop_reason=None,
                    error_msg=None,
                    llm_rationale_summary=f"mock exploration round {round_num}",
                    created_at=self.clock(),
                )
            )
        return traces

    def _start_real(self, request: dict) -> list[ExperimentRoundTrace]:
        experiment_id = request["experiment_id"]
        max_rounds = int(request.get("max_rounds", 1))
        metric_name = request.get("guidance_metric_name", "auc")
        dataset = load_dataset_from_manifest(request["manifest_path"])
        run_dir = self.output_root / experiment_id
        run_dir.mkdir(parents=True, exist_ok=True)
        traces = []

        for round_num in range(1, max_rounds + 1):
            preprocessing = plan_preprocessing_strategy(round_num)
            subset = plan_feature_subset_strategy(round_num)
            trainer = SklearnModelTrainer(
                model_type="logistic_regression",
                random_seed=int(request.get("random_seed", 0)),
            )
            cv_result = cross_validate(
                dataset.train_x,
                dataset.train_y,
                EvaluationConfig(
                    metric=metric_name,
                    k_folds=int(request.get("k_folds", 2)),
                    target_specificity=request.get("target_specificity"),
                    threshold_policy=request.get("threshold_policy", "youden"),
                    use_test_if_available=True,
                ),
                trainer.predict_fold,
            )
            guidance_value = cv_result.metrics[metric_name]
            trace = ExperimentRoundTrace(
                round_id=f"{experiment_id}-round-{round_num}",
                experiment_id=experiment_id,
                round_num=round_num,
                mode=request["mode"],
                exploration_direction=request.get("direction")
                or f"{preprocessing} + {subset}",
                hypothesis=f"round {round_num} evaluates {subset}",
                preprocessing_strategy=preprocessing,
                feature_subset_strategy=subset,
                selected_features_json=json.dumps(dataset.feature_names),
                model_type="logistic_regression",
                params_json=json.dumps({"round": round_num, "random_seed": request.get("random_seed", 0)}),
                cv_metrics_json=json.dumps(cv_result.metrics),
                threshold_policy=cv_result.threshold.policy,
                selected_threshold=cv_result.threshold.threshold,
                test_metrics_json=None,
                guidance_metric_name=metric_name,
                guidance_metric_value=guidance_value,
                status="completed",
                stop_reason=None,
                error_msg=None,
                llm_rationale_summary="real sklearn k-fold exploration round",
                created_at=self.clock(),
            )
            traces.append(trace)

        self._write_outputs(run_dir, traces)
        return traces

    def _write_outputs(
        self, run_dir: Path, traces: list[ExperimentRoundTrace]
    ) -> None:
        rows = [self._trace_to_output_row(trace) for trace in traces]
        (run_dir / "rounds.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        )
        best = max(rows, key=lambda row: row["guidance_metric_value"])
        (run_dir / "best_config.json").write_text(
            json.dumps(best, ensure_ascii=False, indent=2)
        )
        (run_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "experiment_id": best["experiment_id"],
                    "best_metric": best["guidance_metric_value"],
                    "metric_name": best["guidance_metric_name"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        (run_dir / "run_summary.json").write_text(
            json.dumps(
                {
                    "experiment_id": best["experiment_id"],
                    "rounds": len(rows),
                    "status": "completed",
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def _trace_to_output_row(self, trace: ExperimentRoundTrace) -> dict:
        row = asdict(trace)
        row["selected_features"] = json.loads(trace.selected_features_json)
        row["params"] = json.loads(trace.params_json)
        row["cv_metrics"] = json.loads(trace.cv_metrics_json)
        return row


class StrictSkillReproductionAdapter:
    def __init__(self, registry, output_root: str = "experiments/outputs") -> None:
        self.registry = registry
        self.output_root = Path(output_root)

    def reproduce(self, skill_id: str, dataset: dict) -> dict:
        metadata = self.registry.get_metadata(skill_id)
        required_features = metadata.get("required_features", [])
        if dataset.get("manifest_path"):
            loaded = load_dataset_from_manifest(dataset["manifest_path"])
            feature_names = loaded.feature_names
            dataset_id = loaded.manifest.dataset_id
        else:
            feature_names = dataset["features"]
            dataset_id = dataset["dataset_id"]
        missing = [
            feature for feature in required_features if feature not in feature_names
        ]
        if missing:
            raise ValueError(f"missing required features: {', '.join(missing)}")
        result = {
            "skill_id": skill_id,
            "dataset_id": dataset_id,
            "preprocessing_strategy": metadata["preprocessing"],
            "feature_subset_strategy": metadata["feature_subset"],
            "model_type": metadata["model"],
            "threshold_policy": metadata["threshold_policy"],
            "selected_features": required_features,
        }
        if dataset.get("experiment_id"):
            run_dir = self.output_root / dataset["experiment_id"]
            run_dir.mkdir(parents=True, exist_ok=True)
            if dataset.get("manifest_path"):
                cv_result = cross_validate(
                    loaded.train_x,
                    loaded.train_y,
                    EvaluationConfig(
                        metric="auc",
                        k_folds=int(dataset.get("k_folds", 2)),
                        target_specificity=None,
                        threshold_policy=metadata["threshold_policy"],
                        use_test_if_available=True,
                    ),
                    SklearnModelTrainer(
                        model_type="logistic_regression",
                        random_seed=int(dataset.get("random_seed", 0)),
                    ).predict_fold,
                )
                (run_dir / "metrics.json").write_text(
                    json.dumps(
                        {
                            "experiment_id": dataset["experiment_id"],
                            "skill_id": skill_id,
                            "cv_metrics": cv_result.metrics,
                            "threshold": cv_result.threshold.threshold,
                            "threshold_policy": cv_result.threshold.policy,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            (run_dir / "run_summary.json").write_text(
                json.dumps(
                    {
                        "experiment_id": dataset["experiment_id"],
                        "skill_id": skill_id,
                        "dataset_id": dataset_id,
                        "status": "completed",
                        "model_type": metadata["model"],
                        "selected_features": required_features,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return result
