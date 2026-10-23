"""Run real-model conversation scenarios and enforce data transparency rules."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.agent import ShoppingAgent
from src.core.config import PROJECT_ROOT, settings
from src.core.contract import AssistantCard, ConversationState, ShopResult


def load_scenarios() -> list[dict[str, Any]]:
    scenario_file = PROJECT_ROOT / "evals" / "scenarios.json"
    return json.loads(scenario_file.read_text(encoding="utf-8"))


async def run_scenario(agent: ShoppingAgent, scenario: dict[str, Any]) -> dict[str, Any]:
    called_tools: list[str] = []

    def observe(event) -> None:
        if event.type == "tool_start" and event.name:
            called_tools.append(event.name)

    started = asyncio.get_running_loop().time()
    try:
        response = await agent.run(
            scenario["prompt"],
            user_id=f"eval-{scenario['id']}",
            conversation=agent.initial_state(),
            on_event=observe,
        )
        errors = validate_response(scenario, called_tools, response.cards, response.text)
        return {
            "id": scenario["id"],
            "title": scenario["title"],
            "status": "FAIL" if errors else "PASS",
            "durationMs": round((asyncio.get_running_loop().time() - started) * 1000),
            "tools": called_tools,
            "cards": [card.kind for card in response.cards],
            "errors": errors,
            "text": response.text,
        }
    except Exception as error:
        return {
            "id": scenario["id"],
            "title": scenario["title"],
            "status": "ERROR",
            "durationMs": round((asyncio.get_running_loop().time() - started) * 1000),
            "tools": called_tools,
            "cards": [],
            "errors": [str(error)],
        }


def validate_response(scenario, called_tools, cards, text: str) -> list[str]:
    errors = []
    missing_tools = set(scenario["expect_tools"]) - set(called_tools)
    if missing_tools:
        errors.append(f"ابزار مورد انتظار اجرا نشد: {', '.join(sorted(missing_tools))}")
    for card in cards:
        errors.extend(_validate_card(card))
    if re.search(r"[⭐★]{2,}|\b[45]\.\d\s*(?:از|/)", text):
        errors.append("احتمال نمایش امتیاز یا نظر ساختگی")
    if (text.count("?") + text.count("؟")) > 1:
        errors.append("بیش از یک سؤال شفاف‌ساز")
    errors.extend(_validate_advisory(scenario.get("advisory", {}), cards, text))
    return errors


def _validate_advisory(criteria: dict[str, Any], cards, text: str) -> list[str]:
    errors = []
    questions = text.count("?") + text.count("؟")
    asks_for_missing_need = bool(questions and re.search(
        r"(?:حدود|میزان|سقف)\s*بودجه|برای چه کاری|چه کاربردی|چه مدل(?:ی)?|"
        r"کدام ویژگی|چه ویژگی|روزمره.*ورزش|ورزش.*روزمره",
        text,
    ))
    if criteria.get("clarification") == "required" and (questions != 1 or not asks_for_missing_need):
        errors.append("معیار مشاوره: برای ابهام باید دقیقاً یک سؤال هدفمند بپرسد")
    if criteria.get("clarification") == "forbidden" and asks_for_missing_need:
        errors.append("معیار مشاوره: با اطلاعات کافی سؤال بیجا پرسیده است")

    if criteria.get("reason") and not re.search(
        r"چون|به‌خاطر|به دلیل|به‌دلیل|کمترین|نزدیک‌ترین|ارزان‌تر|گرچه|اما|در عوض|"
        r"سقف|فقط یک|بسته|ساعت ثبت|فاصله|در دیتاست|پوشش|فیلتر|آفر پیدا نشد|ثبت نشده|"
        r"نتیجه‌ی مرتبط|نتیجه‌ای نداشت|جست‌وجو.*نتیجه",
        text,
    ):
        errors.append("معیار مشاوره: دلیل انتخاب یا مبادله را نگفته است")

    if criteria.get("next_step"):
        has_clear_next_step = re.search(
            r"قدم (?:بعدی|عملی).{0,120}(?:استعلام|مقایسه|جایگزین|شعاع|مسیر|بررسی|انتخاب|"
            r"بپرسم|بگم|بگویید|اصلاح|محدود|افزایش|تغییر|تأیید|دنبال|بگردم|پیگیری|جست‌وجو)",
            text,
        )
        clarification_is_next_step = (
            criteria.get("clarification") == "required"
            and questions == 1
            and asks_for_missing_need
        )
        if not has_clear_next_step and not clarification_is_next_step:
            errors.append("معیار مشاوره: قدم بعدی مشخصی پیشنهاد نشده است")

    if criteria.get("transparency"):
        if any(
            card.kind in {"shop_cards", "compare", "alternatives"}
            and bool(card.results)
            for card in cards
        ):
            if not re.search(r"تأییدنشده|تأیید موجودی نیست|موجودی.*مشخص نیست", text):
                errors.append("معیار شفافیت: وضعیت موجودی تأییدنشده اعلام نشده است")
        if any(card.kind == "inquiry" for card in cards):
            if not re.search(r"نمونه‌سازی|شبیه‌سازی", text):
                errors.append("معیار شفافیت: شبیه‌سازی بودن استعلام روشن نیست")
        if any(card.kind == "web_results" for card in cards) and "وب" not in text:
            errors.append("معیار شفافیت: منبع وب مشخص نشده است")

    if criteria.get("in_person_tip") and not re.search(
        r"حضوری|ضمانت|فاکتور|مدل|سریال|IMEI|سایز|روشن|ساعت کاری|کارت بانکی|"
        r"رزوه|قطر|تطبیق|سه‌نظام|پیکسل",
        text,
        re.IGNORECASE,
    ):
        errors.append("معیار مشاوره: نکته‌ی خرید حضوری مرتبط نگفته است")
    return errors


def _validate_card(card: AssistantCard) -> list[str]:
    errors = []
    option_lists = {
        "product_cards": card.products if card.kind == "product_cards" else None,
        "shop_cards": card.results if card.kind == "shop_cards" else None,
        "compare": card.results if card.kind == "compare" else None,
        "alternatives_products": card.products if card.kind == "alternatives" else None,
        "alternatives_results": card.results if card.kind == "alternatives" else None,
        "hub": card.hubs if card.kind == "hub" else None,
        "web": card.results if card.kind == "web_results" else None,
    }
    if any(options is not None and len(options) > 3 for options in option_lists.values()):
        errors.append("بیش از سه گزینه در کارت پیشنهاد شده است")
    if card.kind == "inquiry" and card.source != "simulated":
        errors.append("استعلام باید منبع نمونه‌سازی داشته باشد")
    if card.kind in {"shop_cards", "compare", "alternatives"}:
        for result in card.results:
            errors.extend(_validate_shop_result(result))
    if card.kind == "quick_look" and card.label != "خلاصه هوش مصنوعی":
        errors.append("کارت quick look باید برچسب خلاصه هوش مصنوعی داشته باشد")
    return errors


def _validate_shop_result(result: ShopResult) -> list[str]:
    errors = []
    if result.offer.price <= 0 or not result.offer.price_unit:
        errors.append("قیمت آفر نامعتبر است")
    if result.offer.stock not in {"unverified", "verified_in_stock", "verified_out"}:
        errors.append("وضعیت موجودی از قیمت جدا نیست")
    if not result.shop.has_real_name and not result.shop.display_name.startswith("فروشگاه #"):
        errors.append("نام جعلی فروشگاه به شکل نام واقعی نمایش داده شده")
    if len(result.reasons) != 1 or not result.reasons[0].strip():
        errors.append("هر گزینه باید دقیقاً یک دلیل کوتاه داشته باشد")
    return errors


async def run_evaluations() -> dict[str, Any]:
    agent = ShoppingAgent()
    results = []
    for scenario in load_scenarios():
        result = await run_scenario(agent, scenario)
        results.append(result)
        print(f"{result['status']} {result['id']} ({result['durationMs']}ms)")

    failures = sum(result["status"] != "PASS" for result in results)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "model": settings.llm_model,
        "total": len(results),
        "passed": len(results) - failures,
        "failed": failures,
        "results": results,
    }


def main() -> None:
    report = asyncio.run(run_evaluations())
    results_dir = PROJECT_ROOT / "evals"
    results_dir.mkdir(parents=True, exist_ok=True)
    output_file = results_dir / f"results-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    output_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nنتیجه: {report['passed']}/{report['total']} موفق، {report['failed']} ناموفق.")
    print(f"گزارش: {output_file.relative_to(PROJECT_ROOT)}")
    raise SystemExit(1 if report["failed"] else 0)


if __name__ == "__main__":
    main()
