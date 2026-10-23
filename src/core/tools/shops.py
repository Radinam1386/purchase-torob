"""Offer search, store checks, comparison, inquiry, and alternatives."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from src.core.config import settings
from src.core.contract import InquiryRequestDetails
from src.core.database import database
from src.core.inquiry_simulator import (
    CHANNEL_ESCALATION,
    build_draft_message,
    build_timeline,
    check_shop_open_at_eta,
    choose_default_channel,
    determine_persona,
    handle_batch_completion,
    simulate_seller_response,
)
from src.core.text import parse_json
from src.core.tools.common import (
    calculate_price_freshness,
    is_open_now,
    product_from_row,
    shop_from_row,
    shop_result_from_row,
    tool_result,
)
from src.core.tools.schemas import (
    AlternativesInput,
    CancelInquiryInput,
    CompareShopsInput,
    DraftInquiryInput,
    FollowUpInquiryInput,
    GetInquiryStatusInput,
    GetOffersInput,
    InquiryInput,
    ListInquiriesInput,
    SendInquiryBatchInput,
    SendInquiryInput,
    ShopInput,
    VisitGuideInput,
)
from src.core.user_context import get_current_user_id


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
    express: bool = False, open_now: bool = False, result_limit: int | None = None,
):
    with database(readonly=True) as connection:
        rows = connection.execute(_offer_query(), (product_id,)).fetchall()

    results = [shop_result_from_row(row, lat, lng) for row in rows]
    results = [item for item in results if item.distance_km is not None and item.distance_km <= radius]
    if max_price is not None:
        results = [
            item for item in results
            if item.offer.price is not None and item.offer.price <= max_price
        ]
    if installment:
        results = [item for item in results if item.shop.installment is True]
    if express:
        results = [item for item in results if item.shop.express_delivery is True]
    if open_now:
        results = [item for item in results if item.open_now.value is True]
    results = sorted(results, key=lambda item: item.distance_km)
    return results[:max(1, result_limit)] if result_limit is not None else results


@tool(args_schema=CompareShopsInput)
def compare_shops(
    product_id: str,
    shop_ids: list[str] | None = None,
    offer_ids: list[str] | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """مقایسه‌ی فروشگاه‌های منتخب بر اساس آفر، فاصله، ساعت و پرداخت."""
    center_lat = lat if lat is not None else settings.default_lat
    center_lng = lng if lng is not None else settings.default_lng
    selected_offer_ids = list(dict.fromkeys((offer_ids or [])[:8]))
    identifiers = list(dict.fromkeys((shop_ids or [])[:8]))
    if selected_offer_ids:
        condition = f"AND o.id IN ({','.join('?' for _ in selected_offer_ids)})"
        parameters = (product_id, *selected_offer_ids)
    elif identifiers:
        condition = f"AND s.id IN ({','.join('?' for _ in identifiers)})"
        parameters = (product_id, *identifiers)
    else:
        return tool_result("dataset", [])
    query = _offer_query(extra_condition=condition)
    with database(readonly=True) as connection:
        rows = connection.execute(query, parameters).fetchall()

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


@tool(args_schema=DraftInquiryInput)
def draft_inquiry(
    shop_id: str,
    product_id: str,
    offer_id: str | None = None,
    eta_minutes: int | None = None,
    quantity: int = 1,
    size_or_color: str | None = None,
    hold_requested: bool = False,
    channel: str | None = None,
) -> dict:
    """تهیه پیش‌نویس پیام استعلام کوتاه و مؤدبانه برای تأیید توسط کاربر؛ ارسال نمی‌شود."""
    session_id = get_current_user_id()
    digest = hashlib.sha256(f"{session_id}:{shop_id}:{product_id}".encode()).hexdigest()
    inquiry_id = f"inq_{digest[:12]}"
    with database() as connection:
        shop_row = connection.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
        if shop_row is None:
            raise ValueError(f"فروشگاه {shop_id} پیدا نشد")
        prod_row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if prod_row is None:
            raise ValueError(f"کالای {product_id} پیدا نشد")

        query = "SELECT id, price, price_updated_at FROM offers WHERE shop_id = ? AND product_id = ?"
        params: tuple[object, ...] = (shop_id, product_id)
        if offer_id:
            query += " AND id = ?"
            params += (offer_id,)
        query += " ORDER BY price_updated_at DESC LIMIT 1"
        offer_row = connection.execute(query, params).fetchone()
        if offer_row is None:
            raise ValueError("برای این فروشگاه و کالا آفری ثبت نشده است")

        shop = shop_from_row(shop_row)
        product = product_from_row(prod_row)
        freshness = calculate_price_freshness(offer_row["price_updated_at"])
        offer = {
            "id": offer_row["id"],
            "shop_id": shop_id,
            "product_id": product_id,
            "price": offer_row["price"],
            "price_unit": "تومان",
            "price_updated_at": offer_row["price_updated_at"],
            "price_freshness": freshness.model_dump(mode="json", by_alias=True),
            "stock": "unverified",
        }

        open_at_eta = check_shop_open_at_eta(shop_row["weekly_hours"], eta_minutes)
        warning = None
        if open_at_eta is False:
            warning = f"هشدار ساعت کاری: بر اساس اطلاعات ثبت‌شده، فروشگاه در زمان رسیدن شما ({eta_minutes or 0} دقیقه دیگر) بسته است."

        selected_channel = channel if channel in {"panel", "sms", "chat", "ai_call"} else choose_default_channel(shop_row)

        requests = InquiryRequestDetails(
            eta_minutes=eta_minutes,
            quantity=quantity,
            size_or_color=size_or_color,
            hold_requested=hold_requested,
        )

        message = build_draft_message(
            product_title=product.title_fa,
            price=offer_row["price"],
            requests=requests,
            shop_display_name=shop.display_name,
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        is_closed_now = is_open_now(shop_row["weekly_hours"]) is False
        persona = determine_persona(shop_id, product_id, is_closed=is_closed_now or (open_at_eta is False))

        connection.execute(
            """
            INSERT OR REPLACE INTO inquiries (
                id, session_id, shop_id, product_id, offer_id,
                channel, status, message, requests_json, answer_json,
                created_at, persona, simulated, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                inquiry_id,
                session_id,
                shop_id,
                product_id,
                offer_row["id"],
                selected_channel,
                "draft",
                message,
                json.dumps(requests.model_dump(mode="json", by_alias=True), ensure_ascii=False),
                None,
                now_iso,
                persona,
                json.dumps({
                    "id": inquiry_id,
                    "shop_id": shop_id,
                    "product_id": product_id,
                    "offer_id": offer_row["id"],
                    "status": "draft",
                    "simulated": True,
                }, ensure_ascii=False),
            ),
        )

        card_data = {
            "kind": "message_draft",
            "inquiry_id": inquiry_id,
            "shop": shop.model_dump(mode="json", by_alias=True),
            "product": product.model_dump(mode="json", by_alias=True),
            "offer": offer,
            "channel": selected_channel,
            "message": message,
            "requests": requests.model_dump(mode="json", by_alias=True),
            "shop_open_at_eta": {
                "value": open_at_eta,
                "known": open_at_eta is not None,
                "source": "dataset",
            },
            "warning": warning,
            "confirmed": False,
            "source": "simulated",
        }
        return tool_result("simulated", card_data)


@tool(args_schema=SendInquiryInput)
def send_inquiry(
    inquiry_id: str,
    confirmed: bool = False,
    edited_message: str | None = None,
) -> dict:
    """ارسال استعلام پس از تأیید صریح کاربر و شبیه‌سازی مراحل تحویل و پاسخ فروشنده."""
    if not confirmed:
        raise ValueError("استعلام بدون تأیید صریح کاربر ارسال نمی‌شود. لطفاً پیش‌نویس پیام را به کاربر نشان بده و تأیید بگیر.")

    with database() as connection:
        row = connection.execute("SELECT * FROM inquiries WHERE id = ? AND (persona IS NULL OR persona NOT LIKE 'mock_contact:%')", (inquiry_id,)).fetchone()
        if row is None:
            raise ValueError(f"استعلام با شناسه {inquiry_id} یافت نشد")

        shop_row = connection.execute("SELECT * FROM shops WHERE id = ?", (row["shop_id"],)).fetchone()
        prod_row = connection.execute("SELECT * FROM products WHERE id = ?", (row["product_id"],)).fetchone()
        offer_row = connection.execute("SELECT * FROM offers WHERE id = ?", (row["offer_id"],)).fetchone()

        message = edited_message or row["message"]
        now_utc = datetime.now(timezone.utc)
        sent_at = now_utc.isoformat()
        expires_at = (now_utc + timedelta(minutes=10)).isoformat()

        inquiry_record = {
            "id": row["id"],
            "session_id": row["session_id"],
            "shop_id": row["shop_id"],
            "product_id": row["product_id"],
            "offer_id": row["offer_id"],
            "channel": row["channel"],
            "message": message,
            "requests": parse_json(row["requests_json"], default={}),
            "created_at": row["created_at"],
            "sent_at": sent_at,
            "expires_at": expires_at,
            "persona": row["persona"],
            "batch_id": row["batch_id"],
            "simulated": True,
        }

        sim_result = simulate_seller_response(
            inquiry_record,
            offer_row["price"] if offer_row else None,
            shop_name=shop_row["name"] if shop_row and shop_row["has_real_name"] else f"فروشگاه #{row['shop_id']}",
            product_title=prod_row["title"] if prod_row else "کالا",
        )

        connection.execute(
            """
            UPDATE inquiries
            SET status = ?, message = ?, sent_at = ?, delivered_at = ?,
                read_at = ?, answered_at = ?, expires_at = ?, answer_json = ?, payload_json = ?
            WHERE id = ?
            """,
            (
                sim_result["status"],
                message,
                sim_result["sent_at"],
                sim_result["delivered_at"],
                sim_result["read_at"],
                sim_result["answered_at"],
                expires_at,
                json.dumps(sim_result["answer"], ensure_ascii=False),
                json.dumps(sim_result, ensure_ascii=False),
                inquiry_id,
            ),
        )

        if row["batch_id"] and sim_result["status"] == "answered" and sim_result["answer"].get("in_stock") is True:
            handle_batch_completion(connection, row["batch_id"], inquiry_id)

        shop = shop_from_row(shop_row) if shop_row else None
        product = product_from_row(prod_row) if prod_row else None

        card_data = {
            "kind": "inquiry",
            "inquiry": sim_result,
            "shop": shop.model_dump(mode="json", by_alias=True) if shop else None,
            "product": product.model_dump(mode="json", by_alias=True) if product else None,
            "source": "simulated",
        }
        return tool_result("simulated", card_data)


@tool(args_schema=SendInquiryBatchInput)
def send_inquiry_batch(
    shop_ids: list[str],
    product_id: str,
    eta_minutes: int | None = None,
    quantity: int = 1,
    size_or_color: str | None = None,
    hold_requested: bool = False,
    confirmed: bool = False,
) -> dict:
    """استعلام گروهی هم‌زمان از ۲ تا ۳ فروشگاه؛ با اولین پاسخ مثبت بقیه لغو می‌شوند."""
    if not confirmed:
        raise ValueError("ارسال استعلام گروهی بدون تأیید صریح کاربر امکان‌پذیر نیست.")

    session_id = get_current_user_id()
    digest = hashlib.sha256(f"{session_id}:{product_id}:{','.join(shop_ids)}".encode()).hexdigest()
    batch_id = f"batch_{digest[:10]}"
    items = []

    with database() as connection:
        prod_row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if prod_row is None:
            raise ValueError(f"کالای {product_id} پیدا نشد")
        product = product_from_row(prod_row)

        found_positive = False
        selected_shops = shop_ids[:3]
        for sid in selected_shops:
            shop_row = connection.execute("SELECT * FROM shops WHERE id = ?", (sid,)).fetchone()
            if not shop_row:
                continue
            offer_row = connection.execute(
                "SELECT * FROM offers WHERE shop_id = ? AND product_id = ? ORDER BY price_updated_at DESC LIMIT 1",
                (sid, product_id),
            ).fetchone()
            if not offer_row:
                continue

            shop = shop_from_row(shop_row)
            freshness = calculate_price_freshness(offer_row["price_updated_at"])
            offer = {
                "id": offer_row["id"],
                "shop_id": sid,
                "product_id": product_id,
                "price": offer_row["price"],
                "price_unit": "تومان",
                "price_updated_at": offer_row["price_updated_at"],
                "price_freshness": freshness.model_dump(mode="json", by_alias=True),
                "stock": "unverified",
            }

            channel = choose_default_channel(shop_row)
            reqs = InquiryRequestDetails(
                eta_minutes=eta_minutes,
                quantity=quantity,
                size_or_color=size_or_color,
                hold_requested=hold_requested,
            )
            msg = build_draft_message(product.title_fa, offer_row["price"], reqs, shop.display_name)
            inq_digest = hashlib.sha256(f"{batch_id}:{sid}".encode()).hexdigest()
            inq_id = f"inq_{inq_digest[:12]}"
            now_utc = datetime.now(timezone.utc)
            now_iso = now_utc.isoformat()
            is_closed = is_open_now(shop_row["weekly_hours"]) is False
            persona = determine_persona(sid, product_id, is_closed=is_closed)

            if found_positive:
                status = "cancelled"
                answer = {
                    "in_stock": False,
                    "price": None,
                    "note": "به دلیل دریافت پاسخ مثبت از فروشگاه دیگر، این استعلام به صورت خودکار لغو شد.",
                }
                connection.execute(
                    """
                    INSERT OR REPLACE INTO inquiries (
                        id, session_id, shop_id, product_id, offer_id,
                        channel, status, message, requests_json, answer_json,
                        created_at, sent_at, answered_at, persona, simulated, batch_id, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        inq_id, session_id, sid, product_id, offer_row["id"],
                        channel, status, msg,
                        json.dumps(reqs.model_dump(mode="json", by_alias=True), ensure_ascii=False),
                        json.dumps(answer, ensure_ascii=False),
                        now_iso, now_iso, now_iso, persona, batch_id,
                        json.dumps({"id": inq_id, "status": status, "simulated": True}, ensure_ascii=False),
                    ),
                )
                items.append({
                    "inquiry_id": inq_id,
                    "shop": shop.model_dump(mode="json", by_alias=True),
                    "offer": offer,
                    "status": status,
                    "channel": channel,
                    "answer": answer,
                })
                continue

            inquiry_record = {
                "id": inq_id,
                "session_id": session_id,
                "shop_id": sid,
                "product_id": product_id,
                "offer_id": offer_row["id"],
                "channel": channel,
                "message": msg,
                "requests": reqs.model_dump(mode="json", by_alias=True),
                "created_at": now_iso,
                "sent_at": now_iso,
                "expires_at": (now_utc + timedelta(minutes=10)).isoformat(),
                "persona": persona,
                "batch_id": batch_id,
                "simulated": True,
            }

            sim_res = simulate_seller_response(
                inquiry_record,
                offer_row["price"],
                shop_name=shop.display_name,
                product_title=product.title_fa,
            )

            connection.execute(
                """
                INSERT OR REPLACE INTO inquiries (
                    id, session_id, shop_id, product_id, offer_id,
                    channel, status, message, requests_json, answer_json,
                    created_at, sent_at, delivered_at, read_at, answered_at,
                    expires_at, persona, simulated, batch_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    inq_id, session_id, sid, product_id, offer_row["id"],
                    channel, sim_res["status"], msg,
                    json.dumps(reqs.model_dump(mode="json", by_alias=True), ensure_ascii=False),
                    json.dumps(sim_res["answer"], ensure_ascii=False),
                    now_iso, sim_res["sent_at"], sim_res["delivered_at"], sim_res["read_at"],
                    sim_res["answered_at"], inquiry_record["expires_at"], persona,
                    batch_id, json.dumps(sim_res, ensure_ascii=False),
                ),
            )

            items.append({
                "inquiry_id": inq_id,
                "shop": shop.model_dump(mode="json", by_alias=True),
                "offer": offer,
                "status": sim_res["status"],
                "channel": channel,
                "answer": sim_res["answer"],
            })

            if sim_res["status"] == "answered" and sim_res["answer"].get("in_stock") is True:
                found_positive = True
                handle_batch_completion(connection, batch_id, inq_id)

        card_data = {
            "kind": "inquiry_batch",
            "batch_id": batch_id,
            "product": product.model_dump(mode="json", by_alias=True),
            "items": items,
            "source": "simulated",
        }
        return tool_result("simulated", card_data)


@tool(args_schema=GetInquiryStatusInput)
def get_inquiry_status(inquiry_id: str) -> dict:
    """دریافت آخرین وضعیت و تایم‌لاین یک استعلام شبیه‌سازی‌شده."""
    with database(readonly=True) as connection:
        row = connection.execute("SELECT * FROM inquiries WHERE id = ? AND (persona IS NULL OR persona NOT LIKE 'mock_contact:%')", (inquiry_id,)).fetchone()
        if not row:
            raise ValueError(f"استعلام با شناسه {inquiry_id} یافت نشد")
        shop_row = connection.execute("SELECT * FROM shops WHERE id = ?", (row["shop_id"],)).fetchone()
        prod_row = connection.execute("SELECT * FROM products WHERE id = ?", (row["product_id"],)).fetchone()

        shop = shop_from_row(shop_row) if shop_row else None
        product = product_from_row(prod_row) if prod_row else None

        timeline = build_timeline(
            row["status"],
            row["created_at"],
            row["sent_at"],
            row["delivered_at"],
            row["read_at"],
            row["answered_at"],
        )
        inquiry_data = {
            "id": row["id"],
            "session_id": row["session_id"],
            "shop_id": row["shop_id"],
            "product_id": row["product_id"],
            "offer_id": row["offer_id"],
            "channel": row["channel"],
            "status": row["status"],
            "message": row["message"],
            "requests": parse_json(row["requests_json"], default={}),
            "answer": parse_json(row["answer_json"], default=None),
            "timeline": [t.model_dump(mode="json", by_alias=True) for t in timeline],
            "created_at": row["created_at"],
            "sent_at": row["sent_at"],
            "delivered_at": row["delivered_at"],
            "read_at": row["read_at"],
            "answered_at": row["answered_at"],
            "expires_at": row["expires_at"],
            "persona": row["persona"],
            "batch_id": row["batch_id"],
            "simulated": True,
        }
        card_data = {
            "kind": "inquiry",
            "inquiry": inquiry_data,
            "shop": shop.model_dump(mode="json", by_alias=True) if shop else None,
            "product": product.model_dump(mode="json", by_alias=True) if product else None,
            "source": "simulated",
        }
        return tool_result("simulated", card_data)


@tool(args_schema=ListInquiriesInput)
def list_inquiries(
    shop_id: str | None = None,
    status: str | None = None,
    limit: int = 10,
) -> dict:
    """فهرست استعلام‌های ثبت‌شده در جلسه یا فروشگاه برای نظارت و پنل شبیه‌ساز."""
    query = "SELECT * FROM inquiries WHERE (persona IS NULL OR persona NOT LIKE 'mock_contact:%')"
    params: list[object] = []
    if shop_id:
        query += " AND shop_id = ?"
        params.append(shop_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with database(readonly=True) as connection:
        rows = connection.execute(query, params).fetchall()
        inquiries = []
        for row in rows:
            inquiries.append({
                "id": row["id"],
                "session_id": row["session_id"],
                "shop_id": row["shop_id"],
                "product_id": row["product_id"],
                "offer_id": row["offer_id"],
                "channel": row["channel"],
                "status": row["status"],
                "message": row["message"],
                "requests": parse_json(row["requests_json"], default={}),
                "answer": parse_json(row["answer_json"], default=None),
                "created_at": row["created_at"],
                "sent_at": row["sent_at"],
                "delivered_at": row["delivered_at"],
                "read_at": row["read_at"],
                "answered_at": row["answered_at"],
                "expires_at": row["expires_at"],
                "persona": row["persona"],
                "batch_id": row["batch_id"],
                "simulated": True,
            })
    return tool_result("simulated", inquiries)


@tool(args_schema=CancelInquiryInput)
def cancel_inquiry(inquiry_id: str, reason: str | None = None) -> dict:
    """لغو استعلام معلق توسط کاربر یا سیستم."""
    now_iso = datetime.now(timezone.utc).isoformat()
    note = reason or "استعلام توسط کاربر لغو شد."
    with database() as connection:
        row = connection.execute("SELECT * FROM inquiries WHERE id = ? AND (persona IS NULL OR persona NOT LIKE 'mock_contact:%')", (inquiry_id,)).fetchone()
        if not row:
            raise ValueError(f"استعلام با شناسه {inquiry_id} یافت نشد")
        answer = {"in_stock": False, "price": None, "note": note}
        connection.execute(
            """
            UPDATE inquiries
            SET status = 'cancelled', answer_json = ?, answered_at = ?
            WHERE id = ?
            """,
            (json.dumps(answer, ensure_ascii=False), now_iso, inquiry_id),
        )
    return get_inquiry_status.invoke({"inquiry_id": inquiry_id})


@tool(args_schema=FollowUpInquiryInput)
def follow_up_inquiry(inquiry_id: str, escalate_channel: bool = True) -> dict:
    """پیگیری فعال استعلام؛ ارتقای کانال در صورت بی‌پاسخ بودن و بازگرداندن وضعیت."""
    with database() as connection:
        row = connection.execute("SELECT * FROM inquiries WHERE id = ? AND (persona IS NULL OR persona NOT LIKE 'mock_contact:%')", (inquiry_id,)).fetchone()
        if not row:
            raise ValueError(f"استعلام با شناسه {inquiry_id} یافت نشد")

        current_status = row["status"]
        current_channel = row["channel"]

        if current_status == "no_answer" and escalate_channel:
            next_channel = CHANNEL_ESCALATION.get(current_channel)
            if next_channel:
                now_utc = datetime.now(timezone.utc)
                now_iso = now_utc.isoformat()
                expires_at = (now_utc + timedelta(minutes=10)).isoformat()
                shop_row = connection.execute("SELECT * FROM shops WHERE id = ?", (row["shop_id"],)).fetchone()
                prod_row = connection.execute("SELECT * FROM products WHERE id = ?", (row["product_id"],)).fetchone()
                offer_row = connection.execute("SELECT * FROM offers WHERE id = ?", (row["offer_id"],)).fetchone()

                inquiry_record = {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "shop_id": row["shop_id"],
                    "product_id": row["product_id"],
                    "offer_id": row["offer_id"],
                    "channel": next_channel,
                    "message": row["message"],
                    "requests": parse_json(row["requests_json"], default={}),
                    "created_at": row["created_at"],
                    "sent_at": now_iso,
                    "expires_at": expires_at,
                    "persona": row["persona"],
                    "batch_id": row["batch_id"],
                    "simulated": True,
                }
                sim_res = simulate_seller_response(
                    inquiry_record,
                    offer_row["price"] if offer_row else None,
                    shop_name=shop_row["name"] if shop_row and shop_row["has_real_name"] else f"فروشگاه #{row['shop_id']}",
                    product_title=prod_row["title"] if prod_row else "کالا",
                )
                connection.execute(
                    """
                    UPDATE inquiries
                    SET channel = ?, status = ?, sent_at = ?, delivered_at = ?,
                        read_at = ?, answered_at = ?, expires_at = ?, answer_json = ?, payload_json = ?
                    WHERE id = ?
                    """,
                    (
                        next_channel,
                        sim_res["status"],
                        sim_res["sent_at"],
                        sim_res["delivered_at"],
                        sim_res["read_at"],
                        sim_res["answered_at"],
                        expires_at,
                        json.dumps(sim_res["answer"], ensure_ascii=False),
                        json.dumps(sim_res, ensure_ascii=False),
                        inquiry_id,
                    ),
                )
                return get_inquiry_status.invoke({"inquiry_id": inquiry_id})

    return get_inquiry_status.invoke({"inquiry_id": inquiry_id})


@tool(args_schema=InquiryInput)
def inquire_shop(shop_id: str, product_id: str, offer_id: str | None = None) -> dict:
    """ساخت پاسخ قطعی و شفافِ نمونه‌سازی؛ هیچ پیام واقعی ارسال نمی‌شود."""
    session_id = get_current_user_id()
    digest = hashlib.sha256(f"{shop_id}:{product_id}".encode()).hexdigest()
    inquiry_id = f"inq_{digest[:12]}"
    with database() as connection:
        query = "SELECT id, price FROM offers WHERE shop_id = ? AND product_id = ?"
        parameters: tuple[object, ...] = (shop_id, product_id)
        if offer_id:
            query += " AND id = ?"
            parameters += (offer_id,)
        query += " ORDER BY price_updated_at DESC LIMIT 1"
        offer = connection.execute(query, parameters).fetchone()
        if offer is None:
            raise ValueError("برای این فروشگاه و محصول آفر ثبت نشده است")

        outcome = int(digest[:8], 16) % 4
        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()
        if outcome == 3:
            status, answer = "no_answer", None
        else:
            in_stock = outcome in {0, 2}
            changed_price = outcome == 2
            status = "answered"
            answer = {
                "in_stock": in_stock,
                "price": (
                    round(int(offer["price"]) * 1.05)
                    if changed_price and offer["price"] is not None else offer["price"]
                ),
                "note": (
                    "قیمت در پاسخ نمونه‌سازی‌شده ۵٪ بیشتر از قیمت ثبت‌شده است."
                    if changed_price and offer["price"] is not None
                    else "قیمت آفر ثبت نشده؛ فقط پاسخ نمونه‌سازی‌شده‌ی موجودی است."
                    if offer["price"] is None
                    else "پاسخ موجودی و قیمت، صرفاً نمونه‌سازی‌شده است."
                ),
            }

        timeline = build_timeline(status, now_iso, now_iso, now_iso, now_iso, now_iso if status == "answered" else None)
        inquiry = {
            "id": inquiry_id,
            "session_id": session_id,
            "shop_id": shop_id,
            "product_id": product_id,
            "offer_id": offer["id"],
            "channel": "panel",
            "status": status,
            "answer": answer,
            "timeline": [t.model_dump(mode="json", by_alias=True) for t in timeline],
            "created_at": now_iso,
            "sent_at": now_iso,
            "answered_at": now_iso if status == "answered" else None,
            "simulated": True,
        }
        connection.execute(
            """
            INSERT OR REPLACE INTO inquiries (
                id, session_id, shop_id, product_id, offer_id,
                channel, status, answer_json, created_at, sent_at,
                answered_at, simulated, payload_json
            ) VALUES (?, ?, ?, ?, ?, 'panel', ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                inquiry_id, session_id, shop_id, product_id, offer["id"],
                status, json.dumps(answer, ensure_ascii=False) if answer else None,
                now_iso, now_iso, now_iso if status == "answered" else None,
                json.dumps(inquiry, ensure_ascii=False),
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
    installment: bool = False,
    express: bool = False,
    open_now: bool = False,
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
        latitude_delta = radius / 110.574
        longitude_delta = radius / max(
            1, 111.320 * abs(math.cos(math.radians(center_lat)))
        )
        rows = connection.execute(
            """
            SELECT p.* FROM products AS p
            WHERE p.category_norm = ?
              AND EXISTS (
                  SELECT 1 FROM offers AS candidate_offer
                  JOIN shops AS candidate_shop ON candidate_shop.id = candidate_offer.shop_id
                  WHERE candidate_offer.product_id = p.id
                    AND (candidate_offer.price IS NULL OR candidate_offer.price > 0)
                    AND (? IS NULL OR candidate_offer.price <= ?)
                    AND candidate_shop.lat BETWEEN ? AND ?
                    AND candidate_shop.lng BETWEEN ? AND ?
                    AND (? IS NULL OR candidate_shop.id != ?)
              )
            ORDER BY p.title
            """,
            (
                selected["category_norm"], max_price, max_price,
                center_lat - latitude_delta, center_lat + latitude_delta,
                center_lng - longitude_delta, center_lng + longitude_delta,
                shop_id, shop_id,
            ),
        ).fetchall()

    products_by_id = {row["id"]: product_from_row(row) for row in rows}
    results = []
    same_product_offers = _find_offers(
        product_id=product_id,
        lat=center_lat,
        lng=center_lng,
        radius=radius,
        max_price=max_price,
        installment=installment,
        express=express,
        open_now=open_now,
    )
    same_product_offers = [
        result for result in same_product_offers
        if not shop_id or result.shop.id != shop_id
    ]
    if same_product_offers:
        with database(readonly=True) as connection:
            selected_product = connection.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()
        if selected_product:
            products_by_id = {product_id: product_from_row(selected_product), **products_by_id}
            results.extend(same_product_offers[:2])

    for candidate_id in products_by_id:
        if candidate_id == product_id:
            continue
        offers = _find_offers(
            product_id=candidate_id,
            lat=center_lat,
            lng=center_lng,
            radius=radius,
            max_price=max_price,
            installment=installment,
            express=express,
            open_now=open_now,
        )
        offers = [result for result in offers if not shop_id or result.shop.id != shop_id]
        results.extend(offers[:2])
        if len(results) >= 20:
            break

    visible_results = results[:20]
    matched_ids = {item.offer.product_id for item in visible_results}
    products = [item for key, item in products_by_id.items() if key in matched_ids][:10]
    return tool_result("dataset", {"products": products, "results": visible_results})


@tool(args_schema=VisitGuideInput)
def get_shop_location_hint(
    shop_id: str,
    product_id: str | None = None,
    offer_id: str | None = None,
    backup_shop_id: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """ساخت کارت مراجعه با جزئیات فروشگاه، آفر، استعلام و گزینه‌ی پشتیبان."""
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
    center_lat = lat if lat is not None else settings.default_lat
    center_lng = lng if lng is not None else settings.default_lng
    result = None
    inquiry = None
    backup = None
    if product_id:
        matching_offers = _find_offers(
            product_id=product_id, lat=center_lat, lng=center_lng, radius=100
        )
        result = next(
            (
                item for item in matching_offers
                if item.offer.id == offer_id and item.shop.id == shop_id
            ),
            None,
        ) if offer_id else None
        if offer_id and result is None:
            raise ValueError("آفر انتخاب‌شده برای این فروشگاه پیدا نشد")
        if not offer_id:
            result = next((item for item in matching_offers if item.shop.id == shop_id), None)
        with database(readonly=True) as connection:
            inquiry_row = connection.execute(
                "SELECT payload_json FROM inquiries WHERE shop_id=? AND product_id=? AND (persona IS NULL OR persona NOT LIKE 'mock_contact:%') ORDER BY created_at DESC LIMIT 1",
                (shop_id, product_id),
            ).fetchone()
        if inquiry_row:
            inquiry = json.loads(inquiry_row["payload_json"])
        backups = _find_offers(
            product_id=product_id,
            lat=center_lat,
            lng=center_lng,
            radius=100,
        )
        if backup_shop_id:
            backup = next(
                (item for item in backups if item.shop.id == backup_shop_id), None
            )
        else:
            backup = next(
                (item for item in backups if item.shop.id != shop_id), None
            )
    return tool_result(
        "dataset",
        {"shop": shop, "directions": directions, "offer": result, "inquiry": inquiry, "backup": backup},
    )


def _offer_query(extra_condition: str = "") -> str:
    return f"""
        SELECT
            o.id AS offer_id,
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
          AND (o.price IS NULL OR o.price > 0)
          AND s.lat IS NOT NULL
          AND s.lng IS NOT NULL
          {extra_condition}
    """
