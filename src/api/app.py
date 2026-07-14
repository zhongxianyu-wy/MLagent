from __future__ import annotations

from src.api.routes import ApiRouter


def create_app(
    conversation_service=None,
    run_service=None,
    memory_service=None,
) -> ApiRouter:
    return ApiRouter(
        conversation_service=conversation_service,
        run_service=run_service,
        memory_service=memory_service,
    )
