"""Interactive terminal chat for the local shopping assistant."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence

from src.core.agent import ChatTurn, ShoppingAgent
from src.core.contract import AgentEvent, ConversationState

EXIT_COMMANDS = {"/exit", "/quit"}
MAX_HISTORY_TURNS = 8


async def chat() -> None:
    configure_logging()
    agent = ShoppingAgent()
    state = agent.initial_state()
    history: list[ChatTurn] = []

    print("دستیار خرید حضوری ترب — برای خروج /exit را بنویسید.")
    while True:
        try:
            user_text = input("\nشما: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if user_text in EXIT_COMMANDS:
            return
        if not user_text:
            continue

        try:
            response = await agent.run(
                user_text,
                user_id="cli-user",
                conversation=state,
                history=history,
                on_event=_print_progress,
            )
        except Exception as error:
            print(f"\nخطا: {error}")
            continue

        print(f"\nدستیار: {response.text}")
        if response.cards:
            print("\nکارت‌ها:")
            for card in response.cards:
                _print_card(card.model_dump(mode="json", by_alias=True))
        history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": response.text},
            ]
        )
        _trim_history(history)


def _print_progress(event: AgentEvent) -> None:
    if event.type == "tool_start":
        print(f"\n[در حال جستجو: {event.name}]", end="", flush=True)
    elif event.type == "tool_end":
        status = "✓" if event.ok else "خطا"
        duration = f" {event.duration_ms}ms" if event.duration_ms else ""
        print(f" {status}{duration}", end="", flush=True)


def _print_card(card: dict) -> None:
    print(json.dumps(card, ensure_ascii=False, indent=2))


def _trim_history(history: list[ChatTurn]) -> None:
    max_messages = MAX_HISTORY_TURNS * 2
    if len(history) > max_messages:
        del history[:-max_messages]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(chat())


if __name__ == "__main__":
    main()
