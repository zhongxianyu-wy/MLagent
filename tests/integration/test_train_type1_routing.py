from pathlib import Path

from src.agent.slash_commands import load_harnesses
from src.frontend_api.conversation_service import ConversationService


class FakeRunService:
    def __init__(self):
        self.requests = []

    def start_run(self, request):
        self.requests.append(request)
        return {"experiment_id": "exp-1", "status": "created"}


def test_train_type1_routes_to_agent_exploration_with_tail_preserved():
    runs = FakeRunService()
    service = ConversationService(
        run_service=runs,
        harnesses=load_harnesses(Path("config/harnesses.toml")),
    )

    result = service.handle_turn(
        session_id="session-1",
        user_text="/train_type1 用 demo 做特征探索，目标 AUC",
    )

    assert result["mode"] == "agent"
    assert result["domain_action"] == "explore"
    assert result["natural_language_tail"] == "用 demo 做特征探索，目标 AUC"
    assert runs.requests == [
        {
            "mode": "agent",
            "harness_id": "explore",
            "domain_action": "explore",
            "natural_language_tail": "用 demo 做特征探索，目标 AUC",
        }
    ]
