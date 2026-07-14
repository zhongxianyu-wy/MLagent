from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.memory.episodic import EpisodicMemory


@dataclass(frozen=True)
class IdleSchedulerLease:
    lease_id: str
    lease_type: str
    owner_id: str
    acquired_at: int
    heartbeat_at: int
    expires_at: int
    status: str


class IdleSchedulerLeaseStore:
    def __init__(self, db_path: str = "db/experiments.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        EpisodicMemory(db_path)
        self._conn = sqlite3.connect(db_path)

    def acquire_lease(
        self, lease_type: str, owner_id: str, now: int, ttl_seconds: int
    ) -> IdleSchedulerLease | None:
        active = self._active_lease(lease_type)
        if active is not None and active.expires_at > now:
            return None
        if active is not None:
            self.release(active.lease_id, status="expired")

        lease = IdleSchedulerLease(
            lease_id=str(uuid.uuid4()),
            lease_type=lease_type,
            owner_id=owner_id,
            acquired_at=now,
            heartbeat_at=now,
            expires_at=now + ttl_seconds,
            status="active",
        )
        self._conn.execute(
            """
            INSERT INTO idle_scheduler_leases (
                lease_id,
                lease_type,
                owner_id,
                acquired_at,
                heartbeat_at,
                expires_at,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lease.lease_id,
                lease.lease_type,
                lease.owner_id,
                lease.acquired_at,
                lease.heartbeat_at,
                lease.expires_at,
                lease.status,
            ),
        )
        self._conn.commit()
        return lease

    def heartbeat(
        self, lease_id: str, now: int, ttl_seconds: int
    ) -> IdleSchedulerLease:
        self._conn.execute(
            """
            UPDATE idle_scheduler_leases
            SET heartbeat_at = ?, expires_at = ?
            WHERE lease_id = ?
            """,
            (now, now + ttl_seconds, lease_id),
        )
        self._conn.commit()
        return self.get(lease_id)

    def release(self, lease_id: str, status: str) -> IdleSchedulerLease:
        self._conn.execute(
            """
            UPDATE idle_scheduler_leases
            SET status = ?
            WHERE lease_id = ?
            """,
            (status, lease_id),
        )
        self._conn.commit()
        return self.get(lease_id)

    def get(self, lease_id: str) -> IdleSchedulerLease:
        row = self._conn.execute(
            """
            SELECT lease_id, lease_type, owner_id, acquired_at, heartbeat_at, expires_at, status
            FROM idle_scheduler_leases
            WHERE lease_id = ?
            """,
            (lease_id,),
        ).fetchone()
        if row is None:
            raise KeyError(lease_id)
        return IdleSchedulerLease(*row)

    def _active_lease(self, lease_type: str) -> IdleSchedulerLease | None:
        row = self._conn.execute(
            """
            SELECT lease_id, lease_type, owner_id, acquired_at, heartbeat_at, expires_at, status
            FROM idle_scheduler_leases
            WHERE lease_type = ? AND status = 'active'
            ORDER BY acquired_at DESC
            LIMIT 1
            """,
            (lease_type,),
        ).fetchone()
        return None if row is None else IdleSchedulerLease(*row)
