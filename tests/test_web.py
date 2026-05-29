from __future__ import annotations

from dataclasses import asdict

from jurispeed_challenge.agents import ConversationSession
from jurispeed_challenge.types import AgentRunResult, ToolCallTrace
from jurispeed_challenge.web import create_app


class FakeOrchestrator:
    def run(self, user_text: str, session: ConversationSession) -> AgentRunResult:
        assistant_text = f"Respuesta simulada para: {user_text}"
        session.add_turn(user_text, assistant_text)
        return AgentRunResult(text=assistant_text, messages=list(session.history), tool_calls=[])


class FakeOrchestratorWithActivities:
    def run(self, user_text: str, session: ConversationSession) -> AgentRunResult:
        assistant_text = "Respuesta final consolidada."
        session.add_turn(user_text, assistant_text)
        return AgentRunResult(
            text=assistant_text,
            messages=list(session.history),
            tool_calls=[
                ToolCallTrace(
                    tool_name="route_to_litigante",
                    tool_use_id="toolu_litigante",
                    tool_input={"query": user_text},
                    tool_result={
                        "agent": "litigante",
                        "color": "#3b82f6",
                        "answer": "Texto largo que no deberia verse completo en actividad.",
                        "tool_calls": [
                            asdict(
                                ToolCallTrace(
                                    tool_name="search_jurisprudencia",
                                    tool_use_id="toolu_search",
                                    tool_input={"query": user_text, "top_k": 3},
                                    tool_result={"count": 2, "results": [{"id": "ROL-1"}]},
                                )
                            )
                        ],
                    },
                ),
                ToolCallTrace(
                    tool_name="synthesize",
                    tool_use_id="toolu_sintesis",
                    tool_input={"results": []},
                    tool_result={"agent": "orchestrator"},
                ),
            ],
        )


def test_chat_endpoint_persists_messages_in_session() -> None:
    app = create_app(orchestrator=FakeOrchestrator())
    client = app.test_client()

    response = client.post("/api/chat", json={"message": "Hola"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["assistant"]["text"] == "Respuesta simulada para: Hola"
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][1]["role"] == "assistant"


def test_reset_session_clears_history() -> None:
    app = create_app(orchestrator=FakeOrchestrator())
    client = app.test_client()

    client.post("/api/chat", json={"message": "Hola"})
    reset_response = client.post("/api/session/reset")
    state_response = client.get("/api/state")

    assert reset_response.status_code == 200
    assert state_response.get_json()["messages"] == []


def test_chat_endpoint_returns_compact_agent_activities() -> None:
    app = create_app(orchestrator=FakeOrchestratorWithActivities())
    client = app.test_client()

    response = client.post("/api/chat", json={"message": "Hola"})

    assert response.status_code == 200
    payload = response.get_json()
    activities = payload["assistant"]["activities"]
    assert activities[0]["summary"] == "Definio la ruta."
    assert activities[1]["summary"] == "Busco jurisprudencia."
    assert activities[1]["detail"] == "2 resultado(s)."
    assert "Texto largo" not in activities[1]["summary"]
