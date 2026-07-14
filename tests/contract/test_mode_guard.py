from src.agent.mode_guard import ModeCapabilityPolicy, ModeGuard


def test_ask_mode_blocks_project_tool_calls():
    guard = ModeGuard.default()

    decision = guard.authorize(
        mode="ask",
        service_method="RunService.start_run",
        mutation_type="experiment_run",
    )

    assert decision.allowed is False
    assert decision.blocked_pattern == "ask:RunService.start_run"


def test_plan_mode_allows_validation_plan_write_but_blocks_training():
    guard = ModeGuard.default()

    allowed = guard.authorize(
        mode="plan",
        service_method="ConversationService.build_validation_plan",
        mutation_type="validation_plan",
    )
    blocked = guard.authorize(
        mode="plan",
        service_method="RunService.start_run",
        mutation_type="experiment_run",
    )

    assert allowed.allowed is True
    assert blocked.allowed is False
    assert blocked.blocked_pattern == "plan:RunService.start_run"


def test_agent_mode_allows_service_calls_but_policy_can_disable_file_writes():
    guard = ModeGuard(
        policies={
            "agent": ModeCapabilityPolicy(
                mode="agent",
                allowed_service_methods={"RunService.start_run"},
                allowed_mutations={"experiment_run"},
                allow_file_writes=False,
                allow_training_execution=True,
                allow_skill_mutation=False,
            )
        }
    )

    decision = guard.authorize(
        mode="agent",
        service_method="RunService.start_run",
        mutation_type="file_write",
    )

    assert decision.allowed is False
    assert decision.blocked_pattern == "agent:file_write"
