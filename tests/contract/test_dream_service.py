from src.memory.dream import DreamService


class FakeLeaseStore:
    def __init__(self, lease=True):
        self.lease = lease
        self.requests = []

    def acquire_lease(self, lease_type, owner_id, now, ttl_seconds):
        self.requests.append((lease_type, owner_id, now, ttl_seconds))
        if not self.lease:
            return None
        return type("Lease", (), {"lease_id": "lease-1"})()


class FakeRunState:
    def __init__(self, active_runs=False, active_skill_opt=False):
        self.active_runs = active_runs
        self.active_skill_opt = active_skill_opt

    def has_active_run(self):
        return self.active_runs

    def has_active_skill_optimization(self):
        return self.active_skill_opt


def test_dream_does_not_start_before_two_hours_idle():
    service = DreamService(
        lease_store=FakeLeaseStore(),
        run_state=FakeRunState(),
        last_user_instruction_at=100,
    )

    assert service.maybe_start_idle_dream(now=100 + 7199, owner_id="cli") is None


def test_dream_starts_only_with_idle_lease_and_memory_scope():
    lease_store = FakeLeaseStore()
    service = DreamService(
        lease_store=lease_store,
        run_state=FakeRunState(),
        last_user_instruction_at=100,
    )

    job = service.maybe_start_idle_dream(now=100 + 7200, owner_id="cli")

    assert job is not None
    assert job.status == "pending"
    assert job.memory_scope == ["semantic", "episodic"]
    assert job.lease_id == "lease-1"
    assert lease_store.requests == [("dream", "cli", 7300, 600)]


def test_dream_does_not_start_when_run_or_skill_optimization_active():
    service = DreamService(
        lease_store=FakeLeaseStore(),
        run_state=FakeRunState(active_runs=True),
        last_user_instruction_at=100,
    )

    assert service.maybe_start_idle_dream(now=7300, owner_id="cli") is None
