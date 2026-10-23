"""HTTP boundary for the React shopping interface."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.core.agent import ChatTurn, ShoppingAgent, create_agent
from src.core.config import settings
from src.core.contract import ConversationState, ShopResult
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
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="local", alias="userId")
    conversation: ConversationState | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class LocationRequest(BaseModel):
    text: str = Field(min_length=2, max_length=160)


class OffersRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(alias="productId", min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius: float = Field(default=4, ge=0, le=100)
    max_price: int | None = Field(default=None, alias="maxPrice", ge=0)
    installment: bool = False
    open_now: bool = Field(default=False, alias="openNow")


class OffersResponse(BaseModel):
    source: Literal["dataset"]
    data: list[ShopResult]


@lru_cache(maxsize=1)
def _agent() -> ShoppingAgent:
    return create_agent()


@app.get("/api/health")
def health() -> dict[str, bool | str]:
    return {
        "status": "ok",
        "databaseReady": settings.database_path.exists(),
        "llmConfigured": bool(settings.llm_api_key and settings.llm_model and settings.llm_base_url),
    }


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    try:
        agent = _agent()
    except Exception as error:
        logger.exception("Could not create shopping agent")
        raise HTTPException(status_code=503, detail="سرویس راهنمای خرید آماده نیست.") from error

    conversation = request.conversation or agent.initial_state()
    history: list[ChatTurn] = [turn.model_dump() for turn in request.history]

    async def events() -> AsyncIterator[str]:
        try:
            async for event in agent.stream(
                request.message,
                user_id=request.user_id,
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

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


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
            "open_now": request.open_now,
        })
        return OffersResponse.model_validate(result)
    except Exception as error:
        logger.exception("Could not search offers for product %s", request.product_id)
        raise HTTPException(status_code=500, detail="جستجوی فروشگاه‌ها انجام نشد.") from error


def _sse(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"data: {serialized}\n\n"
