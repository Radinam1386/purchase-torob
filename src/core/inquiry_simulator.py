"""Seller simulator engine for in-person shopping inquiries.

Simulates structured, low-friction inquiries ('Let Google Call' style)
with realistic shop personas, channels (panel, sms, chat, ai_call),
deterministic seeds, lifecycle transitions, and batch cancellation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.contract import (
    Inquiry,
    InquiryAnswer,
    InquiryChannel,
    InquiryPersona,
    InquiryRequestDetails,
    InquiryStatus,
    InquiryTimelineStep,
)
from src.core.database import database
from src.core.text import parse_json
from src.core.tools.common import _is_open_at, is_open_now


CHANNEL_ESCALATION: dict[InquiryChannel, InquiryChannel | None] = {
    "panel": "sms",
    "sms": "chat",
    "chat": "ai_call",
    "ai_call": None,
}

TIMELINE_STAGE_LABELS: dict[InquiryStatus, str] = {
    "draft": "پیش‌نویس پیام",
    "sent": "ارسال شد",
    "delivered": "تحویل به فروشگاه",
    "read": "دیده شد توسط فروشنده",
    "answered": "پاسخ دریافت شد",
    "no_answer": "منقضی / بی‌پاسخ",
    "cancelled": "لغو شد",
}


def choose_default_channel(shop_row: Any) -> InquiryChannel:
    """Select appropriate communication channel based on shop attributes."""
    if not shop_row:
        return "panel"
    website = shop_row["website"] if "website" in shop_row.keys() else None
    instagram = shop_row["instagram"] if "instagram" in shop_row.keys() else None
    if website:
        return "panel"
    if instagram:
        return "chat"
    return "sms"


def determine_persona(
    shop_id: str,
    product_id: str,
    *,
    is_closed: bool = False,
    override_persona: str | None = None,
) -> InquiryPersona:
    """Determine deterministic persona for reproducible demos and tests."""
    if override_persona in {"fast_accurate", "slow", "busy_no_answer", "price_changed", "out_of_stock", "closed"}:
        return override_persona  # type: ignore[return-value]
    if is_closed:
        return "closed"

    digest = hashlib.sha256(f"{shop_id}:{product_id}".encode()).hexdigest()
    outcome = int(digest[:8], 16) % 5
    mapping: dict[int, InquiryPersona] = {
        0: "fast_accurate",
        1: "slow",
        2: "price_changed",
        3: "out_of_stock",
        4: "busy_no_answer",
    }
    return mapping.get(outcome, "fast_accurate")


def check_shop_open_at_eta(weekly_hours_raw: str | None, eta_minutes: int | None = None) -> bool | None:
    """Check if shop will be open at the user's estimated arrival time."""
    hours = parse_json(weekly_hours_raw)
    if not isinstance(hours, dict):
        return None
    tehran = ZoneInfo(settings.timezone)
    target_time = datetime.now(tehran)
    if eta_minutes and eta_minutes > 0:
        target_time += timedelta(minutes=eta_minutes)
    return _is_open_at(hours, target_time)


def build_draft_message(
    product_title: str,
    price: int | None,
    requests: InquiryRequestDetails,
    shop_display_name: str,
) -> str:
    """Build short, polite, structured Persian draft message."""
    parts = ["سلام وقت‌بخیر از طرف خریدار ترب حضوری."]
    item_desc = product_title
    if requests.size_or_color:
        item_desc += f" (مدل/رنگ/سایز: {requests.size_or_color})"
    if requests.quantity > 1:
        item_desc += f" به تعداد {requests.quantity} عدد"

    parts.append(f"آیا کالا «{item_desc}» در فروشگاه موجود است؟")
    if price:
        parts.append(f"قیمت ثبت‌شده در ترب {price:,} تومان است، آیا قیمت امروز تأیید می‌شود؟")
    else:
        parts.append("قیمت امروز چقدر است؟")

    if requests.eta_minutes:
        parts.append(f"مشتری تا حدود {requests.eta_minutes} دقیقه دیگر به فروشگاه می‌رسد.")
    if requests.hold_requested:
        parts.append("در صورت موجودی، لطفاً تا زمان رسیدن کالا رزرو بماند.")

    return " ".join(parts)


def generate_ai_call_transcript(
    shop_display_name: str,
    product_title: str,
    persona: InquiryPersona,
    price: int | None,
) -> str:
    """Generate structured, polite mock transcript for AI call channel."""
    lines = [
        f"🤖 تماس هوشمند با {shop_display_name} (شبیه‌سازی‌شده):",
        "دستیار هوشمند ترب: «سلام، وقت‌بخیر. تماس کوتاه از طرف خریدار ترب برای استعلام موجودی حضوری.»",
        f"دستیار: «آیا {product_title} موجود هست و قیمت روز چنده؟»",
    ]
    if persona == "out_of_stock":
        lines.append("فروشنده: «سلام، متأسفانه این مدل تموم شده و موجود نداریم.»")
        lines.append("دستیار: «متشکرم، عدم موجودی ثبت شد. روز خوبی داشته باشید.»")
    elif persona == "price_changed" and price:
        new_price = round(price * 1.05)
        lines.append(f"فروشنده: «سلام، بله یک عدد موجوده، اما قیمت امروز {new_price:,} تومان شده.»")
        lines.append(f"دستیار: «قیمت جدید {new_price:,} تومان ثبت و به خریدار اطلاع داده شد. ممنون.»")
    elif persona == "closed":
        lines.append("سیستم تلفن: «فروشگاه در حال حاضر خارج از ساعت کاری است و پاسخ‌گو نیست.»")
    elif persona == "busy_no_answer":
        lines.append("سیستم تلفن: «خط فروشگاه مشغول است و پس از ۳ بار زنگ پاسخی دریافت نشد.»")
    else:
        display_price = f"{price:,} تومان" if price else "طبق نرخ اعلامی"
        lines.append(f"فروشنده: «سلام، بله موجوده و با قیمت {display_price} تقدیم می‌کنیم.»")
        lines.append("دستیار: «بسیار عالی، به خریدار اطلاع دادم تا برای خرید حضوری مراجعه کنند.»")
    return "\n".join(lines)


def build_timeline(
    status: InquiryStatus,
    created_at: str,
    sent_at: str | None = None,
    delivered_at: str | None = None,
    read_at: str | None = None,
    answered_at: str | None = None,
) -> list[InquiryTimelineStep]:
    """Assemble chronological timeline steps for the inquiry."""
    terminal_stage: InquiryStatus = (
        "answered" if status == "answered"
        else "no_answer" if status == "no_answer"
        else "cancelled" if status == "cancelled"
        else "answered"
    )
    stages: list[tuple[InquiryStatus, str | None]] = [
        ("draft", created_at),
        ("sent", sent_at),
        ("delivered", delivered_at),
        ("read", read_at),
        (terminal_stage, answered_at),
    ]

    timeline: list[InquiryTimelineStep] = []
    has_active_terminal = status in {"answered", "no_answer", "cancelled"}

    for stage_name, ts in stages:
        completed = ts is not None or (has_active_terminal and stage_name == terminal_stage)
        step = InquiryTimelineStep(
            stage=stage_name,
            label=TIMELINE_STAGE_LABELS.get(stage_name, stage_name),
            timestamp=ts,
            completed=completed,
        )
        timeline.append(step)
    return timeline


def simulate_seller_response(
    inquiry_record: dict[str, Any],
    offer_price: int | None,
    *,
    shop_name: str = "فروشگاه",
    product_title: str = "کالا",
) -> dict[str, Any]:
    """Simulate realistic seller response based on persona and channel."""
    persona: InquiryPersona = inquiry_record.get("persona") or "fast_accurate"
    channel: InquiryChannel = inquiry_record.get("channel") or "panel"
    now_utc = datetime.now(timezone.utc)

    created_at = inquiry_record.get("created_at") or now_utc.isoformat()
    sent_at = inquiry_record.get("sent_at") or (now_utc + timedelta(seconds=1)).isoformat()
    delivered_at = (now_utc + timedelta(seconds=2)).isoformat()
    read_at = (now_utc + timedelta(seconds=4)).isoformat()
    answered_at = (now_utc + timedelta(seconds=6)).isoformat()

    transcript = None
    if channel == "ai_call":
        transcript = generate_ai_call_transcript(shop_name, product_title, persona, offer_price)

    if persona == "closed":
        status: InquiryStatus = "no_answer"
        answer = InquiryAnswer(
            in_stock=False,
            price=None,
            note="فروشگاه در حال حاضر بسته است و پاسخی ثبت نشد.",
            transcript=transcript,
        )
    elif persona == "busy_no_answer":
        status = "no_answer"
        answer = InquiryAnswer(
            in_stock=False,
            price=None,
            note="مهلت پاسخ‌گویی به پایان رسید؛ فروشنده پاسخ نداد.",
            transcript=transcript,
        )
    elif persona == "out_of_stock":
        status = "answered"
        answer = InquiryAnswer(
            in_stock=False,
            price=None,
            note="فروشنده اعلام کرد این کالا در حال حاضر ناموجود است.",
            transcript=transcript,
        )
    elif persona == "price_changed":
        status = "answered"
        new_price = round(offer_price * 1.05) if offer_price else None
        answer = InquiryAnswer(
            in_stock=True,
            price=new_price,
            note="فروشنده اعلام کرد کالا موجود است، اما قیمت روز ۵٪ بیشتر از قیمت ثبت‌شده است.",
            transcript=transcript,
        )
    else:  # fast_accurate or slow
        status = "answered"
        answer = InquiryAnswer(
            in_stock=True,
            price=offer_price,
            note="فروشنده موجودی و قیمت ثبت‌شده را تأیید کرد.",
            transcript=transcript,
        )

    timeline = build_timeline(status, created_at, sent_at, delivered_at, read_at, answered_at)

    result = {
        **inquiry_record,
        "status": status,
        "delivered_at": delivered_at,
        "read_at": read_at,
        "answered_at": answered_at,
        "answer": answer.model_dump(mode="json", by_alias=True),
        "timeline": [t.model_dump(mode="json", by_alias=True) for t in timeline],
    }
    return result


def handle_batch_completion(connection: Any, batch_id: str, winning_inquiry_id: str) -> None:
    """When one batch inquiry succeeds positively, auto-cancel the rest."""
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = connection.execute(
        "SELECT id, status FROM inquiries WHERE batch_id = ? AND id != ?",
        (batch_id, winning_inquiry_id),
    ).fetchall()

    for row in rows:
        if row["status"] in {"draft", "sent", "delivered", "read"}:
            answer = {
                "in_stock": False,
                "price": None,
                "note": "به دلیل دریافت پاسخ مثبت از فروشگاه دیگر، این استعلام به صورت خودکار لغو شد.",
            }
            connection.execute(
                """
                UPDATE inquiries
                SET status = 'cancelled', answer_json = ?, answered_at = ?
                WHERE id = ?
                """,
                (json.dumps(answer, ensure_ascii=False), now_iso, row["id"]),
            )
