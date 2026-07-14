from __future__ import annotations

import uuid
from collections.abc import Callable

from src.frontend_api.conversation_service import ConversationService
from src.provider.client import LLMClient
from src.provider.config import load_provider_config


class ChatShell:
    def __init__(
        self,
        conversation_service: ConversationService | None = None,
        session_id: str | None = None,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
    ) -> None:
        self.conversation_service = conversation_service or ConversationService(
            llm=LLMClient(load_provider_config())
        )
        self.session_id = session_id or str(uuid.uuid4())
        self.input_func = input_func
        self.output_func = output_func

    def run(self) -> int:
        while True:
            user_text = self.input_func("mlagent> ")
            if user_text.strip() in {"/exit", "exit", "quit"}:
                return 0
            result = self.conversation_service.handle_turn(self.session_id, user_text)
            for chunk in result.get("chunks", []):
                self.output_func(chunk)
