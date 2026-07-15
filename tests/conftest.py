from types import SimpleNamespace
from pathlib import Path

import pytest


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

    return ConfirmedDomainCore()
