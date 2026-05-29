from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

from jurispeed_challenge.agents import ConversationSession, OrchestratorAgent
from jurispeed_challenge.ai_providers import AIProviderError, ProviderUnavailableError
from jurispeed_challenge.types import AgentRunResult, ToolCallTrace


SESSION_KEY = "jurispeed_session_id"

# Niveles de detalle del runner de pytest expuesto en la GUI.
# El orden refleja un detalle creciente: Simple < Classic < Full.
#   simple  -> --simple : progreso clasico por puntos (verbose desactivado).
#   classic -> (vacio)  : verbose por defecto (addopts="-v"), un test por linea.
#   full    -> --full   : verbose + bloque explicativo por test aprobado.
TEST_DETAIL_FLAGS: dict[str, list[str]] = {
    "simple": ["--simple"],
    "classic": [],
    "full": ["--full"],
}


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

    @app.post("/api/tests/run")
    def run_tests() -> Any:
        payload = request.get_json(silent=True) or {}
        detail = str(payload.get("detail", "classic")).strip().lower()
        if detail not in TEST_DETAIL_FLAGS:
            options = ", ".join(sorted(TEST_DETAIL_FLAGS))
            return (
                jsonify({"error": f"Nivel de detalle invalido. Usa uno de: {options}."}),
                400,
            )

        command = [sys.executable, "-m", "pytest", "--color=no", *TEST_DETAIL_FLAGS[detail]]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=str(_project_root()),
                capture_output=True,
                text=True,
                timeout=180,
            )
        except FileNotFoundError:
            return jsonify({"error": "No se encontro pytest en el entorno actual."}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"error": "La ejecucion de pytest supero el limite de 180s."}), 504

        duration = round(time.perf_counter() - started, 2)
        output = completed.stdout
        if completed.stderr:
            output = f"{output}\n{completed.stderr}" if output else completed.stderr

        return jsonify(
            {
                "detail": detail,
                "command": " ".join(["pytest", "--color=no", *TEST_DETAIL_FLAGS[detail]]),
                "returncode": completed.returncode,
                "status": "passed" if completed.returncode == 0 else "failed",
                "duration": duration,
                "summary": _parse_pytest_summary(completed.returncode, completed.stdout),
                "output": output.rstrip() + "\n" if output else "",
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


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[2]


def _parse_pytest_summary(returncode: int, stdout: str) -> dict[str, Any]:
    counts = {
        outcome: _count_outcome(outcome, stdout)
        for outcome in ("passed", "failed", "error", "skipped", "xfailed", "xpassed")
    }
    total = counts["passed"] + counts["failed"] + counts["error"] + counts["skipped"]
    return {
        **counts,
        "total": total,
        "line": _summary_line(stdout),
        "ok": returncode == 0,
    }


def _count_outcome(outcome: str, stdout: str) -> int:
    match = re.search(rf"(\d+) {outcome}\b", stdout)
    return int(match.group(1)) if match else 0


def _summary_line(stdout: str) -> str:
    for raw_line in reversed(stdout.splitlines()):
        line = raw_line.strip()
        if " in " in line and ("passed" in line or "failed" in line or "error" in line):
            return line.strip("= ").strip()
    return ""


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
