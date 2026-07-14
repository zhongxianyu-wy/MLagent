from pathlib import Path

from src.agent.slash_commands import load_harnesses
from src.frontend_api.conversation_service import ConversationService


class FakeRunService:
    def __init__(self):
        self.requests = []

    def start_run(self, request):
        self.requests.append(request)
        return {"experiment_id": "exp-1", "status": "running"}


class FakeMemoryService:
    def get_related_context(self, dataset_id, objective, top_k=5):
        return []


def test_natural_language_agent_turn_routes_through_mode_guard():
    runs = FakeRunService()
    service = ConversationService(
        run_service=runs,
        memory_service=FakeMemoryService(),
        harnesses=load_harnesses(Path("config/harnesses.toml")),
    )

    result = service.handle_turn("session-1", "运行 demo 数据的特征探索，目标 AUC")

    assert result["mode"] == "agent"
    assert result["domain_action"] == "explore"
    assert runs.requests[0]["mode"] == "agent"
    assert runs.requests[0]["domain_action"] == "explore"


def test_plan_turn_cannot_start_training_even_when_text_says_execute():
    runs = FakeRunService()
    service = ConversationService(
        run_service=runs,
        memory_service=FakeMemoryService(),
    )

    result = service.handle_turn("session-1", "/plan 设计并执行 demo AUC 探索")

    assert result["status"] == "draft"
    assert runs.requests == []
