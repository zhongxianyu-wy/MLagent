from src.scheduler.lease import IdleSchedulerLeaseStore


def test_acquire_lease_blocks_second_active_owner(tmp_path):
    store = IdleSchedulerLeaseStore(str(tmp_path / "leases.db"))

    first = store.acquire_lease("dream", owner_id="cli", now=100, ttl_seconds=60)
    second = store.acquire_lease("dream", owner_id="api", now=120, ttl_seconds=60)

    assert first is not None
    assert first.owner_id == "cli"
    assert second is None


def test_expired_lease_can_be_superseded(tmp_path):
    store = IdleSchedulerLeaseStore(str(tmp_path / "leases.db"))

    store.acquire_lease("dream", owner_id="cli", now=100, ttl_seconds=60)
    second = store.acquire_lease("dream", owner_id="api", now=161, ttl_seconds=60)

    assert second is not None
    assert second.owner_id == "api"
    assert second.status == "active"


def test_heartbeat_and_release_update_lease_state(tmp_path):
    store = IdleSchedulerLeaseStore(str(tmp_path / "leases.db"))
    lease = store.acquire_lease("dream", owner_id="cli", now=100, ttl_seconds=60)

    heartbeat = store.heartbeat(lease.lease_id, now=120, ttl_seconds=60)
    released = store.release(lease.lease_id, status="released")

    assert heartbeat.heartbeat_at == 120
    assert heartbeat.expires_at == 180
    assert released.status == "released"
