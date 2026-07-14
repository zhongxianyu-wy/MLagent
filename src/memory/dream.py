from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DreamJob:
    dream_job_id: str
    status: str
    memory_scope: list[str]
    lease_id: str


class DreamService:
    IDLE_SECONDS = 7200
    LEASE_TTL_SECONDS = 600

    def __init__(
        self,
        lease_store,
        run_state,
        last_user_instruction_at: int,
    ) -> None:
        self.lease_store = lease_store
        self.run_state = run_state
        self.last_user_instruction_at = last_user_instruction_at

    def maybe_start_idle_dream(
        self, now: int, owner_id: str
    ) -> DreamJob | None:
        if now - self.last_user_instruction_at < self.IDLE_SECONDS:
            return None
        if self.run_state.has_active_run():
            return None
        if self.run_state.has_active_skill_optimization():
            return None

        lease = self.lease_store.acquire_lease(
            "dream", owner_id, now, self.LEASE_TTL_SECONDS
        )
        if lease is None:
            return None

        return DreamJob(
            dream_job_id=f"dream-{now}",
            status="pending",
            memory_scope=["semantic", "episodic"],
            lease_id=lease.lease_id,
        )
