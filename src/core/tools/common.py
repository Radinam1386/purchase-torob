"""Conversions from SQLite rows to shared public data contracts."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from src.core.config import settings
from src.core.contract import KnownValue, MarketHub, Offer, PriceFreshness, Product, Shop, ShopResult, Warranty
from src.core.text import normalize_fa, parse_json


def tool_result(source: str, data, **metadata) -> dict:
    """Return JSON-safe data while keeping a uniform tool envelope."""
    return {"source": source, "data": _json_safe(data), **metadata}


def _json_safe(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def product_from_row(row) -> Product:
    specs_rows = parse_json(row["specs"], default=[])
    specs = {
        str(item["key"]): str(item["value"])
        for item in specs_rows
        if isinstance(item, dict) and item.get("key") and item.get("value")
    }
    images = parse_json(row["images"], default=[])
    if not isinstance(images, list):
        images = []

    model = row["model"]
    return Product(
        id=row["id"],
        title_fa=row["title"],
        title_en=model if model and model != "null" else None,
        brand=row["brand"] or None,
        category=row["category"] or None,
        specs=specs,
        images=images,
    )


def payment_options(raw: str | None) -> list[dict] | None:
    if raw is None or raw == "null":
        return None
    value = parse_json(raw, default=None)
    if not isinstance(value, list):
        return None
    return [option for option in value if isinstance(option, dict)]


def supports_in_person_installments(raw: str | None) -> bool | None:
    """Only explicit in-person payment records count as in-person installments."""
    options = payment_options(raw)
    if options is None:
        return None
    return any(option.get("channel") == "in_person" for option in options)


def supports_tarob_pay_in_person(raw: str | None) -> bool | None:
    options = payment_options(raw)
    if options is None:
        return None
    return any(
        option.get("channel") == "in_person"
        and "ترب پی" in normalize_fa(option.get("provider_name", ""))
        for option in options
    )


def shop_from_row(row) -> Shop:
    has_real_name = bool(row["has_real_name"])
    coordinates = valid_coordinates(row["lat"], row["lng"])
    return Shop(
        id=row["shop_id"] if "shop_id" in row.keys() else row["id"],
        display_name=row["name"] if has_real_name else f"فروشگاه #{row['shop_id'] if 'shop_id' in row.keys() else row['id']}",
        has_real_name=has_real_name,
        instagram=row["instagram"] or None,
        website=row["website"] or None,
        lat=coordinates[0] if coordinates else None,
        lng=coordinates[1] if coordinates else None,
        address_text=row["address"] or None,
        mall=row["mall"] or None,
        floor=row["floor"] or None,
        unit=row["unit"] or None,
        hours=parse_json(row["weekly_hours"], default={}) or {},
        tarob_pay_in_store=supports_tarob_pay_in_person(row["payment_options"]),
        installment=supports_in_person_installments(row["payment_options"]),
        express_delivery=(bool(row["fast_delivery"]) if row["fast_delivery"] is not None else None),
    )


def market_hub_from_row(row) -> MarketHub:
    return MarketHub(
        category=row["category"],
        name=row["name"],
        neighborhood=row["neighborhood"],
        lat=float(row["lat"]),
        lng=float(row["lng"]),
        note=row["note"],
        coordinate_source=row["coordinate_source"],
        coordinate_verified=bool(row["coordinate_verified"]),
    )


def haversine_km(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    radius_km = 6371.0
    lat_delta = math.radians(lat_b - lat_a)
    lng_delta = math.radians(lng_b - lng_a)
    value = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(math.radians(lat_a))
        * math.cos(math.radians(lat_b))
        * math.sin(lng_delta / 2) ** 2
    )
    value = min(1, max(0, value))
    return 2 * radius_km * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def valid_coordinates(lat, lng) -> tuple[float, float] | None:
    try:
        latitude, longitude = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def is_open_now(raw_hours: str | None) -> bool | None:
    hours = parse_json(raw_hours)
    if not isinstance(hours, dict):
        return None
    return _is_open_at(hours, datetime.now(ZoneInfo(settings.timezone)))


def _is_open_at(hours: dict, now: datetime) -> bool | None:
    weekday = now.strftime("%a").lower()
    day = hours.get(weekday)
    if not isinstance(day, dict):
        return None
    minute_now = now.hour * 60 + now.minute
    today_result = _is_open_during_shifts(day, minute_now)
    if today_result is True:
        return True

    previous_day_name = (now - timedelta(days=1)).strftime("%a").lower()
    previous_day = hours.get(previous_day_name)
    if isinstance(previous_day, dict) and previous_day.get("status") == "declared":
        for shift in previous_day.get("shifts", []):
            if not isinstance(shift, dict):
                continue
            start = _minutes(shift.get("start_time"))
            end = _minutes(shift.get("end_time"))
            if start is not None and end is not None and start > end and minute_now < end:
                return True
    return today_result


def _is_open_during_shifts(day: dict, minute_now: int) -> bool | None:
    if day.get("status") == "closed":
        return False
    if day.get("status") != "declared":
        return None
    for shift in day.get("shifts", []):
        if not isinstance(shift, dict):
            continue
        start = _minutes(shift.get("start_time"))
        end = _minutes(shift.get("end_time"))
        if start is not None and end is not None and (
            (start <= end and start <= minute_now < end)
            or (start > end and minute_now >= start)
        ):
            return True
    return False


def _minutes(value: str | None) -> int | None:
    try:
        hour, minute = value.split(":", maxsplit=1)
        return int(hour) * 60 + int(minute[:2])
    except (AttributeError, ValueError):
        return None


def calculate_price_freshness(price_updated_at: str | None, now: datetime | None = None) -> PriceFreshness:
    if not price_updated_at:
        return PriceFreshness(days_ago=None, level="unknown", label="نامشخص")
    if now is None:
        now = datetime(2026, 10, 23, tzinfo=ZoneInfo(settings.timezone))
    try:
        updated_dt = datetime.fromisoformat(price_updated_at)
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=now.tzinfo)
        diff_days = max(0, (now.date() - updated_dt.date()).days)
        if diff_days <= 2:
            level = "fresh"
            label = f"تازه ({diff_days} روز پیش)" if diff_days > 0 else "امروز به‌روز شده"
        elif diff_days <= 7:
            level = "moderate"
            label = f"مناسب ({diff_days} روز پیش)"
        else:
            level = "stale"
            label = f"کهنه ({diff_days} روز پیش — نیازمند استعلام)"
        return PriceFreshness(days_ago=diff_days, level=level, label=label)
    except Exception:
        return PriceFreshness(days_ago=None, level="unknown", label="نامشخص")


def shop_result_from_row(row, lat: float, lng: float) -> ShopResult:
    shop = shop_from_row(row)
    distance = haversine_km(lat, lng, shop.lat, shop.lng) if shop.lat is not None and shop.lng is not None else None
    open_value = is_open_now(row["weekly_hours"])
    warranty_data = parse_json(row["warranty"])
    warranty = None
    if isinstance(warranty_data, dict):
        warranty = Warranty(
            provider=warranty_data.get("provider") or None,
            months=warranty_data.get("period_months") or None,
        )

    freshness = calculate_price_freshness(row["price_updated_at"])
    offer = Offer(
        id=row["offer_id"],
        shop_id=row["offer_shop_id"],
        product_id=row["product_id"],
        price=int(row["price"]) if row["price"] is not None else None,
        price_updated_at=row["price_updated_at"],
        price_freshness=freshness,
        warranty=warranty,
        stock="unverified",
    )
    return ShopResult(
        shop=shop,
        offer=offer,
        distance_km=distance,
        open_now=KnownValue(value=open_value, source="dataset", known=open_value is not None),
        reasons=[
            "برای این محصول آفر در دیتاست ترب ثبت شده",
            f"فاصله‌ی مستقیم {distance:.1f} کیلومتر" if distance is not None else "مختصات معتبر موجود نیست؛ محدوده قابل تأیید نیست",
        ],
    )
