from src.skill_bridge.optimizer import SkillOptimizer


class FakeSkillStore:
    def __init__(self):
        self.backups = []

    def backup(self, skill_id):
        self.backups.append(skill_id)
        return f"backups/{skill_id}.tar"


class FakeEvaluator:
    def __init__(self):
        self.requests = []

    def compare(self, skill_id, candidate_path, dataset_id, repeat_count, selection_metric):
        self.requests.append(
            {
                "skill_id": skill_id,
                "candidate_path": candidate_path,
                "dataset_id": dataset_id,
                "repeat_count": repeat_count,
                "selection_metric": selection_metric,
            }
        )
        return {
            "old": {"cv_auc": 0.8, "test_auc": 0.82},
            "candidate": {"cv_auc": 0.85, "test_auc": 0.81},
            "selected_by": "training_cv_only",
        }


def test_skill_optimizer_requires_dataset_approval():
    optimizer = SkillOptimizer(skill_store=FakeSkillStore(), evaluator=FakeEvaluator())

    try:
        optimizer.optimize_skill(
            skill_id="skill-1",
            dataset_id="dataset-1",
            dataset_approved=False,
            repeat_count=3,
            max_runtime_minutes=60,
            selection_metric="auc",
        )
    except ValueError as exc:
        assert "dataset approval" in str(exc)
    else:
        raise AssertionError("unapproved dataset should be rejected")


def test_skill_optimizer_backs_up_and_uses_training_cv_only_selection():
    store = FakeSkillStore()
    evaluator = FakeEvaluator()
    optimizer = SkillOptimizer(skill_store=store, evaluator=evaluator)

    job = optimizer.optimize_skill(
        skill_id="skill-1",
        dataset_id="dataset-1",
        dataset_approved=True,
        repeat_count=3,
        max_runtime_minutes=60,
        selection_metric="auc",
    )

    assert store.backups == ["skill-1"]
    assert job.backup_path == "backups/skill-1.tar"
    assert job.dataset_approval_status == "approved"
    assert job.repeat_count == 3
    assert job.max_runtime_minutes == 60
    assert job.leakage_policy == "train_cv_only_for_selection"
    assert job.performance_comparison["selected_by"] == "training_cv_only"
