from __future__ import annotations

import os
import random
import time
from dataclasses import replace
from typing import Protocol

from dotenv import load_dotenv

from jurispeed_challenge.types import AIProviderConfig, AIRequest, AIResponse, AgentRole, ContentBlock


DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

DEFAULT_PROVIDER_REGISTRY: dict[AgentRole, AIProviderConfig] = {
    "orchestrator": AIProviderConfig(
        role="orchestrator",
        provider="anthropic",
        model=DEFAULT_MODEL,
        max_tokens=1600,
        temperature=0.1,
    ),
    "litigante": AIProviderConfig(
        role="litigante",
        provider="anthropic",
        model=DEFAULT_MODEL,
        max_tokens=1000,
        temperature=0.0,
    ),
    "normativo": AIProviderConfig(
        role="normativo",
        provider="anthropic",
        model=DEFAULT_MODEL,
        max_tokens=900,
        temperature=0.0,
    ),
}


class AIProviderError(RuntimeError):
    """Se lanza cuando un proveedor de IA no puede completar una solicitud."""


class ProviderUnavailableError(AIProviderError):
    """Se lanza cuando el proveedor configurado no existe o no esta disponible."""


class AIProvider(Protocol):
    def create_message(self, request: AIRequest) -> AIResponse:
        """Envia una solicitud de mensaje al modelo configurado."""


def load_provider_registry(load_env_file: bool = True) -> dict[AgentRole, AIProviderConfig]:
    if load_env_file:
        load_dotenv()
    global_provider = _read_env("GLOBAL_AI_PROVIDER")
    global_model = _read_env("GLOBAL_AI_MODEL")
    registry: dict[AgentRole, AIProviderConfig] = {}

    for role, default_config in DEFAULT_PROVIDER_REGISTRY.items():
        env_prefix = f"JURISPEED_{role.upper()}"
        config = default_config
        provider = _read_env(f"{env_prefix}_PROVIDER") or global_provider or config.provider
        model = _read_env(f"{env_prefix}_MODEL") or global_model or config.model
        max_tokens = _read_int(f"{env_prefix}_MAX_TOKENS", config.max_tokens)
        temperature = _read_float(f"{env_prefix}_TEMPERATURE", config.temperature)
        registry[role] = replace(
            config,
            provider=provider,  # type: ignore[arg-type]
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    return registry


def build_provider(config: AIProviderConfig) -> AIProvider:
    if config.provider == "anthropic":
        return AnthropicProvider()
    if config.provider == "bedrock":
        return BedrockProvider()
    raise ProviderUnavailableError(f"Proveedor de IA no soportado: {config.provider}")


class ProviderResolver:
    def __init__(self, registry: dict[AgentRole, AIProviderConfig] | None = None) -> None:
        self.registry = registry or load_provider_registry()
        self._providers: dict[str, AIProvider] = {}

    def get_config(self, role: AgentRole) -> AIProviderConfig:
        return self.registry[role]

    def get_provider(self, role: AgentRole) -> AIProvider:
        config = self.get_config(role)
        cache_key = config.provider
        if cache_key not in self._providers:
            self._providers[cache_key] = build_provider(config)
        return self._providers[cache_key]


class AnthropicProvider:
    def __init__(self) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ProviderUnavailableError(
                "El paquete anthropic no esta instalado. Ejecuta `pip install -e .`."
            ) from exc

        self._client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def create_message(self, request: AIRequest) -> AIResponse:
        return _create_message_with_retry(
            client=self._client,
            request=request,
            provider_label="Anthropic",
        )


class BedrockProvider:
    def __init__(self) -> None:
        try:
            from anthropic import AnthropicBedrock
        except ImportError as exc:
            raise ProviderUnavailableError(
                "El paquete anthropic instalado no expone AnthropicBedrock. "
                "Actualizalo con `pip install -U anthropic`."
            ) from exc

        kwargs = {
            "aws_region": (
                os.getenv("AWS_BEDROCK_REGION")
                or os.getenv("AWS_REGION")
                or os.getenv("AWS_DEFAULT_REGION")
            ),
            "aws_profile": os.getenv("AWS_PROFILE"),
            "aws_access_key": os.getenv("AWS_ACCESS_KEY_ID"),
            "aws_secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "aws_session_token": os.getenv("AWS_SESSION_TOKEN"),
        }
        self._client = AnthropicBedrock(
            **{key: value for key, value in kwargs.items() if value}
        )

    def create_message(self, request: AIRequest) -> AIResponse:
        return _create_message_with_retry(
            client=self._client,
            request=request,
            provider_label="Bedrock",
        )


def _create_message_with_retry(
    client: object,
    request: AIRequest,
    provider_label: str,
) -> AIResponse:
    payload = {
        "model": request.config.model,
        "max_tokens": request.config.max_tokens,
        "temperature": request.config.temperature,
        "system": request.system,
        "messages": request.messages,
    }
    if request.tools:
        payload["tools"] = request.tools
    if request.tool_choice is not None:
        payload["tool_choice"] = request.tool_choice

    for attempt in range(3):
        try:
            response = client.messages.create(**payload)  # type: ignore[attr-defined]
            return AIResponse(
                content=[_content_block_to_dict(block) for block in response.content],
                stop_reason=getattr(response, "stop_reason", None),
                model=getattr(response, "model", request.config.model),
            )
        except Exception as exc:  # SDK versions expose several transient exception classes.
            if attempt < 2 and _is_transient_provider_error(exc):
                delay_seconds = (2**attempt) + random.uniform(0, 0.25)
                time.sleep(delay_seconds)
                continue
            raise AIProviderError(
                f"La solicitud a {provider_label} fallo: {exc}"
            ) from exc

    raise AIProviderError(
        f"La solicitud a {provider_label} fallo despues de reintentos."
    )


def _content_block_to_dict(block: object) -> ContentBlock:
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)  # type: ignore[no-any-return]
    if hasattr(block, "dict"):
        return block.dict(exclude_none=True)  # type: ignore[no-any-return]
    raise AIProviderError(
        f"El proveedor devolvio un bloque de contenido no soportado: {block!r}"
    )


def _read_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _is_transient_provider_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and (status_code == 429 or status_code >= 500):
        return True

    transient_names = {
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "ServiceUnavailableError",
        "ThrottlingException",
    }
    return exc.__class__.__name__ in transient_names


def _read_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        raise AIProviderError(
            f"Valor entero invalido para {name}: {raw_value!r}"
        ) from None


def _read_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        raise AIProviderError(
            f"Valor float invalido para {name}: {raw_value!r}"
        ) from None
