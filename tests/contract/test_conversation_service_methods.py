from pathlib import Path

from src.agent.slash_commands import load_harnesses
from src.frontend_api.conversation_service import ConversationService


def test_conversation_service_exposes_core_methods():
    service = ConversationService(harnesses=load_harnesses(Path("config/harnesses.toml")))

    session = service.start_session(session_id="session-1")
    parsed = service.parse_slash_command("/train_type1 demo")

    assert session["session_id"] == "session-1"
    assert service.classify_turn("session-1", "/plan demo") == "plan"
    assert parsed.domain_action == "explore"
    assert any(command.name == "train_type1" for command in service.list_commands())
