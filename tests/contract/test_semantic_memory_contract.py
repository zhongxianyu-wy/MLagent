from src.memory.metadata_index import MetadataIndex
from src.memory.semantic import SemanticMemory
from src.models import MemoryEntry


class FakeVectorStore:
    def __init__(self):
        self.entries = {}

    def add(self, memory_id, text):
        self.entries[memory_id] = text

    def search(self, query, top_k):
        return [
            {"memory_id": memory_id, "text": text}
            for memory_id, text in list(self.entries.items())[:top_k]
            if query.lower() in text.lower()
        ]


def test_semantic_memory_preserves_sqlite_metadata_on_search(tmp_path):
    index = MetadataIndex(str(tmp_path / "memory.db"))
    semantic = SemanticMemory(vector_store=FakeVectorStore(), metadata_index=index)
    entry = MemoryEntry(
        memory_id="mem-1",
        source="agent",
        text="variance filtering improved auc on methylation features",
        linked_experiment_id="exp-1",
        linked_round_id="round-2",
        linked_skill_id="skill-3",
        confidence="high",
        needs_review=False,
        created_at=123,
    )

    semantic.add(entry)

    results = semantic.search("variance", top_k=5)
    assert results == [entry]
