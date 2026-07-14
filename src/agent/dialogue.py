from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from src.memory.episodic import EpisodicMemory
from src.models import ConversationSession, ConversationTurn


class ConversationStore:
    def __init__(
        self,
        db_path: str = "db/experiments.db",
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.db_path = db_path
        self.clock = clock or (lambda: int(time.time()))
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        EpisodicMemory(db_path)
        self._conn = sqlite3.connect(db_path)

    def start_session(self, session_id: str) -> ConversationSession:
        now = self.clock()
        session = ConversationSession(
            session_id=session_id,
            active_experiment_id=None,
            active_dataset_id=None,
            pending_question=None,
            last_slash_command=None,
            last_user_text=None,
            history_json="[]",
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            """
            INSERT INTO conversation_sessions (
                session_id,
                active_experiment_id,
                active_dataset_id,
                pending_question,
                last_slash_command,
                last_user_text,
                history_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.active_experiment_id,
                session.active_dataset_id,
                session.pending_question,
                session.last_slash_command,
                session.last_user_text,
                session.history_json,
                session.created_at,
                session.updated_at,
            ),
        )
        self._conn.commit()
        return session

    def add_turn(
        self,
        session_id: str,
        turn_id: str,
        raw_user_text: str,
        runtime_mode: str,
        parsed_command: str | None,
        natural_language_tail: str,
        streaming: bool,
        tool_calls_allowed: bool,
        linked_experiment_id: str | None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            turn_id=turn_id,
            session_id=session_id,
            raw_user_text=raw_user_text,
            runtime_mode=runtime_mode,
            parsed_command=parsed_command,
            natural_language_tail=natural_language_tail,
            streaming=streaming,
            tool_calls_allowed=tool_calls_allowed,
            linked_experiment_id=linked_experiment_id,
            created_at=self.clock(),
        )
        self._conn.execute(
            """
            INSERT INTO conversation_turns (
                turn_id,
                session_id,
                raw_user_text,
                runtime_mode,
                parsed_command,
                natural_language_tail,
                streaming,
                tool_calls_allowed,
                linked_experiment_id,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn.turn_id,
                turn.session_id,
                turn.raw_user_text,
                turn.runtime_mode,
                turn.parsed_command,
                turn.natural_language_tail,
                int(turn.streaming),
                int(turn.tool_calls_allowed),
                turn.linked_experiment_id,
                turn.created_at,
            ),
        )
        self._conn.commit()
        return turn

    def list_turns(self, session_id: str) -> list[ConversationTurn]:
        rows = self._conn.execute(
            """
            SELECT
                turn_id,
                session_id,
                raw_user_text,
                runtime_mode,
                parsed_command,
                natural_language_tail,
                streaming,
                tool_calls_allowed,
                linked_experiment_id,
                created_at
            FROM conversation_turns
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
        return [
            ConversationTurn(
                turn_id=row[0],
                session_id=row[1],
                raw_user_text=row[2],
                runtime_mode=row[3],
                parsed_command=row[4],
                natural_language_tail=row[5],
                streaming=bool(row[6]),
                tool_calls_allowed=bool(row[7]),
                linked_experiment_id=row[8],
                created_at=row[9],
            )
            for row in rows
        ]

    def update_pending_question(
        self, session_id: str, pending_question: str | None
    ) -> ConversationSession:
        now = self.clock()
        self._conn.execute(
            """
            UPDATE conversation_sessions
            SET pending_question = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (pending_question, now, session_id),
        )
        self._conn.commit()
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> ConversationSession:
        row = self._conn.execute(
            """
            SELECT
                session_id,
                active_experiment_id,
                active_dataset_id,
                pending_question,
                last_slash_command,
                last_user_text,
                history_json,
                created_at,
                updated_at
            FROM conversation_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return ConversationSession(*row)
