"""Market hubs, product guidance, web search, and address geocoding."""

from __future__ import annotations

import re

import httpx
from langchain_core.tools import tool

from src.core.config import settings
from src.core.database import database
from src.core.text import normalize_fa, parse_json
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
            "SELECT title, brand, category, specs FROM products WHERE id = ?", (product_id,)
        ).fetchone()
    if product is None:
        raise ValueError("محصول پیدا نشد")

    raw_specs = parse_json(product["specs"], default=[])
    specs = [
        (str(item["key"]).strip(), str(item["value"]).strip())
        for item in raw_specs
        if isinstance(item, dict) and item.get("key") and item.get("value")
    ] if isinstance(raw_specs, list) else []
    strengths = [f"{key}: {value}" for key, value in specs[:3]]
    if not strengths:
        strengths = ["مشخصات فنی قابل استفاده‌ای برای این مدل ثبت نشده است."]

    category = normalize_fa(product["category"])
    checks = _in_person_checks(category)
    card = {
        "kind": "quick_look",
        "product_id": product_id,
        "label": "خلاصه هوش مصنوعی",
        "strengths": strengths,
        "weaknesses": [
            "دیتاست نظر کاربران و آزمون مستقل ندارد؛ تناسب کالا را فقط با مشخصات ثبت‌شده بسنج.",
            *([f"این مشخصات در دیتاست ثبت نشده: {', '.join(key for key, _ in specs[3:6])}."] if len(specs) > 3 else []),
        ],
        "in_person_checks": checks,
        "source": "ai_knowledge",
    }
    return tool_result("ai_knowledge", card)


def _in_person_checks(category: str) -> list[str]:
    if "گوشی موبایل" in category:
        return ["مدل و IMEI را با جعبه و فاکتور تطبیق بده", "وضعیت فعال‌سازی و ضمانت را پیش از پرداخت بررسی کن"]
    if any(term in category for term in ("لپ تاپ", "لپ‌تاپ", "کامپیوتر", "مانیتور", "نمایشگر")):
        return ["دستگاه را روشن کن و نمایشگر، درگاه‌ها و شماره‌سریال را بررسی کن", "مدل دقیق و شرایط ضمانت را با فاکتور تطبیق بده"]
    if any(term in category for term in ("کفش", "کتونی")):
        return ["هر دو لنگه را با جوراب معمولت امتحان کن", "شرایط تعویض سایز را پیش از پرداخت بپرس"]
    if any(term in category for term in ("ابزار", "دریل", "فرز")):
        return ["عملکرد دستگاه و متعلقات داخل جعبه را بررسی کن", "مدل، شماره‌سریال و ضمانت را با فاکتور تطبیق بده"]
    return ["مدل و متعلقات را با مشخصات آگهی تطبیق بده", "شرایط ضمانت و بازگشت را پیش از پرداخت بپرس"]


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
