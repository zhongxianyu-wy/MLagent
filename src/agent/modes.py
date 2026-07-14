from __future__ import annotations

from src.agent.slash_commands import parse_slash_command


PLAN_KEYWORDS = ("设计", "方案", "plan", "规划", "验证方案")
AGENT_KEYWORDS = ("运行", "执行", "训练", "探索", "复现", "沉淀", "调研")


def classify_runtime_mode(user_text: str) -> str:
    parsed = parse_slash_command(user_text)
    if parsed is not None:
        return parsed.mode
    if user_text.strip().startswith("/"):
        return "ask"

    lowered = user_text.lower()
    if any(keyword in lowered for keyword in PLAN_KEYWORDS):
        return "plan"
    if any(keyword in lowered for keyword in AGENT_KEYWORDS):
        return "agent"
    return "ask"
