"""LangChain chat-model adapter for the project's OpenAI-compatible endpoint."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import OpenAI
from pydantic import ConfigDict, PrivateAttr


class OpenAICompatibleChatModel(BaseChatModel):
    """Minimal adapter for gateways that implement OpenAI Chat Completions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model_name: str
    api_key: str
    base_url: str
    timeout: float
    reasoning_effort: str = "none"
    max_completion_tokens: int = 1800
    _client: OpenAI = PrivateAttr()

    def model_post_init(self, context: Any) -> None:
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=1,
        )

    @property
    def _llm_type(self) -> str:
        return "openai-compatible-chat-completions"

    def bind_tools(self, tools, **kwargs):
        definitions = [convert_to_openai_tool(item) for item in tools]
        return self.bind(tools=definitions, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        request = {
            "model": self.model_name,
            "messages": [_to_provider_message(message) for message in messages],
            "max_completion_tokens": self.max_completion_tokens,
            "reasoning_effort": self.reasoning_effort,
            **kwargs,
        }
        if stop:
            request["stop"] = stop

        completion = self._client.chat.completions.create(**request)
        choice = completion.choices[0]
        provider_message = choice.message
        tool_calls = [
            {
                "name": item.function.name,
                "args": json.loads(item.function.arguments or "{}"),
                "id": item.id,
                "type": "tool_call",
            }
            for item in (provider_message.tool_calls or [])
        ]
        message = AIMessage(
            content=provider_message.content or "",
            tool_calls=tool_calls,
            response_metadata={"finish_reason": choice.finish_reason},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def _to_provider_message(message: AnyMessage) -> dict[str, Any]:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": _message_content(message.content),
        }
    if isinstance(message, AIMessage):
        result: dict[str, Any] = {"role": "assistant", "content": message.content or None}
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["args"], ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return result
    raise TypeError(f"Unsupported chat message type: {type(message).__name__}")


def _message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)
