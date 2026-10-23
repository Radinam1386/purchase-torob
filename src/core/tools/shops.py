"""Offer search, store checks, comparison, inquiry, and alternatives."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool

from src.core.config import settings
from src.core.database import database
from src.core.tools.common import product_from_row, shop_result_from_row, tool_result
from src.core.tools.schemas import (
    AlternativesInput,
    CompareShopsInput,
    GetOffersInput,
    InquiryInput,
    ShopInput,
)


@tool(args_schema=GetOffersInput)
def get_offers(
    product_id: str,
    lat: float,
    lng: float,
    radius: float = 4,
    max_price: int | None = None,
    installment: bool = False,
    express: bool = False,
    open_now: bool = False,
) -> dict:
    """پیدا کردن آفرهای محصول در شعاع کاربر؛ موجودی تأییدنشده است."""
    results = _find_offers(
        product_id=product_id,
        lat=lat,
        lng=lng,
        radius=radius,
        max_price=max_price,
        installment=installment,
        express=express,
        open_now=open_now,
    )
    return tool_result("dataset", results)


def _find_offers(
    *, product_id: str, lat: float, lng: float, radius: float,
    max_price: int | None = None, installment: bool = False,
    express: bool = False, open_now: bool = False,
):
    with database(readonly=True) as connection:
        rows = connection.execute(_offer_query(), (product_id,)).fetchall()

    results = [shop_result_from_row(row, lat, lng) for row in rows]
    results = [item for item in results if item.distance_km <= radius]
    if max_price is not None:
        results = [item for item in results if item.offer.price <= max_price]
    if installment:
        results = [item for item in results if item.shop.installment is True]
    if express:
        results = [item for item in results if item.shop.express_delivery is True]
    if open_now:
        results = [item for item in results if item.open_now.value is True]
    return sorted(results, key=lambda item: item.distance_km)[:40]


@tool(args_schema=CompareShopsInput)
def compare_shops(
    shop_ids: list[str],
    product_id: str,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """مقایسه‌ی فروشگاه‌های منتخب بر اساس آفر، فاصله، ساعت و پرداخت."""
    center_lat = lat if lat is not None else settings.default_lat
    center_lng = lng if lng is not None else settings.default_lng
    identifiers = list(dict.fromkeys(shop_ids[:8]))
    if not identifiers:
        return tool_result("dataset", [])

    placeholders = ",".join("?" for _ in identifiers)
    query = _offer_query(
        extra_condition=f"AND s.id IN ({placeholders})",
    )
    with database(readonly=True) as connection:
        rows = connection.execute(query, (product_id, *identifiers)).fetchall()

    results = [shop_result_from_row(row, center_lat, center_lng) for row in rows]
    return tool_result("dataset", results)


@tool(args_schema=ShopInput)
def check_open_now(shop_id: str) -> dict:
    """بررسی ساعت کاری ثبت‌شده‌ی فروشگاه با ساعت تهران."""
    with database(readonly=True) as connection:
        row = connection.execute(
            "SELECT weekly_hours FROM shops WHERE id = ?", (shop_id,)
        ).fetchone()
    if row is None:
        raise ValueError("فروشگاه پیدا نشد")
    from src.core.tools.common import is_open_now

    value = is_open_now(row["weekly_hours"])
    return tool_result(
        "dataset",
        {
            "shop_id": shop_id,
            "open_now": {"value": value, "known": value is not None, "source": "dataset"},
        },
    )


@tool(args_schema=InquiryInput)
def inquire_shop(shop_id: str, product_id: str) -> dict:
    """ثبت استعلام شبیه‌سازی‌شده؛ هیچ تماس یا پیام واقعی ارسال نمی‌شود."""
    inquiry_id = str(uuid.uuid4())
    inquiry = {
        "id": inquiry_id,
        "shop_id": shop_id,
        "product_id": product_id,
        "status": "sent",
        "simulated": True,
    }
    with database() as connection:
        exists = connection.execute(
            "SELECT 1 FROM offers WHERE shop_id = ? AND product_id = ? LIMIT 1",
            (shop_id, product_id),
        ).fetchone()
        if exists is None:
            raise ValueError("برای این فروشگاه و محصول آفر ثبت نشده است")
        connection.execute(
            "INSERT INTO inquiries VALUES (?, ?, ?, ?, ?, ?)",
            (
                inquiry_id, shop_id, product_id, "sent",
                json.dumps(inquiry, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
            ),
        )
    return tool_result("simulated", inquiry)


@tool(args_schema=AlternativesInput)
def find_alternatives(
    product_id: str,
    shop_id: str | None = None,
    max_price: int | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius: float = 4,
) -> dict:
    """پیشنهاد مدل‌های هم‌دسته که آفر واقعی در شعاع کاربر دارند."""
    center_lat = lat if lat is not None else settings.default_lat
    center_lng = lng if lng is not None else settings.default_lng
    with database(readonly=True) as connection:
        selected = connection.execute(
            "SELECT category_norm FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if selected is None:
            return tool_result("dataset", {"products": [], "results": []})
        rows = connection.execute(
            """
            SELECT p.* FROM products AS p
            WHERE p.category_norm = ? AND p.id != ?
            ORDER BY p.title LIMIT 200
            """,
            (selected["category_norm"], product_id),
        ).fetchall()

    products_by_id = {row["id"]: product_from_row(row) for row in rows}
    results = []
    for candidate_id in products_by_id:
        offers = _find_offers(
            product_id=candidate_id,
            lat=center_lat,
            lng=center_lng,
            radius=radius,
            max_price=max_price,
        )
        results.extend(offers[:2])
        if len(results) >= 20:
            break

    matched_ids = {item.offer.product_id for item in results}
    products = [item for key, item in products_by_id.items() if key in matched_ids][:10]
    return tool_result("dataset", {"products": products, "results": results[:20]})


@tool(args_schema=ShopInput)
def get_shop_location_hint(shop_id: str) -> dict:
    """نمایش پاساژ، طبقه، واحد و آدرس ثبت‌شده‌ی فروشگاه."""
    with database(readonly=True) as connection:
        row = connection.execute(
            "SELECT * FROM shops WHERE id = ?", (shop_id,)
        ).fetchone()
    if row is None:
        raise ValueError("فروشگاه پیدا نشد")

    from src.core.tools.common import shop_from_row

    shop = shop_from_row(row)
    directions = [
        f"پاساژ: {shop.mall or 'نامشخص'}",
        f"طبقه: {shop.floor or 'نامشخص'}",
        f"واحد: {shop.unit or 'نامشخص'}",
        shop.address_text or "آدرس: نامشخص",
    ]
    return tool_result("dataset", {"shop": shop, "directions": directions})


def _offer_query(extra_condition: str = "") -> str:
    return f"""
        SELECT
            o.shop_id AS offer_shop_id,
            o.product_id,
            o.price,
            o.price_updated_at,
            o.warranty,
            s.id AS shop_id,
            s.name,
            s.has_real_name,
            s.instagram,
            s.website,
            s.lat,
            s.lng,
            s.address,
            s.mall,
            s.floor,
            s.unit,
            s.payment_options,
            s.fast_delivery,
            s.weekly_hours
        FROM offers AS o
        JOIN shops AS s ON s.id = o.shop_id
        WHERE o.product_id = ?
          AND o.price > 0
          AND s.lat IS NOT NULL
          AND s.lng IS NOT NULL
          {extra_condition}
    """
