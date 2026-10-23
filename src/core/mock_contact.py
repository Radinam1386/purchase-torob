"""Explicit, deterministic Mock calls backed by dataset offers and inquiry history."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Literal, Protocol

from src.core.config import settings
from src.core.contract import InquiryRequestDetails
from src.core.database import database
from src.core.inquiry_simulator import build_draft_message
from src.core.tools.common import product_from_row, shop_result_from_row
from src.core.tools.shops import _offer_query

Scenario = Literal["confirmed", "price_changed", "out_of_stock", "needs_review", "no_answer", "alternative"]
MOCK_PERSONA = "mock_contact:"
LIMITATION = "این تماس کاملاً شبیه‌سازی‌شده است؛ هیچ تماس یا پیامی برای فروشنده ارسال نشده و قیمت و موجودی واقعی تأیید نشده است."


def selection_from_offer(connection, offer_id: str) -> dict:
    offer = connection.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
    if offer is None:
        raise LookupError("آفر در دیتاست پیدا نشد.")
    row = connection.execute(
        _offer_query().replace("AND s.lat IS NOT NULL", "").replace("AND s.lng IS NOT NULL", "") + " AND o.id=?",
        (offer["product_id"], offer_id),
    ).fetchone()
    product = connection.execute("SELECT * FROM products WHERE id=?", (offer["product_id"],)).fetchone()
    if row is None or product is None:
        raise LookupError("محصول یا فروشگاه متناظر با آفر پیدا نشد.")
    result = shop_result_from_row(row, settings.default_lat, settings.default_lng)
    return {"source": "dataset", "product": product_from_row(product).model_dump(mode="json", by_alias=True),
            "shop": result.shop.model_dump(mode="json", by_alias=True),
            "offer": result.offer.model_dump(mode="json", by_alias=True)}


class ContactProvider(Protocol):
    def respond(self, selection: dict, scenario: Scenario, new_price: int | None) -> dict: ...


class MockContactProvider:
    def respond(self, selection: dict, scenario: Scenario, new_price: int | None) -> dict:
        price = selection["offer"]["price"]
        status, stock, simulated_price = "completed", None, None
        if scenario == "confirmed" and price is not None:
            stock, simulated_price = True, price
            reply = f"بله، کالا موجود است؛ قیمت در این سناریو {price:,} تومان است."
        elif scenario == "price_changed" and (new_price is not None or price is not None):
            simulated_price = new_price if new_price is not None else max(price + 1, (price * 105 + 50) // 100)
            stock = True
            reply = f"کالا موجود است؛ قیمت جدید در این سناریو {simulated_price:,} تومان است."
        elif scenario in {"out_of_stock", "alternative"}:
            stock = False
            reply = "این کالا در این سناریو موجود نیست."
        elif scenario == "no_answer":
            status = "no_answer"
            reply = "در سناریوی شبیه‌سازی پاسخی از فروشنده دریافت نشد."
        else:
            status = "needs_review"
            reply = ("قیمت آفر ثبت نشده؛ امکان تأیید قیمت در این سناریو وجود ندارد."
                     if price is None and scenario != "needs_review" else "قیمت و موجودی دقیق مشخص نیست؛ نیاز به بررسی بیشتر دارد.")
        return {"status": status, "simulatedInStock": stock, "simulatedPrice": simulated_price,
                "reply": reply, "role": "system" if scenario == "no_answer" else "seller"}


def _alternatives(connection, selection: dict) -> list[dict]:
    category = connection.execute("SELECT category_norm FROM products WHERE id=?", (selection["product"]["id"],)).fetchone()[0]
    query = _offer_query().replace("o.product_id = ?", "o.product_id IN (SELECT id FROM products WHERE id=? OR (category_norm=? AND category_norm<>''))")
    query = query.replace("AND s.lat IS NOT NULL", "").replace("AND s.lng IS NOT NULL", "")
    rows = connection.execute(query + " AND o.id<>? ORDER BY (o.product_id=?) DESC,(o.shop_id=?) DESC,o.price IS NULL,o.price,o.id LIMIT 3",
        (selection["product"]["id"], category, selection["offer"]["id"], selection["product"]["id"], selection["shop"]["id"])).fetchall()
    return [shop_result_from_row(row, settings.default_lat, settings.default_lng).model_dump(mode="json", by_alias=True) for row in rows]


def create_mock_run(session_id: str, offer_id: str, scenario: Scenario, new_price: int | None = None,
                    run_key: str | None = None, *, provider: ContactProvider | None = None) -> dict:
    run_id = "mock_" + (hashlib.sha256(f"{session_id}:{run_key}".encode()).hexdigest()[:32] if run_key else secrets.token_hex(16))
    request_data = {"offerId": offer_id, "scenario": scenario, "newPrice": new_price}
    with database() as connection:
        existing = connection.execute("SELECT requests_json,payload_json FROM inquiries WHERE id=? AND session_id=? AND persona LIKE 'mock_contact:%'", (run_id, session_id)).fetchone()
        if existing:
            if json.loads(existing["requests_json"]) != request_data:
                raise ValueError("این شناسه اجرا قبلاً برای درخواست دیگری استفاده شده است.")
            return json.loads(existing["payload_json"])
        selection = selection_from_offer(connection, offer_id)
        if new_price is not None and (scenario != "price_changed" or new_price == selection["offer"]["price"]):
            raise ValueError("قیمت جدید باید متفاوت باشد و فقط برای سناریوی تغییر قیمت مجاز است.")
        created_at = datetime.now(timezone.utc).isoformat()
        message = build_draft_message(selection["product"]["titleFa"], selection["offer"]["price"], InquiryRequestDetails(), selection["shop"]["displayName"])
        answer = (provider or MockContactProvider()).respond(selection, scenario, new_price)
        alternatives = _alternatives(connection, selection) if scenario == "alternative" else []
        analysis = {
            "confirmed": "در خروجی Mock، موجودی و قیمت دیتاست یکسان اعلام شدند؛ این نتیجه تأیید واقعی فروشنده نیست.",
            "price_changed": "قیمت شبیه‌سازی با قیمت دیتاست مقایسه شد؛ اختلاف زیر فقط مربوط به سناریوی Mock است.",
            "out_of_stock": "در سناریوی Mock کالا ناموجود اعلام شد؛ موجودی واقعی همچنان تأیید نشده است.",
            "needs_review": "پاسخ شبیه‌سازی برای تصمیم خرید کافی نیست؛ قیمت و موجودی نامشخص می‌مانند.",
            "no_answer": "پاسخی دریافت نشد؛ از بی‌پاسخ بودن نمی‌توان موجودی یا قیمت را نتیجه گرفت.",
            "alternative": ("گزینه‌های مرتبط زیر از آفرهای واقعی دیتاست انتخاب شدند؛ قیمت و موجودی آن‌ها نیازمند بررسی است."
                            if alternatives else "آفر جایگزین مرتبط در دیتاست پیدا نشد؛ گزینه‌ای ساخته نشده است."),
        }[scenario]
        if answer["status"] == "needs_review":
            analysis = "قیمت یا موجودی قابل تأیید نیست؛ نتیجه نیازمند بررسی است و مقدار نامشخص ثبت شد."
        original_price = selection["offer"]["price"]
        difference = answer["simulatedPrice"] - original_price if answer["simulatedPrice"] is not None and original_price is not None else None
        if scenario == "price_changed" and answer["simulatedPrice"] is not None:
            analysis = f"فروشنده شبیه‌سازی‌شده قیمت {answer['simulatedPrice']:,} تومان اعلام کرده است. "
            analysis += (f"این مبلغ نسبت به قیمت دیتاست {abs(difference):,} تومان {'بیشتر' if difference > 0 else 'کمتر'} است. "
                         if difference is not None else "قیمت دیتاست ثبت نشده و اختلاف قابل محاسبه نیست. ")
            analysis += "این نتیجه تأیید واقعی فروشنده محسوب نمی‌شود."
        analysis = "در این شبیه‌سازی، " + analysis
        stages = [{"id": key, "label": label, "timestamp": datetime.now(timezone.utc).isoformat()} for key, label in [
            ("prepared", "آماده‌سازی اطلاعات تماس از دیتاست"), ("started", "شروع شبیه‌سازی با سناریوی انتخابی"),
            ("requested", "ارسال درخواست به موتور Mock"), ("responded", "دریافت پاسخ شبیه‌سازی‌شده"),
            ("analysis", "تحلیل پاسخ توسط Agent و مقایسه با دیتاست"), ("saved", "نمایش نتیجه و ثبت در تاریخچه")]]
        run = {"id": run_id, "source": "simulated", "provider": "mock", "status": answer["status"],
               "scenario": scenario, "createdAt": created_at, "product": selection["product"], "shop": selection["shop"],
               "datasetOffer": selection["offer"], "simulatedPrice": answer["simulatedPrice"], "simulatedInStock": answer["simulatedInStock"],
               "priceDifference": difference, "transcript": [
                   {"role": "system", "text": LIMITATION},
                   {"role": "agent", "text": "عامل هماهنگ‌کننده: آفر انتخابی از دیتاست خوانده شد؛ اجرای سناریوی Mock با اجازه خریدار آغاز شد."},
                   {"role": "agent", "text": "عامل تماس: " + message}, {"role": answer["role"], "text": answer["reply"]},
                   {"role": "agent", "text": "عامل تحلیل: " + analysis}],
               "stages": stages, "analysis": analysis, "alternatives": alternatives, "limitation": LIMITATION}
        connection.execute("""INSERT INTO inquiries
            (id,session_id,shop_id,product_id,offer_id,channel,status,message,requests_json,answer_json,created_at,sent_at,answered_at,persona,simulated,payload_json)
            VALUES (?,?,?,?,?,'ai_call',?,?,?,?,?,?,?,?,1,?)""",
            (run_id, session_id, selection["shop"]["id"], selection["product"]["id"], offer_id,
             "no_answer" if answer["status"] == "no_answer" else "answered", message,
             json.dumps(request_data, ensure_ascii=False), json.dumps(answer, ensure_ascii=False), created_at,
             created_at, created_at, MOCK_PERSONA + scenario, json.dumps(run, ensure_ascii=False)))
    return run


def list_mock_runs(session_id: str, page: int, page_size: int) -> dict:
    with database(readonly=True) as connection:
        try:
            total = connection.execute("SELECT COUNT(*) FROM inquiries WHERE session_id=? AND persona LIKE 'mock_contact:%'", (session_id,)).fetchone()[0]
            rows = connection.execute("SELECT payload_json FROM inquiries WHERE session_id=? AND persona LIKE 'mock_contact:%' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (session_id, page_size, (page - 1) * page_size)).fetchall()
        except sqlite3.OperationalError as error:
            if "no such table: inquiries" not in str(error):
                raise
            total, rows = 0, []
    return {"total": total, "page": page, "page_size": page_size, "data": [json.loads(row["payload_json"]) for row in rows]}


def get_mock_run(session_id: str, run_id: str) -> dict:
    with database(readonly=True) as connection:
        try:
            row = connection.execute("SELECT payload_json FROM inquiries WHERE id=? AND session_id=? AND persona LIKE 'mock_contact:%'", (run_id, session_id)).fetchone()
        except sqlite3.OperationalError as error:
            if "no such table: inquiries" not in str(error):
                raise
            row = None
    if row is None:
        raise LookupError("اجرای Mock پیدا نشد.")
    return json.loads(row["payload_json"])
