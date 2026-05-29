from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AgentRole = Literal["orchestrator", "litigante", "normativo"]
ProviderName = Literal["anthropic", "bedrock"]

Message = dict[str, Any]
ContentBlock = dict[str, Any]
ToolSchema = dict[str, Any]


@dataclass(frozen=True)
class AIProviderConfig:
    role: AgentRole
    provider: ProviderName
    model: str
    max_tokens: int = 1200
    temperature: float = 0.1


@dataclass(frozen=True)
class AIRequest:
    config: AIProviderConfig
    system: str
    messages: list[Message]
    tools: list[ToolSchema] = field(default_factory=list)
    tool_choice: dict[str, Any] | None = None


@dataclass(frozen=True)
class AIResponse:
    content: list[ContentBlock]
    stop_reason: str | None
    model: str


@dataclass(frozen=True)
class ToolCallTrace:
    tool_name: str
    tool_use_id: str
    tool_input: dict[str, Any]
    tool_result: Any
    is_error: bool = False


@dataclass(frozen=True)
class AgentRunResult:
    text: str
    messages: list[Message]
    tool_calls: list[ToolCallTrace]

