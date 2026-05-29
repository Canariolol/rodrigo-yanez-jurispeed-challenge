from __future__ import annotations

import argparse
import sys

from jurispeed_challenge.agents import ConversationSession, OrchestratorAgent
from jurispeed_challenge.ai_providers import AIProviderError, ProviderUnavailableError


DEMO_TURNS = [
    """Tengo un contrato de arriendo con el arrendatario Juan Perez.
Lleva 4 meses sin pagar la renta. Que acciones legales puedo tomar
y cuales son las implicancias tributarias de las rentas no percibidas?""",
    "Y si el contrato tiene clausula de arbitraje, cambia algo?",
    """Hay sentencias de la Corte Suprema sobre nulidad de finiquito por error en el calculo
proporcional de vacaciones?""",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CLI del challenge multi-agente de Jurispeed.ai"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Ejecuta la demo obligatoria de 3 turns.",
    )
    args = parser.parse_args(argv)

    session = ConversationSession()
    orchestrator = OrchestratorAgent()

    try:
        if args.demo:
            _run_demo(orchestrator, session)
        else:
            _run_interactive(orchestrator, session)
    except (AIProviderError, ProviderUnavailableError) as exc:
        print(f"\nError del proveedor de IA: {exc}", file=sys.stderr)
        print(
            "Revisa ANTHROPIC_API_KEY, los fondos de la cuenta, las variables del proveedor "
            "o ejecuta los tests unitarios para validar el loop de tools sin un LLM en vivo.",
            file=sys.stderr,
        )
        return 1
    return 0


def _run_demo(orchestrator: OrchestratorAgent, session: ConversationSession) -> None:
    for index, user_text in enumerate(DEMO_TURNS, start=1):
        print(f"\n=== Turn {index} - Usuario ===")
        print(user_text)
        result = orchestrator.run(user_text, session)
        print(f"\n=== Turn {index} - Orquestador ===")
        print(result.text)
        if result.tool_calls:
            called_tools = ", ".join(trace.tool_name for trace in result.tool_calls)
            print(f"\nHerramientas usadas: {called_tools}")


def _run_interactive(orchestrator: OrchestratorAgent, session: ConversationSession) -> None:
    print("Jurispeed.ai challenge CLI. Escribe 'salir' para terminar.")
    while True:
        try:
            user_text = input("\nTu pregunta > ").strip()
        except EOFError:
            print()
            return
        if not user_text:
            continue
        if user_text.lower() in {"salir", "exit", "quit"}:
            return
        result = orchestrator.run(user_text, session)
        print("\nOrquestador:")
        print(result.text)


if __name__ == "__main__":
    raise SystemExit(main())
