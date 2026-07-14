from src.memory.metadata_index import MetadataIndex
from src.memory.semantic import SemanticMemory
from src.memory.skill_linker import SkillLinker
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


def test_memory_to_skill_candidate_linkage_preserves_evidence_metadata(tmp_path):
    db_path = str(tmp_path / "memory.db")
    semantic = SemanticMemory(
        vector_store=FakeVectorStore(),
        metadata_index=MetadataIndex(db_path),
    )
    linker = SkillLinker(db_path)
    entry = MemoryEntry(
        memory_id="mem-1",
        source="agent",
        text="low variance filtering was unstable on dataset alpha",
        linked_experiment_id="exp-1",
        linked_round_id="round-1",
        linked_skill_id=None,
        confidence="medium",
        needs_review=False,
        created_at=123,
    )
    semantic.add(entry)

    linker.link_memory_to_skill(memory_id="mem-1", candidate_id="candidate-1")

    evidence = linker.list_candidate_evidence("candidate-1")
    assert evidence == [entry]
