from src.frontend_api.conversation_service import ConversationService


class FakeRunService:
    def __init__(self):
        self.requests = []

    def start_run(self, request):
        self.requests.append(request)
        return {"experiment_id": "exp-1", "status": "created"}


def test_promote_ready_plan_to_agent_run_requires_explicit_confirmation():
    run_service = FakeRunService()
    service = ConversationService(run_service=run_service)
    service.save_validation_plan(
        session_id="session-1",
        plan={
            "plan_id": "plan-1",
            "status": "ready",
            "harness_id": "explore",
            "objective": "auc",
            "dataset_ref": "demo",
        },
    )

    run = service.promote_plan(
        session_id="session-1",
        plan_id="plan-1",
        confirmed=True,
    )

    assert run == {"experiment_id": "exp-1", "status": "created"}
    assert run_service.requests == [
        {
            "mode": "agent",
            "harness_id": "explore",
            "plan_id": "plan-1",
            "dataset_ref": "demo",
            "objective": "auc",
        }
    ]


def test_promote_plan_rejects_unconfirmed_or_draft_plan():
    service = ConversationService(run_service=FakeRunService())
    service.save_validation_plan(
        session_id="session-1",
        plan={"plan_id": "plan-1", "status": "draft", "harness_id": "explore"},
    )

    try:
        service.promote_plan("session-1", "plan-1", confirmed=True)
    except ValueError as exc:
        assert "ready" in str(exc)
    else:
        raise AssertionError("draft plan should not be promoted")
