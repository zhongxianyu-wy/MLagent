from src.frontend_api.conversation_service import ConversationService


class FakeMemoryService:
    def __init__(self):
        self.queries = []

    def get_related_context(self, dataset_id, objective, top_k=5):
        self.queries.append((dataset_id, objective, top_k))
        return []


class FakeRunService:
    def __init__(self):
        self.calls = []

    def start_run(self, request):
        self.calls.append(request)


def test_plan_mode_reads_memory_and_creates_draft_validation_plan_without_execution():
    memory = FakeMemoryService()
    runs = FakeRunService()
    service = ConversationService(memory_service=memory, run_service=runs)

    plan = service.build_validation_plan(
        session_id="session-1",
        user_text="用 demo 设计 AUC 特征探索方案",
    )

    assert plan["status"] == "draft"
    assert plan["dataset_ref"] == "demo"
    assert plan["objective"] == "auc"
    assert plan["open_questions"] == ["是否已有独立测试集，还是需要随机划分？"]
    assert memory.queries == [("demo", "auc", 5)]
    assert runs.calls == []
