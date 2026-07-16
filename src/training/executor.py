from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from src.domain.models import TrainingExecutionResult
from src.domain.run_repository import PreparedTrainingInstance


RESULT_FILENAME = "result.json"
ERROR_FILENAME = "error.json"


class SubprocessTrainingExecutor:
    def __init__(
        self,
        worker_module: str = "src.training.classification_worker",
        poll_interval_seconds: float = 0.1,
        termination_grace_seconds: float = 1.0,
        diagnostic_limit_bytes: int = 8000,
    ) -> None:
        if poll_interval_seconds <= 0 or termination_grace_seconds <= 0:
            raise ValueError("executor intervals must be positive")
        self.worker_module = worker_module
        self.poll_interval_seconds = poll_interval_seconds
        self.termination_grace_seconds = termination_grace_seconds
        self.diagnostic_limit_bytes = diagnostic_limit_bytes

    def execute(
        self,
        prepared: PreparedTrainingInstance,
        stop_requested: Callable[[], bool],
        timeout_seconds: float,
    ) -> TrainingExecutionResult:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        started_at = _utc_now()
        started = time.monotonic()
        primary_metric = _primary_metric(prepared.input_path)
        try:
            stopped_before_start = stop_requested()
        except Exception:
            return self._unsuccessful(
                "failed",
                primary_metric,
                "stop_check_failed",
                "Training stop state could not be checked.",
                started_at,
                started,
            )
        if stopped_before_start:
            return self._unsuccessful(
                "stopped",
                primary_metric,
                "user_stop",
                "Training was stopped before the worker started.",
                started_at,
                started,
            )
        repository = _repository_path(prepared)
        output = prepared.worker_output_path
        _require_local_output(output, repository)
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
        command = [
            sys.executable,
            "-m",
            self.worker_module,
            "--repository",
            str(repository),
            "--input",
            str(prepared.input_path),
            "--output",
            str(output),
        ]
        environment = os.environ.copy()
        project_root = Path(__file__).resolve().parents[2]
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(project_root)
            if not existing_pythonpath
            else f"{project_root}{os.pathsep}{existing_pythonpath}"
        )
        environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            }
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=project_root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError:
            shutil.rmtree(output, ignore_errors=True)
            return self._unsuccessful(
                "failed",
                primary_metric,
                "worker_start_failed",
                "Training worker process could not be started.",
                started_at,
                started,
            )
        stdout = _BoundedCollector(process.stdout, self.diagnostic_limit_bytes)
        stderr = _BoundedCollector(process.stderr, self.diagnostic_limit_bytes)
        stdout.start()
        stderr.start()
        terminal: tuple[str, str, str] | None = None
        while process.poll() is None:
            try:
                requested = stop_requested()
            except Exception:
                terminal = (
                    "failed",
                    "stop_check_failed",
                    "Training stop state could not be checked.",
                )
                self._terminate(process)
                break
            if requested:
                terminal = (
                    "stopped",
                    "user_stop",
                    "Training was stopped by user request.",
                )
                self._terminate(process)
                break
            if time.monotonic() - started >= timeout_seconds:
                terminal = (
                    "timed_out",
                    "training_timeout",
                    "Training exceeded its approved timeout.",
                )
                self._terminate(process)
                break
            time.sleep(self.poll_interval_seconds)
        stdout.join(timeout=self.termination_grace_seconds)
        stderr.join(timeout=self.termination_grace_seconds)
        if terminal is not None:
            shutil.rmtree(output, ignore_errors=True)
            return self._unsuccessful(
                terminal[0],
                primary_metric,
                terminal[1],
                terminal[2],
                started_at,
                started,
            )
        if process.returncode != 0:
            code, summary = _worker_error(output, stderr.text())
            shutil.rmtree(output, ignore_errors=True)
            return self._unsuccessful(
                "failed",
                primary_metric,
                code,
                summary,
                started_at,
                started,
            )
        try:
            result = _load_worker_result(output, primary_metric)
            return TrainingExecutionResult(
                state="completed",
                primary_metric_name=primary_metric,
                primary_metric_value=result["primary_metric_value"],
                metrics=result["metrics"],
                predictions_path=output / result["predictions_path"],
                model_path=output / result["model_path"],
                model_fingerprint=result["model_fingerprint"],
                error_code=None,
                error_summary=None,
                started_at=started_at,
                ended_at=_utc_now(),
                duration_ms=_duration_ms(started),
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            shutil.rmtree(output, ignore_errors=True)
            return self._unsuccessful(
                "failed",
                primary_metric,
                "invalid_worker_result",
                "Worker completed without a valid evidence result.",
                started_at,
                started,
            )

    def _terminate(self, process: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=self.termination_grace_seconds)
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=self.termination_grace_seconds)

    @staticmethod
    def _unsuccessful(
        state: str,
        primary_metric: str,
        error_code: str,
        error_summary: str,
        started_at: str,
        started: float,
    ) -> TrainingExecutionResult:
        return TrainingExecutionResult(
            state=state,
            primary_metric_name=primary_metric,
            primary_metric_value=None,
            metrics={},
            predictions_path=None,
            model_path=None,
            model_fingerprint=None,
            error_code=error_code,
            error_summary=error_summary[:2000],
            started_at=started_at,
            ended_at=_utc_now(),
            duration_ms=_duration_ms(started),
        )


class _BoundedCollector:
    def __init__(self, stream: BinaryIO | None, limit: int) -> None:
        self.stream = stream
        self.limit = limit
        self.buffer = bytearray()
        self.thread = threading.Thread(target=self._drain, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def join(self, timeout: float) -> None:
        self.thread.join(timeout)

    def text(self) -> str:
        return bytes(self.buffer).decode("utf-8", errors="replace").strip()

    def _drain(self) -> None:
        if self.stream is None:
            return
        try:
            while chunk := self.stream.read(4096):
                self.buffer.extend(chunk)
                if len(self.buffer) > self.limit:
                    del self.buffer[: len(self.buffer) - self.limit]
        finally:
            self.stream.close()


def _load_worker_result(output: Path, primary_metric: str) -> dict[str, Any]:
    payload = json.loads((output / RESULT_FILENAME).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("worker result must be an object")
    if payload.get("state") != "completed":
        raise ValueError("worker result is not completed")
    if payload.get("primary_metric_name") != primary_metric:
        raise ValueError("worker primary metric changed")
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("worker metrics are invalid")
    normalized_metrics = {
        str(name): float(value) for name, value in metrics.items()
    }
    value = float(payload["primary_metric_value"])
    if normalized_metrics.get(primary_metric) != value:
        raise ValueError("worker primary metric is inconsistent")
    predictions_path = _safe_output_name(payload["predictions_path"])
    model_path = _safe_output_name(payload["model_path"])
    predictions = output / predictions_path
    model = output / model_path
    if not predictions.is_file() or predictions.is_symlink():
        raise ValueError("worker predictions are unavailable")
    if not model.is_file() or model.is_symlink():
        raise ValueError("worker model is unavailable")
    model_fingerprint = payload.get("model_fingerprint")
    if model_fingerprint != _sha256(model.read_bytes()):
        raise ValueError("worker model fingerprint changed")
    return {
        "primary_metric_value": value,
        "metrics": normalized_metrics,
        "predictions_path": predictions_path,
        "model_path": model_path,
        "model_fingerprint": model_fingerprint,
    }


def _worker_error(output: Path, diagnostic: str) -> tuple[str, str]:
    try:
        payload = json.loads((output / ERROR_FILENAME).read_text(encoding="utf-8"))
        code = payload["error_code"]
        summary = payload["error_summary"]
        if isinstance(code, str) and code.strip() and isinstance(summary, str) and summary.strip():
            return code, summary[:2000]
    except (KeyError, OSError, TypeError, json.JSONDecodeError):
        pass
    return "worker_failed", (diagnostic or "Training worker failed.")[-2000:]


def _primary_metric(input_path: Path) -> str:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    metric = payload.get("primary_metric_name")
    if not isinstance(metric, str) or not metric.strip():
        raise ValueError("frozen input has no primary metric")
    return metric


def _repository_path(prepared: PreparedTrainingInstance) -> Path:
    try:
        repository = prepared.pending_path.parents[3]
        relative = prepared.pending_path.relative_to(repository)
    except (IndexError, ValueError) as error:
        raise ValueError("pending package is outside Team Memory") from error
    if relative.parts[:4] != (
        "runs",
        prepared.run_id,
        "pending",
        prepared.instance_id,
    ):
        raise ValueError("pending package path does not match its identity")
    return repository


def _require_local_output(output: Path, repository: Path) -> None:
    root = repository / ".mlagent-local" / "run-work"
    try:
        output.resolve(strict=False).relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("worker output is outside the local run-work root") from error


def _safe_output_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("worker output name is empty")
    path = Path(value)
    if path.is_absolute() or len(path.parts) != 1 or ".." in path.parts:
        raise ValueError("worker output name is unsafe")
    return path.name


def _duration_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
