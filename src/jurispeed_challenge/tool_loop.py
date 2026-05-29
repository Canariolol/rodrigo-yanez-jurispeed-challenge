from __future__ import annotations

from jurispeed_challenge.ai_providers import AIProvider
from jurispeed_challenge.tools import ToolRegistry, tool_result_to_text
from jurispeed_challenge.types import AIRequest, AgentRunResult, Message, ToolCallTrace


class ToolUseLoop:
    def __init__(
        self,
        provider: AIProvider,
        tools: ToolRegistry,
        max_tool_rounds: int = 5,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.max_tool_rounds = max_tool_rounds

    def run(self, request: AIRequest) -> AgentRunResult:
        messages: list[Message] = [dict(message) for message in request.messages]
        tool_calls: list[ToolCallTrace] = []

        for round_index in range(self.max_tool_rounds + 1):
            tool_choice = request.tool_choice if round_index == 0 else {"type": "auto"}
            response = self.provider.create_message(
                AIRequest(
                    config=request.config,
                    system=request.system,
                    messages=messages,
                    tools=request.tools,
                    tool_choice=tool_choice,
                )
            )
            messages.append({"role": "assistant", "content": response.content})

            tool_use_blocks = [
                block for block in response.content if block.get("type") == "tool_use"
            ]
            if not tool_use_blocks:
                return AgentRunResult(
                    text=_extract_text(response.content),
                    messages=messages,
                    tool_calls=tool_calls,
                )

            tool_result_blocks = []
            for block in tool_use_blocks:
                tool_name = str(block.get("name"))
                tool_use_id = str(block.get("id"))
                tool_input = block.get("input") or {}
                if not isinstance(tool_input, dict):
                    tool_input = {}

                try:
                    result = self.tools.execute(tool_name, tool_input)
                    is_error = False
                    content = tool_result_to_text(result)
                except Exception as exc:
                    result = {"error": str(exc)}
                    is_error = True
                    content = tool_result_to_text(result)

                tool_calls.append(
                    ToolCallTrace(
                        tool_name=tool_name,
                        tool_use_id=tool_use_id,
                        tool_input=tool_input,
                        tool_result=result,
                        is_error=is_error,
                    )
                )
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                }
                if is_error:
                    result_block["is_error"] = True
                tool_result_blocks.append(result_block)

            messages.append({"role": "user", "content": tool_result_blocks})

        raise RuntimeError(
            f"Tool loop exceeded {self.max_tool_rounds} tool rounds. "
            "Check whether the model is repeatedly calling tools without producing a final answer."
        )


def _extract_text(content_blocks: list[dict[str, object]]) -> str:
    text_parts = [
        str(block.get("text", ""))
        for block in content_blocks
        if block.get("type") == "text" and block.get("text")
    ]
    return "\n".join(text_parts).strip()
