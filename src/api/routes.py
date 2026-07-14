from __future__ import annotations

from collections.abc import Iterable

from src.api.schemas import ApiResponse


class ApiRouter:
    def __init__(
        self,
        conversation_service=None,
        run_service=None,
        memory_service=None,
    ) -> None:
        self.conversation_service = conversation_service
        self.run_service = run_service
        self.memory_service = memory_service

    def handle(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        query: dict | None = None,
    ) -> ApiResponse:
        json = json or {}
        query = query or {}
        parts = [part for part in path.split("/") if part]

        if method == "POST" and parts == ["api", "conversations"]:
            session_id = json["session_id"]
            return ApiResponse(
                status_code=201,
                json=self.conversation_service.start_session(session_id),
            )

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["api", "conversations"]
            and parts[3] == "turns"
        ):
            return ApiResponse(
                status_code=200,
                json=self.conversation_service.handle_turn(parts[2], json["user_text"]),
            )

        if (
            method == "GET"
            and len(parts) == 4
            and parts[:2] == ["api", "conversations"]
            and parts[3] == "stream"
        ):
            stream = self._sse(
                self.conversation_service.stream_ask(
                    parts[2], query.get("user_text", "")
                )
            )
            return ApiResponse(
                status_code=200,
                stream=stream,
                media_type="text/event-stream",
            )

        if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "runs"]:
            return ApiResponse(
                status_code=200,
                json=self.run_service.get_status(parts[2]),
            )

        if (
            method == "GET"
            and len(parts) == 4
            and parts[:2] == ["api", "runs"]
            and parts[3] == "rounds"
        ):
            return ApiResponse(
                status_code=200,
                json=self.run_service.list_rounds(parts[2]),
            )

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["api", "runs"]
            and parts[3] == "stop"
        ):
            return ApiResponse(
                status_code=200,
                json=self.run_service.stop_run(parts[2], json["reason"]),
            )

        if method == "GET" and parts == ["api", "memory", "search"]:
            return ApiResponse(
                status_code=200,
                json=self.memory_service.search(
                    query.get("q", ""),
                    top_k=int(query.get("top_k", 5)),
                ),
            )

        return ApiResponse(status_code=404, json={"error": "not_found"})

    def _sse(self, chunks: Iterable[str]) -> Iterable[str]:
        for chunk in chunks:
            yield f"data: {chunk}\n\n"
