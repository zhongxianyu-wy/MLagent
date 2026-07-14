from __future__ import annotations

from dataclasses import dataclass

from src.models import SafetyDecision


@dataclass(frozen=True)
class ModeCapabilityPolicy:
    mode: str
    allowed_service_methods: set[str]
    allowed_mutations: set[str]
    allow_file_writes: bool
    allow_training_execution: bool
    allow_skill_mutation: bool


class ModeGuard:
    def __init__(self, policies: dict[str, ModeCapabilityPolicy]) -> None:
        self.policies = policies

    @classmethod
    def default(cls) -> "ModeGuard":
        return cls(
            policies={
                "ask": ModeCapabilityPolicy(
                    mode="ask",
                    allowed_service_methods={"ConversationService.stream_ask"},
                    allowed_mutations={"conversation_history"},
                    allow_file_writes=False,
                    allow_training_execution=False,
                    allow_skill_mutation=False,
                ),
                "plan": ModeCapabilityPolicy(
                    mode="plan",
                    allowed_service_methods={
                        "ConversationService.build_validation_plan",
                        "MemoryService.search",
                        "MemoryService.get_related_context",
                    },
                    allowed_mutations={"validation_plan", "conversation_history"},
                    allow_file_writes=False,
                    allow_training_execution=False,
                    allow_skill_mutation=False,
                ),
                "agent": ModeCapabilityPolicy(
                    mode="agent",
                    allowed_service_methods={"*"},
                    allowed_mutations={"*"},
                    allow_file_writes=True,
                    allow_training_execution=True,
                    allow_skill_mutation=True,
                ),
            }
        )

    def authorize(
        self,
        mode: str,
        service_method: str,
        mutation_type: str | None = None,
    ) -> SafetyDecision:
        policy = self.policies[mode]
        if not self._method_allowed(policy, service_method):
            return self._deny(mode, service_method)
        if mutation_type is not None and not self._mutation_allowed(
            policy, mutation_type
        ):
            return self._deny(mode, mutation_type)
        return SafetyDecision(
            allowed=True,
            reason="Mode capability allowed",
            blocked_pattern=None,
            requires_user_approval=False,
        )

    def _method_allowed(
        self, policy: ModeCapabilityPolicy, service_method: str
    ) -> bool:
        return "*" in policy.allowed_service_methods or service_method in policy.allowed_service_methods

    def _mutation_allowed(self, policy: ModeCapabilityPolicy, mutation_type: str) -> bool:
        if mutation_type == "file_write" and not policy.allow_file_writes:
            return False
        if mutation_type == "training_execution" and not policy.allow_training_execution:
            return False
        if mutation_type == "skill_mutation" and not policy.allow_skill_mutation:
            return False
        return "*" in policy.allowed_mutations or mutation_type in policy.allowed_mutations

    def _deny(self, mode: str, blocked: str) -> SafetyDecision:
        return SafetyDecision(
            allowed=False,
            reason="Mode capability blocked",
            blocked_pattern=f"{mode}:{blocked}",
            requires_user_approval=False,
        )
