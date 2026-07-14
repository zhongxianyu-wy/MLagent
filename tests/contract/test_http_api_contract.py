from src.api.app import create_app


class FakeConversationService:
    def __init__(self):
        self.turns = []

    def start_session(self, session_id):
        return {"session_id": session_id, "history": []}

    def handle_turn(self, session_id, user_text):
        self.turns.append((session_id, user_text))
        return {"mode": "ask", "chunks": ["hello"]}

    def stream_ask(self, session_id, user_text):
        yield "hello"
        yield " world"


class FakeRunService:
    def get_status(self, experiment_id):
        return {"experiment_id": experiment_id, "status": "running"}

    def list_rounds(self, experiment_id):
        return [{"round_id": "round-1", "experiment_id": experiment_id}]

    def stop_run(self, experiment_id, reason):
        return {"experiment_id": experiment_id, "status": "stopped", "reason": reason}


class FakeMemoryService:
    def search(self, query, top_k=5):
        return [{"memory_id": "mem-1", "text": query, "top_k": top_k}]


def test_conversation_routes_start_session_and_submit_turn():
    app = create_app(conversation_service=FakeConversationService())

    created = app.handle("POST", "/api/conversations", json={"session_id": "s1"})
    turn = app.handle(
        "POST",
        "/api/conversations/s1/turns",
        json={"user_text": "/ask hi"},
    )

    assert created.status_code == 201
    assert created.json == {"session_id": "s1", "history": []}
    assert turn.status_code == 200
    assert turn.json == {"mode": "ask", "chunks": ["hello"]}


def test_conversation_stream_route_returns_sse_chunks():
    app = create_app(conversation_service=FakeConversationService())

    response = app.handle(
        "GET",
        "/api/conversations/s1/stream",
        query={"user_text": "hi"},
    )

    assert response.status_code == 200
    assert response.media_type == "text/event-stream"
    assert list(response.stream) == ["data: hello\n\n", "data:  world\n\n"]


def test_run_and_memory_routes_expose_frontend_state():
    app = create_app(
        run_service=FakeRunService(),
        memory_service=FakeMemoryService(),
    )

    status = app.handle("GET", "/api/runs/exp-1")
    rounds = app.handle("GET", "/api/runs/exp-1/rounds")
    stopped = app.handle(
        "POST",
        "/api/runs/exp-1/stop",
        json={"reason": "user_stop"},
    )
    memory = app.handle("GET", "/api/memory/search", query={"q": "auc", "top_k": "3"})

    assert status.json == {"experiment_id": "exp-1", "status": "running"}
    assert rounds.json == [{"round_id": "round-1", "experiment_id": "exp-1"}]
    assert stopped.json == {
        "experiment_id": "exp-1",
        "status": "stopped",
        "reason": "user_stop",
    }
    assert memory.json == [{"memory_id": "mem-1", "text": "auc", "top_k": 3}]
