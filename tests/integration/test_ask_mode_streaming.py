from src.frontend_api.conversation_service import ConversationService
from urllib.error import HTTPError
from io import BytesIO


class FakeLLM:
    def stream(self, prompt):
        yield "AUC"
        yield " 是排序指标"


class ToolSpy:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return call


def test_ask_mode_streams_answer_without_tool_calls():
    tools = ToolSpy()
    service = ConversationService(llm=FakeLLM(), tools=tools)

    chunks = list(service.stream_ask("session-1", "什么是 AUC？"))

    assert chunks == ["AUC", " 是排序指标"]
    assert tools.calls == []


def test_ask_mode_without_llm_returns_configuration_message():
    service = ConversationService()

    chunks = list(service.stream_ask("session-1", "你好"))

    assert chunks == ["LLM provider is not configured. Please set MLAGENT_LLM_* in .env."]


def test_ask_mode_returns_readable_message_when_llm_http_auth_fails():
    class AuthFailingLLM:
        def stream(self, prompt):
            raise HTTPError(
                url="https://api.example.test/v1/messages",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=BytesIO(b'{"error":"unauthorized"}'),
            )

    service = ConversationService(llm=AuthFailingLLM())

    chunks = list(service.stream_ask("session-1", "hello"))

    assert chunks == ["LLM request failed with HTTP 401: Unauthorized"]


def test_ask_mode_returns_readable_message_when_generator_llm_http_auth_fails():
    class GeneratorAuthFailingLLM:
        def stream(self, prompt):
            if False:
                yield ""
            raise HTTPError(
                url="https://api.example.test/v1/messages",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=BytesIO(b'{"error":"unauthorized"}'),
            )

    service = ConversationService(llm=GeneratorAuthFailingLLM())

    chunks = list(service.stream_ask("session-1", "hello"))

    assert chunks == ["LLM request failed with HTTP 401: Unauthorized"]
