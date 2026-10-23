"""HTTP boundary for the React shopping interface."""

from __future__ import annotations

import json
import logging
import os
import secrets
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
        result = await TOOLS_BY_NAME["get_offers"].ainvoke({
            "product_id": request.product_id,
            "lat": request.lat,
            "lng": request.lng,
            "radius": request.radius,
            "max_price": request.max_price,
            "installment": request.installment,
            "express": request.express,
            "open_now": request.open_now,
        })
        return OffersResponse.model_validate(result)
    except Exception as error:
        logger.exception("Could not search offers for product %s", request.product_id)
        raise HTTPException(status_code=500, detail="جستجوی فروشگاه‌ها انجام نشد.") from error


def _sse(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"data: {serialized}\n\n"
