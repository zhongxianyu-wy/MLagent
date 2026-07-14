from src.frontend_api.memory_service import MemoryService
from src.models import MemoryEntry


class FakeSemanticMemory:
    def __init__(self):
        self.entries = []
        self.queries = []

    def add(self, entry):
        self.entries.append(entry)

    def search(self, query, top_k=5):
        self.queries.append((query, top_k))
        return self.entries[:top_k]


def test_memory_service_adds_experience_with_round_linkage():
    semantic = FakeSemanticMemory()
    service = MemoryService(
        semantic_memory=semantic,
        id_factory=lambda: "mem-1",
        clock=lambda: 123,
    )

    entry = service.add_experience(
        round_id="round-1",
        summary="variance filter improved auc",
        confidence="high",
    )

    assert entry == MemoryEntry(
        memory_id="mem-1",
        source="agent",
        text="variance filter improved auc",
        linked_experiment_id=None,
        linked_round_id="round-1",
        linked_skill_id=None,
        confidence="high",
        needs_review=False,
        created_at=123,
    )
    assert semantic.entries == [entry]


def test_memory_service_get_related_context_searches_dataset_and_objective():
    semantic = FakeSemanticMemory()
    service = MemoryService(
        semantic_memory=semantic,
        id_factory=lambda: "mem-1",
        clock=lambda: 123,
    )

    service.get_related_context(dataset_id="dataset-1", objective="auc", top_k=3)

    assert semantic.queries == [("dataset-1 auc", 3)]
