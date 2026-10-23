"""Parse model text and build UI cards exclusively from tool results."""

from __future__ import annotations

import ast
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from src.core.contract import (
    AlternativesCard,
    AssistantCard,
    AssistantResponse,
    CompareCard,
    HubCard,
    InquiryBatchCard,
    InquiryCard,
    MallGuideCard,
    MessageDraftCard,
    ProductCards,
    QuickLookCard,
    ShopCards,
    WebCards,
)

logger = logging.getLogger("purchase_torob.response")

CARD_MODELS = {
    "search_products": ProductCards,
    "get_offers": ShopCards,
    "compare_shops": CompareCard,
    "draft_inquiry": MessageDraftCard,
    "send_inquiry": InquiryCard,
    "send_inquiry_batch": InquiryBatchCard,
    "get_inquiry_status": InquiryCard,
    "cancel_inquiry": InquiryCard,
    "follow_up_inquiry": InquiryCard,
    "inquire_shop": InquiryCard,
    "find_alternatives": AlternativesCard,
    "suggest_market_hub": HubCard,
    "product_quick_look": QuickLookCard,
    "get_shop_location_hint": MallGuideCard,
    "web_search": WebCards,
}


def response_from_messages(messages: list[AnyMessage]) -> AssistantResponse:
    final_message = next(
        (
            message for message in reversed(messages)
            if isinstance(message, AIMessage) and not message.tool_calls
        ),
        None,
    )
    if final_message is None:
        raise RuntimeError("مدل پاسخ نهایی تولید نکرد.")

    text, question = parse_model_text(message_text(final_message))
    if question:
        text = f"{text}\n\n{question}"
    search_args = next((call.get("args", {})
                        for message in reversed(messages) if isinstance(message, AIMessage)
                        for call in reversed(message.tool_calls) if call.get("name") == "search_products"), None)
    search_filters = search_args.get("filters") if search_args else None
    if not isinstance(search_filters, dict):
        search_filters = {}
    return AssistantResponse(
        text=text,
        cards=cards_from_tool_messages(messages),
        clarification_question=question,
        search_query=str(search_args.get("query", "")) if search_args is not None else None,
        search_category=(search_args.get("category") or search_filters.get("category")) if search_args else None,
        search_min_price=search_filters.get("min_price"),
    )


def parse_model_text(raw: str) -> tuple[str, str | None]:
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    try:
        payload = json.loads(cleaned.strip())
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            raise ValueError("پاسخ مدل فاقد فیلد text معتبر است")
        question = payload.get("clarificationQuestion", payload.get("clarification_question"))
        return payload["text"], question if isinstance(question, str) else None
    except (ValueError, json.JSONDecodeError):
        return raw or "در پردازش پاسخ مشکلی پیش آمد؛ دوباره تلاش کنید.", None


def message_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(
        part.get("text", "")
        for part in message.content
        if isinstance(part, dict) and part.get("type") == "text"
    )


def cards_from_tool_messages(messages: list[AnyMessage]) -> list[AssistantCard]:
    calls_by_id = {
        call.get("id"): call.get("name")
        for message in messages if isinstance(message, AIMessage)
        for call in message.tool_calls
    }
    cards = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        name = calls_by_id.get(message.tool_call_id)
        card_model = CARD_MODELS.get(name)
        payload = parse_tool_payload(message.content)
        if card_model is None or not payload or "error" in payload:
            continue

        card_data = card_data_for_tool(name, payload.get("data"), payload.get("source"))
        if card_data is None:
            continue
        try:
            cards.append(card_model.model_validate(card_data))
        except Exception:
            logger.exception("Tool output does not match card contract: %s", name)
    return cards


def parse_tool_payload(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(content)
        except (SyntaxError, ValueError):
            return None
    return value if isinstance(value, dict) else None


def card_data_for_tool(name: str, data: Any, source: str) -> dict[str, Any] | None:
    if name == "search_products":
        return {"kind": "product_cards", "products": data[:20] if isinstance(data, list) else [], "source": source}
    if name == "get_offers":
        return {"kind": "shop_cards", "results": _advisory_results(data), "source": source}
    if name == "compare_shops":
        return {"kind": "compare", "results": _advisory_results(data), "source": source}
    if name == "draft_inquiry":
        return data
    if name in {"send_inquiry", "get_inquiry_status", "cancel_inquiry", "follow_up_inquiry"}:
        return data
    if name == "send_inquiry_batch":
        return data
    if name == "inquire_shop":
        if isinstance(data, dict) and "kind" in data:
            return data
        return {"kind": "inquiry", "inquiry": data, "source": "simulated"}
    if name == "find_alternatives":
        return {
            "kind": "alternatives",
            "options": _alternative_options(data),
            "source": source,
        }
    if name == "suggest_market_hub":
        return {"kind": "hub", "hubs": _limit(data), "source": "ai_knowledge"}
    if name == "product_quick_look":
        return data
    if name == "get_shop_location_hint":
        return {
            "kind": "mall_guide",
            "shop": data.get("shop"),
            "directions": data.get("directions", []),
            "offer": data.get("offer"),
            "inquiry": data.get("inquiry"),
            "backup": data.get("backup"),
            "source": "dataset",
        }
    if name == "web_search":
        return {"kind": "web_results", "results": _limit(data), "source": "web"}
    return None


def _limit(items: Any) -> list[Any]:
    """Keep every user-facing option list short without changing tool output."""
    return items[:3] if isinstance(items, list) else []


def _advisory_results(items: Any) -> list[dict[str, Any]]:
    """Give each displayed offer one concise, data-based reason."""
    results = _limit(items)
    if not results:
        return []

    prices = [item.get("offer", {}).get("price") for item in results]
    distances = [item.get("distanceKm") for item in results]
    valid_prices = [price for price in prices if isinstance(price, (int, float))]
    valid_distances = [distance for distance in distances if isinstance(distance, (int, float))]
    lowest_price = min(valid_prices) if valid_prices else None
    shortest_distance = min(valid_distances) if valid_distances else None

    summarized = []
    for item in results:
        result = dict(item)
        price = result.get("offer", {}).get("price")
        distance = result.get("distanceKm")
        open_now = result.get("openNow", {}).get("value")
        if open_now is False:
            reason = "فروشگاه الان بسته است؛ پیش از مراجعه ساعت کاری را دوباره بررسی کن."
        elif price is not None and price == lowest_price and distance == shortest_distance:
            reason = "هم کم‌قیمت‌ترین گزینه‌ی ثبت‌شده است و هم نزدیک‌ترین گزینه‌ی این فهرست."
        elif price is not None and price == lowest_price:
            reason = f"کمترین قیمت ثبت‌شده را دارد؛ فاصله‌ی مستقیمش {distance} کیلومتر است."
        elif distance == shortest_distance:
            reason = (
                f"نزدیک‌ترین گزینه است؛ قیمت ثبت‌شده‌اش {price} تومان است."
                if price is not None else "نزدیک‌ترین گزینه است؛ قیمت ثبت نشده."
            )
        elif price is None:
            reason = f"آفر ثبت‌شده دارد؛ قیمت مشخص نیست و {distance} کیلومتر فاصله دارد."
        else:
            reason = f"آفر ثبت‌شده دارد و {distance} کیلومتر با لوکیشن شما فاصله دارد."
        result["reasons"] = [reason]
        summarized.append(result)
    return summarized


def _alternative_options(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    products = {
        product.get("id"): product
        for product in data.get("products", [])
        if isinstance(product, dict) and product.get("id")
    }
    offers_by_product: dict[str, list[dict[str, Any]]] = {}
    for result in data.get("results", []):
        if not isinstance(result, dict):
            continue
        product_id = result.get("offer", {}).get("productId")
        if product_id:
            offers_by_product.setdefault(product_id, []).append(result)

    options = []
    for product_id, results in offers_by_product.items():
        product = products.get(product_id)
        if product is None:
            continue
        options.append({
            "product": product,
            "results": _advisory_results(results[:3]),
        })
        if len(options) == 3:
            break
    return options
