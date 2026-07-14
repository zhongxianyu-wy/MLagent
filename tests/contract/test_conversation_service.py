from src.agent.dialogue import ConversationStore


def test_conversation_store_creates_session_and_records_turn(tmp_path):
    store = ConversationStore(str(tmp_path / "conversation.db"), clock=lambda: 123)

    session = store.start_session(session_id="session-1")
    turn = store.add_turn(
        session_id=session.session_id,
        turn_id="turn-1",
        raw_user_text="/ask hello",
        runtime_mode="ask",
        parsed_command="ask",
        natural_language_tail="hello",
        streaming=True,
        tool_calls_allowed=False,
        linked_experiment_id=None,
    )

    assert session.session_id == "session-1"
    assert session.history_json == "[]"
    assert turn.turn_id == "turn-1"
    assert store.list_turns("session-1") == [turn]


def test_conversation_store_updates_pending_question(tmp_path):
    store = ConversationStore(str(tmp_path / "conversation.db"), clock=lambda: 123)
    store.start_session(session_id="session-1")

    updated = store.update_pending_question(
        session_id="session-1",
        pending_question="是否已有独立测试集？",
    )

    assert updated.pending_question == "是否已有独立测试集？"
    assert updated.updated_at == 123
