from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from jurispeed_challenge.tool_loop import ToolUseLoop
from jurispeed_challenge.tools import ToolDefinition, ToolRegistry
from jurispeed_challenge.types import AIProviderConfig, AIRequest, AIResponse


@dataclass
class MockProvider:
    calls: int = 0
    observed_messages: list[list[dict[str, object]]] | None = None

    def create_message(self, request: AIRequest) -> AIResponse:
        if self.observed_messages is None:
            self.observed_messages = []
        self.observed_messages.append(deepcopy(request.messages))
        self.calls += 1
        if self.calls == 1:
            return AIResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "toolu_test_1",
                        "name": "search_jurisprudencia",
                        "input": {"query": "arrendatario sin pagar renta", "top_k": 1},
                    }
                ],
                stop_reason="tool_use",
                model="mock-model",
            )
        return AIResponse(
            content=[
                {
                    "type": "text",
                    "text": "Se encontro ROL-1234-2024 y la respuesta final fue sintetizada.",
                }
            ],
            stop_reason="end_turn",
            model="mock-model",
        )


def test_tool_loop_returns_final_answer(test_report) -> None:
    provider = MockProvider()
    tools = ToolRegistry(
        [
            ToolDefinition(
                name="search_jurisprudencia",
                description="Search jurisprudencia",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer"},
                    },
                    "required": ["query"],
                },
                handler=lambda params: {
                    "count": 1,
                    "results": [{"id": "ROL-1234-2024"}],
                    "query": params["query"],
                },
            )
        ]
    )
    loop = ToolUseLoop(provider=provider, tools=tools)

    result = loop.run(
        AIRequest(
            config=AIProviderConfig(
                role="litigante",
                provider="anthropic",
                model="mock-model",
            ),
            system="test",
            messages=[{"role": "user", "content": "consulta"}],
            tools=tools.schemas(),
        )
    )

    assert provider.calls == 2
    assert "ROL-1234-2024" in result.text
    assert result.tool_calls[0].tool_name == "search_jurisprudencia"
    assert result.tool_calls[0].tool_result["count"] == 1

    second_call_messages = provider.observed_messages[1]

    test_report.set_checked(
        "El loop manual de tool_use ejecuta la tool, devuelve tool_result y obtiene texto final."
    )
    test_report.set_setup(
        "Provider mock con dos respuestas: primero tool_use(search_jurisprudencia), luego texto final."
    )
    test_report.set_observed(
        "provider.calls=2, tool_result.count=1 y el texto final contiene ROL-1234-2024."
    )
    test_report.add_step(
        "El primer response del assistant pide search_jurisprudencia con top_k=1."
    )
    test_report.add_step(
        "El loop ejecuta la handler local y manda un bloque tool_result como siguiente mensaje de user."
    )
    test_report.add_step(
        "El segundo response del provider cierra el flujo con una respuesta sintetizada."
    )

    assert second_call_messages[-1]["role"] == "user"
    assert second_call_messages[-1]["content"][0]["type"] == "tool_result"
    assert second_call_messages[-1]["content"][0]["tool_use_id"] == "toolu_test_1"
