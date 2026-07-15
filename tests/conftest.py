from types import SimpleNamespace
from pathlib import Path

import pytest

from src.domain.models import TrainingAuthorization


@pytest.fixture
def confirmed_domain_core():
    class ConfirmedDomainCore:
        def require_confirmed_dataset(self, connection_path, dataset_id, version):
            return SimpleNamespace(
                dataset_id=dataset_id,
                version=version,
                state="confirmed",
                content_fingerprint=f"fingerprint-{dataset_id}-v{version}",
                version_fingerprint=f"version-fingerprint-{dataset_id}-v{version}",
            )

        def require_confirmed_dataset_reference(
            self,
            connection_path,
            dataset_id,
            version,
        ):
            snapshot = SimpleNamespace(
                dataset_id=dataset_id,
                version=version,
                state="confirmed",
                content_fingerprint=f"fingerprint-{dataset_id}-v{version}",
                version_fingerprint=f"version-fingerprint-{dataset_id}-v{version}",
                primary_metric="roc_auc",
                random_seed=42,
            )
            return SimpleNamespace(
                snapshot=snapshot,
                manifest_path=Path(
                    f"/team-memory/datasets/{dataset_id}/v{version:04d}/manifest.json"
                ),
            )

        def authorize_training(self, command):
            return TrainingAuthorization(
                authorized=True,
                entry_point=command.entry_point,
                dataset_id=command.dataset_id,
                dataset_version=command.dataset_version,
                dataset_version_fingerprint=(
                    f"version-fingerprint-{command.dataset_id}-v"
                    f"{command.dataset_version}"
                ),
                plan_id=command.plan_id,
                plan_event_id="plan-event-1",
                approval_id=command.approval_id,
                plan_fingerprint="plan-sha",
                code_fingerprint="code-sha",
                authorized_at="2026-07-15T00:00:00Z",
                authorized_by="alice",
            )

    return ConfirmedDomainCore()
