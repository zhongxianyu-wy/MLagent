from __future__ import annotations

from typing import Protocol
from urllib.error import HTTPError

from src.agent.mode_guard import ModeGuard
from src.agent.modes import classify_runtime_mode
from src.agent.slash_commands import FunctionalHarness, parse_slash_command


class RunServiceLike(Protocol):
    def start_run(self, request: dict) -> object:
        ...


class ConversationService:
    def __init__(
        self,
        run_service: RunServiceLike | None = None,
        llm: object | None = None,
        tools: object | None = None,
        memory_service: object | None = None,
        harnesses: list[FunctionalHarness] | None = None,
        mode_guard: ModeGuard | None = None,
    ) -> None:
        self.run_service = run_service
        self.llm = llm
        self.tools = tools
        self.memory_service = memory_service
        self.harnesses = harnesses or []
        self.mode_guard = mode_guard or ModeGuard.default()
        self._sessions: dict[str, dict] = {}
        self._plans: dict[tuple[str, str], dict] = {}

    def start_session(self, session_id: str) -> dict:
        session = {"session_id": session_id, "history": []}
        self._sessions[session_id] = session
        return session

    def classify_turn(self, session_id: str, user_text: str) -> str:
        return classify_runtime_mode(user_text)

    def parse_slash_command(self, user_text: str):
        return parse_slash_command(user_text, harnesses=self.harnesses)

    def list_commands(self) -> list:
        commands = []
        for harness in self.harnesses:
            for command in harness.commands:
                commands.append(
                    type(
                        "SlashCommand",
                        (),
                        {
                            "name": command.removeprefix("/"),
                            "mode": "agent",
                            "domain_action": harness.domain_action,
                        },
                    )()
                )
        return commands

    def save_validation_plan(self, session_id: str, plan: dict) -> dict:
        self._plans[(session_id, plan["plan_id"])] = plan
        return plan

    def promote_plan(
        self, session_id: str, plan_id: str, confirmed: bool
    ) -> object:
        if not confirmed:
            raise ValueError("plan promotion requires explicit confirmation")
        plan = self._plans[(session_id, plan_id)]
        if plan.get("status") != "ready":
            raise ValueError("validation plan must be ready before promotion")
        if self.run_service is None:
            raise ValueError("run_service is required for plan promotion")
        decision = self.mode_guard.authorize(
            mode="agent",
            service_method="RunService.start_run",
            mutation_type="experiment_run",
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)

        return self.run_service.start_run(
            {
                "mode": "agent",
                "harness_id": plan["harness_id"],
                "plan_id": plan["plan_id"],
                "dataset_ref": plan.get("dataset_ref"),
                "objective": plan.get("objective"),
            }
        )

    def stream_ask(self, session_id: str, user_text: str):
        if self.llm is None:
            return iter(["LLM provider is not configured. Please set MLAGENT_LLM_* in .env."])
        return self._safe_llm_stream(user_text)

    def _safe_llm_stream(self, user_text: str):
        try:
            for chunk in self.llm.stream(user_text):
                yield chunk
        except HTTPError as exc:
            yield f"LLM request failed with HTTP {exc.code}: {exc.reason}"

    def build_validation_plan(self, session_id: str, user_text: str) -> dict:
        decision = self.mode_guard.authorize(
            mode="plan",
            service_method="ConversationService.build_validation_plan",
            mutation_type="validation_plan",
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        dataset_ref = "demo" if "demo" in user_text else None
        objective = "auc" if "AUC" in user_text or "auc" in user_text.lower() else ""
        if self.memory_service is not None and dataset_ref and objective:
            self.memory_service.get_related_context(dataset_ref, objective, top_k=5)

        plan = {
            "plan_id": f"{session_id}-plan-1",
            "session_id": session_id,
            "status": "draft",
            "harness_id": "explore",
            "dataset_ref": dataset_ref,
            "objective": objective,
            "open_questions": ["是否已有独立测试集，还是需要随机划分？"],
        }
        return self.save_validation_plan(session_id, plan)

    def handle_turn(self, session_id: str, user_text: str) -> dict:
        parsed = parse_slash_command(user_text, harnesses=self.harnesses)
        if parsed is None:
            mode = self.classify_turn(session_id, user_text)
            if mode == "agent":
                return self._handle_agent_turn(
                    session_id=session_id,
                    domain_action=self._infer_domain_action(user_text),
                    natural_language_tail=user_text,
                    harness_id=self._infer_harness_id(user_text),
                )
            if mode == "plan":
                return self.build_validation_plan(session_id, user_text)
            return {"mode": "ask", "chunks": list(self.stream_ask(session_id, user_text))}
        if parsed.mode == "agent":
            return self._handle_agent_turn(
                session_id=session_id,
                domain_action=parsed.domain_action,
                natural_language_tail=parsed.natural_language_tail,
                harness_id=parsed.alias_source or parsed.domain_action,
            )
        if parsed.mode == "plan":
            return self.build_validation_plan(session_id, parsed.natural_language_tail)
        return {"mode": "ask", "chunks": list(self.stream_ask(session_id, parsed.natural_language_tail))}

    def _handle_agent_turn(
        self,
        session_id: str,
        domain_action: str | None,
        natural_language_tail: str,
        harness_id: str | None,
    ) -> dict:
        if self.run_service is None:
            raise ValueError("run_service is required for agent turns")
        decision = self.mode_guard.authorize(
            mode="agent",
            service_method="RunService.start_run",
            mutation_type="experiment_run",
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        run_request = {
            "mode": "agent",
            "harness_id": harness_id or domain_action,
            "domain_action": domain_action,
            "natural_language_tail": natural_language_tail,
        }
        self.run_service.start_run(run_request)
        return {
            "mode": "agent",
            "domain_action": domain_action,
            "natural_language_tail": natural_language_tail,
        }

    def _infer_domain_action(self, user_text: str) -> str:
        lowered = user_text.lower()
        if "复现" in lowered:
            return "reproduce"
        if "沉淀" in lowered:
            return "distill"
        if "调研" in lowered:
            return "research"
        if "验证" in lowered:
            return "interactive_validate"
        return "explore"

    def _infer_harness_id(self, user_text: str) -> str | None:
        domain_action = self._infer_domain_action(user_text)
        for harness in self.harnesses:
            if harness.domain_action == domain_action:
                return harness.harness_id
        return domain_action
