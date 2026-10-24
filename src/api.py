"""HTTP boundary for the React shopping interface."""

from __future__ import annotations

import json
import asyncio
import logging
import os
import secrets
import re
import sqlite3
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.core.agent import ChatTurn, ShoppingAgent, create_agent
from src.core.config import settings
from src.core.contract import ConversationState, ShopResult
from src.core.database import database
from src.core.tools.registry import TOOLS_BY_NAME
from src.core.tools.shops import _find_offers

_CATALOG_INTENT_WORDS = {
    "میخوام", "میخوامش", "می", "خوام", "میخواهم", "میخواستم", "میخرم",
    "بخرم", "بگیرم", "میگیرم", "برای", "واسه", "لطفا", "لطفاً",
    "پیشنهاد", "پیشنهاد بده", "پیدا", "کن", "بهم", "یه", "یک",
    "موسیقی", "موزیک", "روزمره", "دانشگاه", "کار", "عکاسی", "بازی",
    "گیم", "ورزش", "استفاده", "حدود", "بودجه", "تومان", "میلیون",
    "گوش", "دادن", "به", "موسیقی",
}


def _catalog_terms(query: str) -> list[str]:
    normalized = query
    if re.search(r"تومان|میلیون|میلیارد|هزار|بودجه|سقف", normalized):
        normalized = re.sub(r"[0-9۰-۹٠-٩][0-9۰-۹٠-٩,.٫]*", " ", normalized)
        normalized = re.sub(r"تومان|میلیون|میلیارد|هزار|بودجه|سقف|حداکثر|تا", " ", normalized)
    return [term for term in normalized.split() if term not in _CATALOG_INTENT_WORDS]

logger = logging.getLogger("purchase_torob.api")

app = FastAPI(title="ترب حضوری", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, allow_inf_nan=False)

    message: str = Field(min_length=1, max_length=4000)
    user_id: str | None = Field(default=None, alias="userId", max_length=100)
    conversation: ConversationState | None = None
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


class LocationRequest(BaseModel):
    text: str = Field(min_length=2, max_length=160)


class OffersRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, allow_inf_nan=False)

    product_id: str = Field(alias="productId", min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius: float = Field(default=4, ge=0, le=100)
    max_price: int | None = Field(default=None, alias="maxPrice", ge=0)
    installment: bool = False
    express: bool = False
    open_now: bool = Field(default=False, alias="openNow")


class OffersResponse(BaseModel):
    source: Literal["dataset"]
    data: list[ShopResult]


class ProductSearchResponse(BaseModel):
    source: Literal["dataset"]
    query: str
    total: int
    page: int
    page_size: int
    data: list[dict]


@lru_cache(maxsize=1)
def _agent() -> ShoppingAgent:
    return create_agent()


@app.get("/api/health")
def health() -> dict[str, bool | str]:
    try:
        with database(readonly=True) as connection:
            for table in ("products", "shops", "offers", "product_fts", "market_hubs"):
                if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is None:
                    raise sqlite3.OperationalError(f"جدول {table} خالی است.")
    except (OSError, sqlite3.Error) as error:
        logger.info("Database readiness check failed: %s", error)
        raise HTTPException(status_code=503, detail="پایگاه داده آماده نیست.") from error
    return {
        "status": "ready",
        "databaseReady": True,
        "llmConfigured": bool(settings.llm_api_key and settings.llm_model and settings.llm_base_url),
    }


@app.get("/api/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


_RATE_LIMIT = max(1, int(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "15")))
_MAX_CONCURRENT_CHATS = max(1, int(os.getenv("CHAT_MAX_CONCURRENT", "4")))
_rate_history: dict[str, deque[float]] = {}
_request_lock = threading.Lock()
_active_chats = 0


def _enforce_chat_limits(client_id: str) -> None:
    now = time.monotonic()
    with _request_lock:
        history = _rate_history.setdefault(client_id, deque())
        while history and now - history[0] >= 60:
            history.popleft()
        if len(history) >= _RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="درخواست‌های گفتگو در این بازه زیاد است؛ کمی بعد دوباره تلاش کن.",
                headers={"Retry-After": "60"},
            )
        history.append(now)
        if len(_rate_history) > 4096:
            for key in tuple(_rate_history):
                if not _rate_history[key] or now - _rate_history[key][-1] >= 60:
                    _rate_history.pop(key, None)


def _reserve_chat_slot() -> bool:
    global _active_chats
    with _request_lock:
        if _active_chats >= _MAX_CONCURRENT_CHATS:
            return False
        _active_chats += 1
        return True


def _release_chat_slot() -> None:
    global _active_chats
    with _request_lock:
        _active_chats = max(0, _active_chats - 1)


@app.post("/api/chat/stream")
async def chat_stream(http_request: Request, request: ChatRequest) -> StreamingResponse:
    client_id = http_request.client.host if http_request.client else "unknown-client"
    _enforce_chat_limits(client_id)
    if not _reserve_chat_slot():
        raise HTTPException(
            status_code=503,
            detail="گفتگوها موقتاً مشغول‌اند؛ چند لحظه‌ی دیگر تلاش کن.",
        )
    try:
        agent = _agent()
    except Exception as error:
        _release_chat_slot()
        logger.exception("Could not create shopping agent")
        raise HTTPException(status_code=503, detail="سرویس راهنمای خرید آماده نیست.") from error

    conversation = request.conversation or agent.initial_state()
    history: list[ChatTurn] = [turn.model_dump() for turn in request.history]
    session_id = http_request.cookies.get("torob_session") or secrets.token_urlsafe(32)
    new_session = http_request.cookies.get("torob_session") is None

    async def events() -> AsyncIterator[str]:
        try:
            async for event in agent.stream(
                request.message,
                user_id=session_id,
                conversation=conversation,
                history=history,
            ):
                yield _sse(event.model_dump(mode="json", by_alias=True, exclude_none=True))

            yield _sse({
                "type": "conversation",
                "conversation": conversation.model_dump(mode="json", by_alias=True),
            })
            yield _sse({"type": "done"})
        except Exception:
            logger.exception("Shopping conversation failed")
            yield _sse({"type": "error", "message": "پاسخ‌گویی با مشکل روبه‌رو شد؛ دوباره تلاش کن."})
        finally:
            _release_chat_slot()

    response = StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
    if new_session:
        response.set_cookie(
            "torob_session",
            session_id,
            httponly=True,
            secure=http_request.url.scheme == "https",
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
            path="/",
        )
    return response


@app.post("/api/location/resolve")
async def resolve_location(request: LocationRequest) -> dict:
    try:
        result = await TOOLS_BY_NAME["resolve_location"].ainvoke({"text": request.text})
    except Exception as error:
        logger.exception("Could not resolve the requested location")
        raise HTTPException(status_code=502, detail="پیدا کردن این محدوده ممکن نشد.") from error

    data = result.get("data") if isinstance(result, dict) else None
    if not data:
        raise HTTPException(status_code=404, detail="این محدوده پیدا نشد؛ نام محله را دقیق‌تر بنویس.")
    return data


@app.post("/api/offers", response_model=OffersResponse)
async def search_offers(request: OffersRequest) -> OffersResponse:
    """Apply the selected filters directly, without another model round trip."""
    try:
        results = await asyncio.to_thread(
            _find_offers, product_id=request.product_id, lat=request.lat,
            lng=request.lng, radius=request.radius, max_price=request.max_price,
            installment=request.installment, express=request.express,
            open_now=request.open_now, result_limit=500,
        )
        return OffersResponse(source="dataset", data=results)
    except Exception as error:
        logger.exception("Could not search offers for product %s", request.product_id)
        raise HTTPException(status_code=500, detail="جستجوی فروشگاه‌ها انجام نشد.") from error


@app.get("/api/products", response_model=ProductSearchResponse)
def search_catalog(q: str = "", page: int = 1, page_size: int = 24,
                   brand: str = "", min_price: int | None = None,
                   max_price: int | None = None,
                   sort: Literal["relevance", "price_asc", "price_desc"] = "relevance") -> ProductSearchResponse:
    """Paginated, read-only catalog search for the product discovery page."""
    from src.core.text import normalize_fa

    page = max(1, page)
    page_size = min(60, max(1, page_size))
    query = normalize_fa(q.strip())
    try:
        with database(readonly=True) as connection:
            clauses = []
            params: list[object] = []
            terms = _catalog_terms(query) if query else []
            if terms:
                # Require every normalized query term; OR produced thousands of weak matches for model names.
                match = " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)
                clauses.append("product_fts MATCH ?")
                params.append(match)
                has_budget_context = bool(re.search(r"تومان|میلیون|میلیارد|هزار|بودجه|سقف", query))
                if not has_budget_context and re.search(r"(?:سامسونگ|samsung|galaxy|گلکسی)?\s*s?\s*\d{2}\s*(?:fe|ultra|plus)?", query, re.I):
                    clauses.append("p.category_norm LIKE '%گوشی موبایل%'")
                elif any(term in query for term in ("هدفون", "هندزفری", "هدست")):
                    clauses.append("p.category_norm LIKE 'هدفون%'")
                elif "لپ تاپ" in query or "لپتاپ" in query or "لپ‌تاپ" in q:
                    clauses.append("p.category_norm LIKE 'لپ%'")
            if brand.strip():
                clauses.append("p.brand LIKE ?")
                params.append(f"%{brand.strip()}%")
            if min_price is not None:
                clauses.append("EXISTS (SELECT 1 FROM offers ox WHERE ox.product_id=p.id AND ox.price>=?)")
                params.append(min_price)
            if max_price is not None:
                clauses.append("EXISTS (SELECT 1 FROM offers ox WHERE ox.product_id=p.id AND ox.price>0 AND ox.price<=?)")
                params.append(max_price)
            where = "WHERE " + " AND ".join(clauses) if clauses else ""
            total = connection.execute(
                f"SELECT COUNT(*) FROM product_fts JOIN products p ON p.id=product_fts.product_id {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT p.id,p.title,p.brand,p.category,p.images,p.specs,
                    (SELECT MIN(o.price) FROM offers o WHERE o.product_id=p.id AND o.price>0) AS min_price
                    FROM product_fts JOIN products p ON p.id=product_fts.product_id {where}
                    ORDER BY {('min_price ASC' if sort == 'price_asc' else 'min_price DESC') if sort != 'relevance' else ('bm25(product_fts, 0, 8, 2, 1)' if query else 'p.title')}
                    LIMIT ? OFFSET ?""",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
    except sqlite3.Error as error:
        logger.exception("Catalog search failed")
        raise HTTPException(status_code=500, detail="جستجوی محصولات انجام نشد.") from error
    results = []
    for row in rows:
        try:
            images = json.loads(row["images"] or "[]")
        except (TypeError, json.JSONDecodeError):
            images = []
        results.append({"id": row["id"], "titleFa": row["title"], "brand": row["brand"],
                        "category": row["category"], "images": images if isinstance(images, list) else [],
                        "minPrice": row["min_price"]})
    return ProductSearchResponse(source="dataset", query=q, total=total, page=page,
                                 page_size=page_size, data=results)


@app.get("/api/products/{product_id}")
def get_catalog_product(product_id: str) -> dict:
    from src.core.tools.common import product_from_row
    with database(readonly=True) as connection:
        row = connection.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="محصول در دیتاست پیدا نشد.")
        offer = connection.execute("SELECT MIN(price) AS price,COUNT(*) AS count FROM offers WHERE product_id=? AND price>0", (product_id,)).fetchone()
    product = product_from_row(row).model_dump(mode="json", by_alias=True)
    return {"source":"dataset", "product":product, "offerCount":offer["count"], "minPrice":offer["price"]}


class DraftInquiryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    shop_id: str = Field(alias="shopId")
    product_id: str = Field(alias="productId")
    offer_id: str | None = Field(default=None, alias="offerId")
    eta_minutes: int | None = Field(default=None, alias="etaMinutes")
    quantity: int = 1
    size_or_color: str | None = Field(default=None, alias="sizeOrColor")
    hold_requested: bool = Field(default=False, alias="holdRequested")
    channel: str | None = None


class ConfirmInquiryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    inquiry_id: str = Field(alias="inquiryId")
    edited_message: str | None = Field(default=None, alias="editedMessage")


class CancelInquiryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    inquiry_id: str = Field(alias="inquiryId")
    reason: str | None = None


class SellerReplyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    action: Literal["in_stock", "out_of_stock", "price_changed", "delay_10m"]
    custom_price: int | None = Field(default=None, alias="customPrice")
    note: str | None = None


class PriceCheckReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    product_id: str = Field(alias="productId", min_length=1, max_length=120)
    shop_id: str = Field(alias="shopId", min_length=1, max_length=120)
    offer_id: str | None = Field(default=None, alias="offerId", max_length=120)
    outcome: Literal["confirmed", "changed", "unavailable", "no_answer", "unclear"]
    reported_price: int | None = Field(default=None, alias="reportedPrice", ge=0)
    method: Literal["phone", "visit", "other"]
    note: str | None = Field(default=None, max_length=1000)


@app.post("/api/inquiries/draft")
async def api_draft_inquiry(request: DraftInquiryRequest) -> dict:
    try:
        result = await TOOLS_BY_NAME["draft_inquiry"].ainvoke({
            "shop_id": request.shop_id,
            "product_id": request.product_id,
            "offer_id": request.offer_id,
            "eta_minutes": request.eta_minutes,
            "quantity": request.quantity,
            "size_or_color": request.size_or_color,
            "hold_requested": request.hold_requested,
            "channel": request.channel,
        })
        return result
    except Exception as error:
        logger.exception("Could not draft inquiry")
        raise HTTPException(status_code=500, detail="تهیه پیش‌نویس استعلام انجام نشد.") from error


@app.post("/api/inquiries/confirm")
async def api_confirm_inquiry(request: ConfirmInquiryRequest) -> dict:
    try:
        result = await TOOLS_BY_NAME["send_inquiry"].ainvoke({
            "inquiry_id": request.inquiry_id,
            "confirmed": True,
            "edited_message": request.edited_message,
        })
        return result
    except Exception as error:
        logger.exception("Could not confirm inquiry")
        raise HTTPException(status_code=500, detail="ارسال استعلام با خطا روبه‌رو شد.") from error


@app.post("/api/inquiries/cancel")
async def api_cancel_inquiry(request: CancelInquiryRequest) -> dict:
    try:
        result = await TOOLS_BY_NAME["cancel_inquiry"].ainvoke({
            "inquiry_id": request.inquiry_id,
            "reason": request.reason,
        })
        return result
    except Exception as error:
        logger.exception("Could not cancel inquiry")
        raise HTTPException(status_code=500, detail="لغو استعلام با خطا روبه‌رو شد.") from error


@app.get("/api/inquiries/{inquiry_id}")
async def api_get_inquiry(inquiry_id: str) -> dict:
    try:
        result = await TOOLS_BY_NAME["get_inquiry_status"].ainvoke({"inquiry_id": inquiry_id})
        return result
    except Exception as error:
        logger.exception("Could not get inquiry")
        raise HTTPException(status_code=404, detail="استعلام یافت نشد.") from error


@app.get("/api/inquiries")
def api_list_inquiries(
    shop_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    query = """
        SELECT i.*, s.name AS shop_name, s.has_real_name, p.title AS product_title, o.price AS offer_price
        FROM inquiries AS i
        LEFT JOIN shops AS s ON s.id = i.shop_id
        LEFT JOIN products AS p ON p.id = i.product_id
        LEFT JOIN offers AS o ON o.id = i.offer_id
        WHERE 1=1
    """
    params: list[object] = []
    if shop_id:
        query += " AND i.shop_id = ?"
        params.append(shop_id)
    if status:
        query += " AND i.status = ?"
        params.append(status)
    query += " ORDER BY i.created_at DESC LIMIT ?"
    params.append(limit)

    with database(readonly=True) as connection:
        rows = connection.execute(query, params).fetchall()
        items = []
        for r in rows:
            shop_display = r["shop_name"] if r["has_real_name"] else f"فروشگاه #{r['shop_id']}"
            reqs = json.loads(r["requests_json"]) if r["requests_json"] else {}
            ans = json.loads(r["answer_json"]) if r["answer_json"] else None
            items.append({
                "id": r["id"],
                "sessionId": r["session_id"],
                "shopId": r["shop_id"],
                "shopName": shop_display,
                "productId": r["product_id"],
                "productTitle": r["product_title"] or "کالا",
                "offerId": r["offer_id"],
                "offerPrice": r["offer_price"],
                "channel": r["channel"],
                "status": r["status"],
                "message": r["message"],
                "requests": reqs,
                "answer": ans,
                "createdAt": r["created_at"],
                "sentAt": r["sent_at"],
                "deliveredAt": r["delivered_at"],
                "readAt": r["read_at"],
                "answeredAt": r["answered_at"],
                "expiresAt": r["expires_at"],
                "persona": r["persona"],
                "batchId": r["batch_id"],
                "simulated": bool(r["simulated"]),
            })
    return {"inquiries": items}


@app.post("/api/price-checks")
def create_price_check(request: PriceCheckReport) -> dict:
    """Store a buyer-reported check separately from the original dataset offer."""
    check_id = secrets.token_urlsafe(12)
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        with database() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS price_checks (
                id TEXT PRIMARY KEY, product_id TEXT NOT NULL, shop_id TEXT NOT NULL,
                offer_id TEXT, outcome TEXT NOT NULL, reported_price INTEGER,
                method TEXT NOT NULL, note TEXT, source TEXT NOT NULL DEFAULT 'buyer_report',
                checked_at TEXT NOT NULL)""")
            exists = connection.execute(
                "SELECT 1 FROM offers WHERE id=? AND product_id=? AND shop_id=?",
                (request.offer_id, request.product_id, request.shop_id),
            ).fetchone() if request.offer_id else connection.execute(
                "SELECT 1 FROM offers WHERE product_id=? AND shop_id=? LIMIT 1",
                (request.product_id, request.shop_id),
            ).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="آفر متناظر در دیتاست پیدا نشد.")
            connection.execute("INSERT INTO price_checks VALUES (?,?,?,?,?,?,?,?,?,?)", (
                check_id, request.product_id, request.shop_id, request.offer_id,
                request.outcome, request.reported_price, request.method, request.note,
                "buyer_report", checked_at,
            ))
    except sqlite3.Error as error:
        logger.exception("Could not save buyer price check")
        raise HTTPException(status_code=500, detail="ثبت نتیجه بررسی انجام نشد.") from error
    return {"id": check_id, "source": "buyer_report", "checkedAt": checked_at,
            "outcome": request.outcome, "reportedPrice": request.reported_price}


@app.get("/api/price-checks")
def list_price_checks(product_id: str, shop_id: str, offer_id: str | None = None) -> dict:
    with database(readonly=True) as connection:
        try:
            rows = connection.execute(
                "SELECT * FROM price_checks WHERE product_id=? AND shop_id=? AND (? IS NULL OR offer_id=?) ORDER BY checked_at DESC LIMIT 20",
                (product_id, shop_id, offer_id, offer_id),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    return {"source": "buyer_report", "checks": [dict(row) for row in rows]}


@app.post("/api/inquiries/{inquiry_id}/seller-reply")
def api_seller_reply(inquiry_id: str, request: SellerReplyRequest) -> dict:
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with database() as connection:
        row = connection.execute("SELECT * FROM inquiries WHERE id = ?", (inquiry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="استعلام پیدا نشد.")

        offer_row = connection.execute("SELECT price FROM offers WHERE id = ?", (row["offer_id"],)).fetchone()
        base_price = offer_row["price"] if offer_row else None

        if request.action == "in_stock":
            new_status = "answered"
            answer = {
                "in_stock": True,
                "price": base_price,
                "note": request.note or "فروشنده با یک لمس موجودی و قیمت را تأیید کرد.",
            }
        elif request.action == "out_of_stock":
            new_status = "answered"
            answer = {
                "in_stock": False,
                "price": None,
                "note": request.note or "فروشنده اعلام کرد این کالا ناموجود است.",
            }
        elif request.action == "price_changed":
            new_status = "answered"
            price = request.custom_price or (round(base_price * 1.08) if base_price else None)
            answer = {
                "in_stock": True,
                "price": price,
                "note": request.note or "فروشنده موجودی را با قیمت جدید اعلام کرد.",
            }
        elif request.action == "delay_10m":
            new_status = "read"
            answer = {
                "in_stock": True,
                "price": base_price,
                "note": "فروشنده پیام را دید و اعلام کرد ظرف ۱۰ دقیقه موجودی دقیق را بررسی می‌کند.",
            }
        else:
            raise HTTPException(status_code=400, detail="اقدام نامعتبر است.")

        connection.execute(
            """
            UPDATE inquiries
            SET status = ?, read_at = COALESCE(read_at, ?), answered_at = ?, answer_json = ?
            WHERE id = ?
            """,
            (new_status, now_iso, now_iso if new_status == "answered" else None, json.dumps(answer, ensure_ascii=False), inquiry_id),
        )

        if row["batch_id"] and new_status == "answered" and answer["in_stock"]:
            from src.core.inquiry_simulator import handle_batch_completion
            handle_batch_completion(connection, row["batch_id"], inquiry_id)

    return {"status": "ok", "newStatus": new_status, "answer": answer}


def _sse(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"data: {serialized}\n\n"
