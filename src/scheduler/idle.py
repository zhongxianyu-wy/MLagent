from __future__ import annotations

from src.scheduler.lease import IdleSchedulerLease, IdleSchedulerLeaseStore


class IdleScheduler:
    def __init__(self, leases: IdleSchedulerLeaseStore) -> None:
        self.leases = leases

    def acquire_dream_lease(
        self, owner_id: str, now: int, ttl_seconds: int = 600
    ) -> IdleSchedulerLease | None:
        return self.leases.acquire_lease("dream", owner_id, now, ttl_seconds)
