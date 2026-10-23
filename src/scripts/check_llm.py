"""Verify model discovery, a normal answer, and a real function tool call."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from openai import OpenAI

from src.core.config import settings
from src.core.llm import OpenAICompatibleChatModel


@tool
def ping(value: int) -> int:
    """Return the received integer to validate function calling."""
    return value


def main() -> None:
    settings.validate_llm()
    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.timeout_seconds,
    )
    available_models = sorted(model.id for model in client.models.list().data)
    print("مدل‌های قابل دسترس: " + ", ".join(available_models))
    print(f"مدل تنظیم‌شده: {'موجود' if settings.llm_model in available_models else 'پیدا نشد'}")

    model = OpenAICompatibleChatModel(
        model_name=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.timeout_seconds,
        reasoning_effort=settings.llm_reasoning_effort,
        max_completion_tokens=100,
    )
    answer = model.invoke([HumanMessage(content="فقط بگو: اتصال برقرار است.")])
    print(f"پاسخ ساده: {answer.content}")

    tool_response = model.bind_tools([ping]).invoke(
        [HumanMessage(content="با ابزار ping یک بار مقدار 7 را بررسی کن.")]
    )
    calls = [(call["name"], call["args"]) for call in tool_response.tool_calls]
    print(f"tool call: {json.dumps(calls, ensure_ascii=False)}")
    if not calls or calls[0] != ("ping", {"value": 7}):
        raise SystemExit("مدل tool call مورد انتظار را برنگرداند.")


if __name__ == "__main__":
    main()
