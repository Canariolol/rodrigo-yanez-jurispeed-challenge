from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from jurispeed_challenge.agents import LitiganteAgent
from jurispeed_challenge.types import AIProviderConfig, AIRequest, AIResponse


@dataclass
class SpecialistMockProvider:
    calls: int = 0
    observed_messages: list[list[dict[str, object]]] = field(default_factory=list)

    def create_message(self, request: AIRequest) -> AIResponse:
        self.observed_messages.append(deepcopy(request.messages))
        self.calls += 1
        if self.calls == 1:
            return AIResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "toolu_litigante_context",
                        "name": "search_jurisprudencia",
                        "input": {"query": "clausula de arbitraje en contrato de arriendo"},
                    }
                ],
                stop_reason="tool_use",
                model="mock-model",
            )
        return AIResponse(
            content=[{"type": "text", "text": "Respuesta litigante."}],
            stop_reason="end_turn",
            model="mock-model",
        )


class FakeResolver:
    def __init__(self, provider: SpecialistMockProvider) -> None:
        self.provider = provider

    def get_config(self, role: str) -> AIProviderConfig:
        return AIProviderConfig(
            role=role,  # type: ignore[arg-type]
            provider="anthropic",
            model="mock-model",
        )

    def get_provider(self, role: str) -> SpecialistMockProvider:
        return self.provider


def test_litigante_agent_includes_recent_conversation_context_in_follow_up() -> None:
    provider = SpecialistMockProvider()
    agent = LitiganteAgent(FakeResolver(provider))  # type: ignore[arg-type]
    conversation_history = [
        {
            "role": "user",
            "content": (
                "Tengo un contrato de arriendo con el arrendatario Juan Perez. "
                "Lleva 4 meses sin pagar la renta."
            ),
        },
        {
            "role": "assistant",
            "content": "Puedes evaluar cobro de rentas, terminacion y lanzamiento.",
        },
    ]

    agent.run(
        "Y si el contrato tiene clausula de arbitraje, cambia algo?",
        conversation_history=conversation_history,
    )

    first_request_messages = provider.observed_messages[0]
    assert len(first_request_messages) == 1
    enriched_prompt = str(first_request_messages[0]["content"])
    assert "Contexto conversacional reciente" in enriched_prompt
    assert "Juan Perez" in enriched_prompt
    assert "4 meses sin pagar la renta" in enriched_prompt
    assert "Consulta actual a resolver" in enriched_prompt
    assert "clausula de arbitraje" in enriched_prompt
