from src.agent.chat_shell import ChatShell
from src.frontend_api.conversation_service import ConversationService


class FakeConversationService:
    def __init__(self):
        self.turns = []

    def handle_turn(self, session_id, user_text):
        self.turns.append((session_id, user_text))
        return {"mode": "ask", "chunks": ["ok"]}


def test_chat_shell_processes_until_exit_command():
    service = FakeConversationService()
    outputs = []
    inputs = iter(["/ask hi", "/exit"])
    shell = ChatShell(
        conversation_service=service,
        session_id="session-1",
        input_func=lambda prompt: next(inputs),
        output_func=outputs.append,
    )

    exit_code = shell.run()

    assert exit_code == 0
    assert service.turns == [("session-1", "/ask hi")]
    assert outputs == ["ok"]


def test_chat_shell_default_service_has_configured_llm(monkeypatch):
    monkeypatch.setenv("MLAGENT_LLM_PROVIDER_NAME", "minimax")
    monkeypatch.setenv("MLAGENT_LLM_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("MLAGENT_LLM_API_KEY_ENV", "MINIMAX_API_KEY")
    monkeypatch.setenv("MINIMAX_API_KEY", "secret")
    monkeypatch.setenv("MLAGENT_LLM_MODEL", "MiniMax-M2.7")

    shell = ChatShell(input_func=lambda prompt: "/exit")

    assert isinstance(shell.conversation_service, ConversationService)
    assert shell.conversation_service.llm is not None
    assert shell.conversation_service.llm.default_model == "MiniMax-M2.7"
