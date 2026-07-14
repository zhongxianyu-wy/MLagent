from src.memory.skill_linker import SkillExecutionWriteback


class FakeMemoryService:
    def __init__(self):
        self.experiences = []

    def add_experience(self, round_id, summary, confidence):
        self.experiences.append((round_id, summary, confidence))
        return {"memory_id": "mem-1"}


class FakeRegistry:
    def __init__(self):
        self.used = []

    def record_use(self, skill_id, used_at):
        self.used.append((skill_id, used_at))


def test_skill_execution_writeback_records_memory_and_registry_use():
    memory = FakeMemoryService()
    registry = FakeRegistry()
    writeback = SkillExecutionWriteback(memory_service=memory, registry=registry)

    result = writeback.record_execution(
        skill_id="ngs-xgboost-baseline",
        round_id="round-1",
        metrics={"auc": 0.91},
        used_at=123,
    )

    assert result == {"memory_id": "mem-1"}
    assert memory.experiences == [
        ("round-1", "Skill ngs-xgboost-baseline reproduced with metrics {'auc': 0.91}", "high")
    ]
    assert registry.used == [("ngs-xgboost-baseline", 123)]
