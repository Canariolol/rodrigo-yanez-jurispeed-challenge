from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jurispeed_challenge.ai_providers import ProviderResolver
from jurispeed_challenge.prompts import (
    LITIGANTE_SYSTEM_PROMPT,
    NORMATIVO_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
)
from jurispeed_challenge.search import search_jurisprudencia, search_normativa
from jurispeed_challenge.tool_loop import ToolUseLoop
from jurispeed_challenge.tools import ToolDefinition, ToolRegistry
from jurispeed_challenge.types import AIRequest, AgentRunResult, Message


SPECIALIST_CONTEXT_MESSAGE_LIMIT = 4


@dataclass
class ConversationSession:
    history: list[Message] = field(default_factory=list)

    def add_turn(self, user_text: str, assistant_text: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})

    def build_messages(self, user_text: str) -> list[Message]:
        return [*self.history, {"role": "user", "content": user_text}]


class LitiganteAgent:
    def __init__(self, resolver: ProviderResolver) -> None:
        self.resolver = resolver

    def run(
        self,
        query: str,
        conversation_history: list[Message] | None = None,
    ) -> AgentRunResult:
        config = self.resolver.get_config("litigante")
        provider = self.resolver.get_provider("litigante")
        tools = ToolRegistry(
            [
                ToolDefinition(
                    name="search_jurisprudencia",
                    description=(
                        "Busca jurisprudencia chilena en mock_data.json. "
                        "Usa esta herramienta para preguntas sobre arrendamiento, pago de rentas, "
                        "lanzamiento, notificaciones judiciales, prescripcion, tribunales o litigios. "
                        "Devuelve solo registros existentes en el mock; si no hay coincidencias, count sera 0."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "top_k": {"type": "integer", "minimum": 1, "maximum": 5},
                        },
                        "required": ["query"],
                    },
                    handler=lambda params: search_jurisprudencia(
                        query=str(params.get("query", query)),
                        top_k=int(params.get("top_k", 3)),
                    ),
                )
            ]
        )
        loop = ToolUseLoop(provider=provider, tools=tools, max_tool_rounds=3)
        return loop.run(
            AIRequest(
                config=config,
                system=LITIGANTE_SYSTEM_PROMPT,
                messages=_build_specialist_messages(query, conversation_history),
                tools=tools.schemas(),
                tool_choice={"type": "tool", "name": "search_jurisprudencia"},
            )
        )


class NormativoAgent:
    def __init__(self, resolver: ProviderResolver) -> None:
        self.resolver = resolver

    def run(
        self,
        query: str,
        conversation_history: list[Message] | None = None,
    ) -> AgentRunResult:
        config = self.resolver.get_config("normativo")
        provider = self.resolver.get_provider("normativo")
        tools = ToolRegistry(
            [
                ToolDefinition(
                    name="search_normativa",
                    description=(
                        "Busca normativa tributaria y legal en mock_data.json. "
                        "Usa esta herramienta para impuestos, rentas no percibidas, LIR, circulares SII, "
                        "gastos deducibles o reglas normativas. Devuelve solo registros existentes en el mock."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    handler=lambda params: search_normativa(query=str(params.get("query", query))),
                )
            ]
        )
        loop = ToolUseLoop(provider=provider, tools=tools, max_tool_rounds=3)
        return loop.run(
            AIRequest(
                config=config,
                system=NORMATIVO_SYSTEM_PROMPT,
                messages=_build_specialist_messages(query, conversation_history),
                tools=tools.schemas(),
                tool_choice={"type": "tool", "name": "search_normativa"},
            )
        )


class OrchestratorAgent:
    def __init__(self, resolver: ProviderResolver | None = None) -> None:
        self.resolver = resolver or ProviderResolver()
        self.litigante = LitiganteAgent(self.resolver)
        self.normativo = NormativoAgent(self.resolver)

    def run(self, user_text: str, session: ConversationSession) -> AgentRunResult:
        config = self.resolver.get_config("orchestrator")
        provider = self.resolver.get_provider("orchestrator")
        tools = ToolRegistry(
            [
                ToolDefinition(
                    name="route_to_litigante",
                    description=(
                        "Envia la consulta al agente Litigante para buscar jurisprudencia chilena "
                        "en mock_data.json. Debes usarla para arrendamientos, acciones legales, "
                        "lanzamiento, notificaciones, contratos, arbitraje, tribunales o litigios."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    handler=lambda params: self._route_to_litigante(
                        params,
                        user_text,
                        session.history,
                    ),
                ),
                ToolDefinition(
                    name="route_to_normativo",
                    description=(
                        "Envia la consulta al agente Normativo para buscar normas tributarias o legales "
                        "en mock_data.json. Debes usarla para rentas no percibidas, impuestos, LIR, "
                        "SII, gastos deducibles o interpretacion normativa."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    handler=lambda params: self._route_to_normativo(
                        params,
                        user_text,
                        session.history,
                    ),
                ),
                ToolDefinition(
                    name="synthesize",
                    description=(
                        "Consolida resultados ya obtenidos de los agentes antes de redactar la respuesta final. "
                        "Usala despues de route_to_litigante y/o route_to_normativo cuando tengas evidencia."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "results": {
                                "type": "array",
                                "items": {"type": "object"},
                            }
                        },
                        "required": ["results"],
                    },
                    handler=self._synthesize,
                ),
            ]
        )
        loop = ToolUseLoop(provider=provider, tools=tools, max_tool_rounds=5)
        result = loop.run(
            AIRequest(
                config=config,
                system=ORCHESTRATOR_SYSTEM_PROMPT,
                messages=session.build_messages(user_text),
                tools=tools.schemas(),
                tool_choice={"type": "auto"},
            )
        )
        session.add_turn(user_text, result.text)
        return result

    def _route_to_litigante(
        self,
        params: dict[str, Any],
        fallback_query: str,
        conversation_history: list[Message],
    ) -> dict[str, Any]:
        query = str(params.get("query") or fallback_query)
        result = self.litigante.run(
            query,
            conversation_history=conversation_history,
        )
        return {
            "agent": "litigante",
            "color": "#3b82f6",
            "query": query,
            "answer": result.text,
            "tool_calls": [_trace_to_dict(trace) for trace in result.tool_calls],
        }

    def _route_to_normativo(
        self,
        params: dict[str, Any],
        fallback_query: str,
        conversation_history: list[Message],
    ) -> dict[str, Any]:
        query = str(params.get("query") or fallback_query)
        result = self.normativo.run(
            query,
            conversation_history=conversation_history,
        )
        return {
            "agent": "normativo",
            "color": "#f59e0b",
            "query": query,
            "answer": result.text,
            "tool_calls": [_trace_to_dict(trace) for trace in result.tool_calls],
        }

    def _synthesize(self, params: dict[str, Any]) -> dict[str, Any]:
        results = params.get("results", [])
        return {
            "agent": "orchestrator",
            "color": "#6366f1",
            "results": results,
            "instruction": (
                "Redacta la respuesta final usando solo estas evidencias. "
                "Si algun resultado tiene count=0, menciona la falta de evidencia sin inventar fuentes."
            ),
        }


def _trace_to_dict(trace: object) -> dict[str, Any]:
    return {
        "tool_name": getattr(trace, "tool_name"),
        "tool_use_id": getattr(trace, "tool_use_id"),
        "tool_input": getattr(trace, "tool_input"),
        "tool_result": getattr(trace, "tool_result"),
        "is_error": getattr(trace, "is_error"),
    }


def _build_specialist_messages(
    query: str,
    conversation_history: list[Message] | None,
) -> list[Message]:
    if not conversation_history:
        return [{"role": "user", "content": query}]

    recent_history = conversation_history[-SPECIALIST_CONTEXT_MESSAGE_LIMIT:]
    history_lines = []
    for message in recent_history:
        role = str(message.get("role", "user"))
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        label = "Usuario" if role == "user" else "Asistente"
        history_lines.append(f"{label}: {content}")

    if not history_lines:
        return [{"role": "user", "content": query}]

    history_text = "\n".join(history_lines)
    enriched_query = (
        "Contexto conversacional reciente:\n"
        f"{history_text}\n\n"
        "Consulta actual a resolver:\n"
        f"{query}\n\n"
        "Usa el contexto solo para interpretar referencias del seguimiento, "
        "pero busca evidencia en mock_data.json segun la consulta actual."
    )
    return [{"role": "user", "content": enriched_query}]
