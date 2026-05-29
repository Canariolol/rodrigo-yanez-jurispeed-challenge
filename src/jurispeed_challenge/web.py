from __future__ import annotations

import argparse
import os
import secrets
from dataclasses import asdict
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

from jurispeed_challenge.agents import ConversationSession, OrchestratorAgent
from jurispeed_challenge.ai_providers import AIProviderError, ProviderUnavailableError
from jurispeed_challenge.types import AgentRunResult, ToolCallTrace


SESSION_KEY = "jurispeed_session_id"


def create_app(orchestrator: OrchestratorAgent | None = None) -> Flask:
    load_dotenv()
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = os.getenv(
        "FLASK_SECRET_KEY", "jurispeed-dev-secret-key-change-me"
    )
    app.config["JSON_AS_ASCII"] = False
    app.extensions["jurispeed_sessions"] = {}
    app.extensions["jurispeed_orchestrator"] = orchestrator or OrchestratorAgent()

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/health")
    def health() -> Any:
        return jsonify({"status": "ok"})

    @app.get("/api/state")
    def state() -> Any:
        conversation = _get_conversation_session(app)
        return jsonify(
            {
                "session_id": session.get(SESSION_KEY),
                "messages": list(conversation.history),
            }
        )

    @app.post("/api/session/reset")
    def reset_session() -> Any:
        session_id = session.pop(SESSION_KEY, None)
        store = _get_session_store(app)
        if session_id is not None:
            store.pop(session_id, None)
        return jsonify({"status": "ok"})

    @app.post("/api/chat")
    def chat() -> Any:
        payload = request.get_json(silent=True) or {}
        user_text = str(payload.get("message", "")).strip()
        if not user_text:
            return jsonify({"error": "Debes escribir una consulta antes de enviar."}), 400

        orchestrator_instance = _get_orchestrator(app)
        conversation = _get_conversation_session(app)

        try:
            result = orchestrator_instance.run(user_text, conversation)
        except (AIProviderError, ProviderUnavailableError) as exc:
            return jsonify({"error": str(exc)}), 502

        return jsonify(
            {
                "session_id": session.get(SESSION_KEY),
                "assistant": _serialize_run_result(result),
                "messages": list(conversation.history),
            }
        )

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Servidor web del challenge de Jurispeed.ai")
    parser.add_argument("--host", default="127.0.0.1", help="Host para el servidor Flask.")
    parser.add_argument("--port", type=int, default=5000, help="Puerto del servidor Flask.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activa el modo debug de Flask.",
    )
    args = parser.parse_args(argv)

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


def _get_orchestrator(app: Flask) -> OrchestratorAgent:
    return app.extensions["jurispeed_orchestrator"]


def _get_session_store(app: Flask) -> dict[str, ConversationSession]:
    return app.extensions["jurispeed_sessions"]


def _get_conversation_session(app: Flask) -> ConversationSession:
    store = _get_session_store(app)
    session_id = session.get(SESSION_KEY)
    if not session_id:
        session_id = secrets.token_hex(16)
        session[SESSION_KEY] = session_id
    if session_id not in store:
        store[session_id] = ConversationSession()
    return store[session_id]


def _serialize_run_result(result: AgentRunResult) -> dict[str, Any]:
    return {
        "text": result.text,
        "tool_calls": [_serialize_tool_call(tool_call) for tool_call in result.tool_calls],
        "activities": _build_agent_activities(result),
    }


def _serialize_tool_call(tool_call: ToolCallTrace) -> dict[str, Any]:
    return asdict(tool_call)


def _build_agent_activities(result: AgentRunResult) -> list[dict[str, Any]]:
    activities: list[dict[str, Any]] = [
        {
            "agent": "orchestrator",
            "label": "Orquestador",
            "color": "#6366f1",
            "phase": "decision",
            "summary": "Definio la ruta.",
        }
    ]

    for tool_call in result.tool_calls:
        if tool_call.tool_name not in {"route_to_litigante", "route_to_normativo", "synthesize"}:
            continue

        tool_result = tool_call.tool_result if isinstance(tool_call.tool_result, dict) else {}
        if tool_call.tool_name == "synthesize":
            activities.append(
                {
                    "agent": "orchestrator",
                    "label": "Orquestador",
                    "color": "#6366f1",
                    "phase": "sintesis",
                    "summary": "Sintetizo la respuesta.",
                }
            )
            continue

        nested_tool_calls = tool_result.get("tool_calls", [])
        nested_summary = _summarize_nested_tool_call(nested_tool_calls)
        agent_name = tool_result.get("agent", "desconocido")
        activities.append(
            {
                "agent": agent_name,
                "label": _agent_label(agent_name),
                "color": tool_result.get("color", _agent_color(agent_name)),
                "phase": "consulta",
                "summary": _agent_summary(agent_name),
                "detail": nested_summary,
            }
        )

    return activities


def _summarize_nested_tool_call(nested_tool_calls: Any) -> str:
    if not nested_tool_calls or not isinstance(nested_tool_calls, list):
        return ""

    first_call = nested_tool_calls[0]
    if not isinstance(first_call, dict):
        return ""

    tool_name = first_call.get("tool_name", "tool")
    tool_result = first_call.get("tool_result", {})
    if isinstance(tool_result, dict) and "count" in tool_result:
        return f"{tool_result['count']} resultado(s)."
    return str(tool_name)


def _agent_label(agent: Any) -> str:
    mapping = {
        "orchestrator": "Orquestador",
        "litigante": "Litigante",
        "normativo": "Normativo",
    }
    return mapping.get(agent, "Agente")


def _agent_color(agent: Any) -> str:
    mapping = {
        "orchestrator": "#6366f1",
        "litigante": "#3b82f6",
        "normativo": "#f59e0b",
    }
    return mapping.get(agent, "#475569")


def _agent_summary(agent: Any) -> str:
    mapping = {
        "litigante": "Busco jurisprudencia.",
        "normativo": "Busco normativa.",
    }
    return mapping.get(agent, "Ejecuto una tarea.")


if __name__ == "__main__":
    raise SystemExit(main())
