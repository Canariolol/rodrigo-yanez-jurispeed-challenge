from __future__ import annotations

import subprocess
from dataclasses import asdict
from unittest.mock import patch

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


def test_chat_persists_history(test_report) -> None:
    app = create_app(orchestrator=FakeOrchestrator())
    client = app.test_client()

    response = client.post("/api/chat", json={"message": "Hola"})

    assert response.status_code == 200
    payload = response.get_json()
    test_report.set_checked(
        "El endpoint /api/chat guarda user y assistant en la sesion conversacional."
    )
    test_report.set_setup("POST /api/chat con JSON {'message': 'Hola'} usando orquestador fake.")
    test_report.set_observed(
        "assistant.text='Respuesta simulada para: Hola' y messages contiene user+assistant."
    )
    test_report.add_step("El cliente envia una consulta corta al endpoint de chat.")
    test_report.add_step("El orquestador fake agrega el turno y devuelve la respuesta simulada.")
    test_report.add_step("La API responde con el historial persistido en la sesion.")
    assert payload["assistant"]["text"] == "Respuesta simulada para: Hola"
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][1]["role"] == "assistant"


def test_reset_session_clears_history(test_report) -> None:
    app = create_app(orchestrator=FakeOrchestrator())
    client = app.test_client()

    client.post("/api/chat", json={"message": "Hola"})
    reset_response = client.post("/api/session/reset")
    state_response = client.get("/api/state")

    assert reset_response.status_code == 200
    test_report.set_checked(
        "El endpoint /api/session/reset elimina el historial guardado en la sesion."
    )
    test_report.set_setup(
        "Se crea primero una conversacion y luego se llama POST /api/session/reset."
    )
    test_report.set_observed(
        "El reset responde 200 y GET /api/state devuelve messages=[]"
    )
    test_report.add_step("Primero se registra un turno en la sesion con /api/chat.")
    test_report.add_step("Luego /api/session/reset elimina la referencia de la sesion activa.")
    test_report.add_step("El estado posterior confirma que el historial quedo vacio.")
    assert state_response.get_json()["messages"] == []


def test_chat_summarizes_agent_activity(test_report) -> None:
    app = create_app(orchestrator=FakeOrchestratorWithActivities())
    client = app.test_client()

    response = client.post("/api/chat", json={"message": "Hola"})

    assert response.status_code == 200
    payload = response.get_json()
    activities = payload["assistant"]["activities"]
    test_report.set_checked(
        "La API de chat devuelve actividades compactas en vez de exponer respuestas largas de agentes."
    )
    test_report.set_setup(
        "POST /api/chat con un orquestador fake que devuelve route_to_litigante + synthesize."
    )
    test_report.set_observed(
        "Las actividades muestran 'Definio la ruta.', 'Busco jurisprudencia.' y detail='2 resultado(s).'"
    )
    test_report.add_step("El orquestador fake reporta una ruta al litigante con tool_calls anidados.")
    test_report.add_step("La capa web resume esos tool_calls en una actividad compacta por agente.")
    test_report.add_step("El texto largo del agente no aparece en el summary final enviado al frontend.")
    assert activities[0]["summary"] == "Definio la ruta."
    assert activities[1]["summary"] == "Busco jurisprudencia."
    assert activities[1]["detail"] == "2 resultado(s)."
    assert "Texto largo" not in activities[1]["summary"]


def test_run_tests_maps_detail_to_pytest_flags(test_report) -> None:
    app = create_app(orchestrator=FakeOrchestrator())
    client = app.test_client()

    fake_run = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="3 passed in 0.11s\n", stderr=""
    )
    with patch("jurispeed_challenge.web.subprocess.run", return_value=fake_run) as run_mock:
        response = client.post("/api/tests/run", json={"detail": "full"})

    assert response.status_code == 200
    command = run_mock.call_args.args[0]
    payload = response.get_json()
    test_report.set_checked(
        "El endpoint /api/tests/run mapea el nivel de detalle al flag correcto de pytest."
    )
    test_report.set_setup(
        "POST /api/tests/run con detail='full' y subprocess.run mockeado (sin correr pytest real)."
    )
    test_report.set_observed(
        "El comando incluye --full, status='passed' y summary.passed=3 parseado de la salida."
    )
    test_report.add_step("La GUI pide correr los tests en nivel Full.")
    test_report.add_step("El endpoint traduce 'full' a ['--full'] y arma el comando de pytest.")
    test_report.add_step("La salida simulada se parsea en un resumen estructurado para el frontend.")
    assert "--full" in command
    assert "--color=no" in command
    assert payload["status"] == "passed"
    assert payload["detail"] == "full"
    assert payload["summary"]["passed"] == 3
    assert payload["summary"]["total"] == 3


def test_run_tests_rejects_unknown_detail(test_report) -> None:
    app = create_app(orchestrator=FakeOrchestrator())
    client = app.test_client()

    with patch("jurispeed_challenge.web.subprocess.run") as run_mock:
        response = client.post("/api/tests/run", json={"detail": "verbose"})

    assert response.status_code == 400
    test_report.set_checked(
        "El endpoint /api/tests/run solo acepta niveles de detalle de una lista blanca."
    )
    test_report.set_setup("POST /api/tests/run con detail='verbose', un nivel no soportado.")
    test_report.set_observed("Responde 400 y nunca invoca subprocess.run.")
    test_report.add_step("El cliente envia un nivel de detalle invalido.")
    test_report.add_step("El endpoint valida contra la lista blanca antes de ejecutar nada.")
    test_report.add_step("No se lanza ningun proceso de pytest y se devuelve un error claro.")
    run_mock.assert_not_called()
