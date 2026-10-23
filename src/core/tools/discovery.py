"""Market hubs, product guidance, web search, and address geocoding."""

from __future__ import annotations

import re

import httpx
from langchain_core.tools import tool

from src.core.config import settings
from src.core.database import database
from src.core.text import normalize_fa
from src.core.tools.common import market_hub_from_row, tool_result
from src.core.tools.schemas import HubInput, LocationInput, QuickLookInput, WebSearchInput


@tool(args_schema=HubInput)
def suggest_market_hub(category_or_product: str) -> dict:
    """پیشنهاد بورس کالای مرتبط بر پایه‌ی جدول مراکز بازار."""
    query = normalize_fa(category_or_product)
    with database(readonly=True) as connection:
        rows = connection.execute("SELECT * FROM market_hubs").fetchall()
    hubs = [market_hub_from_row(row) for row in rows]
    matches = [
        hub for hub in hubs
        if query in normalize_fa(hub.category) or normalize_fa(hub.category) in query
    ]
    if not matches:
        category = _guess_hub_category(query)
        if category:
            matches = [hub for hub in hubs if category in normalize_fa(hub.category)]
    return tool_result("ai_knowledge", matches)


def _guess_hub_category(query: str) -> str | None:
    categories = (
        (r"موبایل|گوشی", "موبایل"),
        (r"کفش|کتونی|پوشاک", "کفش"),
        (r"دوربین", "دوربین"),
        (r"کامپیوتر|لپتاپ|پرینتر|چاپگر|ماشین اداری", "کامپیوتر"),
        (r"طلا|جواهر", "طلا"),
        (r"خانه|یخچال|اجاق", "خانگی"),
        (r"مبل|مبلمان", "مبلمان"),
        (r"ابزار|یراق", "ابزار"),
    )
    return next((category for pattern, category in categories if re.search(pattern, query)), None)


@tool(args_schema=QuickLookInput)
def product_quick_look(product_id: str) -> dict:
    """خلاصه‌ی هوش مصنوعی و نکات خرید حضوری، بدون جعل نظر کاربران."""
    with database(readonly=True) as connection:
        product = connection.execute(
            "SELECT title, brand, category FROM products WHERE id = ?", (product_id,)
        ).fetchone()
    if product is None:
        raise ValueError("محصول پیدا نشد")

    card = {
        "kind": "quick_look",
        "product_id": product_id,
        "label": "خلاصه هوش مصنوعی",
        "strengths": [
            f"دسته: {product['category'] or 'نامشخص'}",
            f"برند: {product['brand'] or 'نامشخص'}",
        ],
        "weaknesses": [
            "اطلاعات نظر کاربران در دیتاست وجود ندارد؛ این بخش ارزیابی مستقل کالا نیست."
        ],
        "in_person_checks": [
            "اصالت و تطابق مدل روی جعبه را بررسی کنید",
            "شرایط بازگشت و ضمانت را حضوری بپرسید",
            "قیمت نهایی را پیش از پرداخت تأیید کنید",
        ],
        "source": "ai_knowledge",
    }
    return tool_result("ai_knowledge", card)


@tool(args_schema=WebSearchInput)
def web_search(query: str) -> dict:
    """جستجوی وب برای تکمیل پاسخ، پس از بررسی دیتاست محلی."""
    if not settings.search_api_key:
        return tool_result("web", [], notice="کلید جستجوی وب تنظیم نشده است.")

    response = httpx.post(
        settings.search_endpoint,
        headers={"X-API-KEY": settings.search_api_key},
        json={"q": query, "gl": "ir", "hl": "fa"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "source": "web",
        }
        for item in payload.get("organic", [])[:5]
    ]
    return tool_result("web", results)


@tool(args_schema=LocationInput)
def resolve_location(text: str) -> dict:
    """تبدیل نام محله یا نشانی تهران به مختصات جغرافیایی."""
    response = httpx.get(
        settings.geocoding_url,
        params={"q": f"{text}, Tehran, Iran", "format": "jsonv2", "limit": 1},
        headers={"User-Agent": "purchase-torob-agent/0.2"},
        timeout=8,
    )
    response.raise_for_status()
    results = response.json()
    result = None
    if results:
        first = results[0]
        result = {
            "lat": float(first["lat"]),
            "lng": float(first["lon"]),
            "label": first["display_name"],
        }
    return tool_result("web", result)
