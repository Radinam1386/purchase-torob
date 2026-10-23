"""Regression checks for purchase paths covered by the 53ee66d audit."""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.contract import ConversationState
from src.core.tools.catalog import search_products
from src.core.tools.common import (
    supports_in_person_installments,
    supports_tarob_pay_in_person,
    _is_open_at,
)
from src.core.tools.shops import compare_shops
from src.core.agent import _apply_constraints, _needs_clarification
from src.core.response import _alternative_options
from src.core.database import database
from langchain_core.messages import HumanMessage
from src.core.agent import ShoppingAgent


class PurchaseRegressionTests(unittest.TestCase):
    def test_model_json_after_intro_is_not_exposed_in_chat(self):
        from src.core.response import response_from_messages
        from langchain_core.messages import AIMessage
        question = "چه نوع جاروبرقی و چه بودجه‌ای مدنظرت است؟"
        payload = json.dumps({'text': question, 'clarificationQuestion': question}, ensure_ascii=False)
        response = response_from_messages([AIMessage(content=question + '\n' + payload)])
        self.assertEqual(response.text, question)
        self.assertEqual(response.clarification_question, question)

    def test_plain_and_fenced_model_responses_remain_readable(self):
        from src.core.response import parse_model_text
        self.assertEqual(parse_model_text('سلام، چه محصولی می‌خواهی؟'), ('سلام، چه محصولی می‌خواهی؟', None))
        self.assertEqual(parse_model_text('```json\n{"text":"سلام","clarificationQuestion":"بودجه؟"}\n```'), ('سلام', 'بودجه؟'))

    def test_advisor_collects_budget_after_usage_answer(self) -> None:
        initial = ShoppingAgent._advisor_gate({
            "messages": [HumanMessage(content="هدفون می‌خوام")], "conversation": {},
        })
        self.assertIn("بودجه", initial["clarification_question"])
        followup = ShoppingAgent._advisor_gate({
            "messages": [HumanMessage(content="هدفون می‌خوام"), HumanMessage(content="برای موزیک")],
            "conversation": initial["conversation"],
        })
        self.assertIn("بودجه", followup["clarification_question"])

    def test_advisor_summarizes_before_search_when_budget_and_use_are_known(self) -> None:
        result = ShoppingAgent._advisor_gate({
            "messages": [HumanMessage(content="هدفون برای موزیک تا ۵ میلیون تومان")],
            "conversation": {},
        })
        self.assertIn("خلاصه ترجیحات", result["clarification_question"])
        confirmed = ShoppingAgent._advisor_gate({
            "messages": [HumanMessage(content="بله")], "conversation": result["conversation"],
        })
        self.assertNotIn("clarification_question", confirmed)

    def test_persian_decimal_budget_and_installment_negation(self) -> None:
        state = ConversationState()

        _apply_constraints(state, "بودجه ۲٫۵ میلیون، قسطی نمی‌خوام")

        self.assertEqual(state.budget, 2_500_000)
        self.assertFalse(state.filters.installment)

    def test_malformed_radius_is_ignored(self) -> None:
        state = ConversationState(radius_km=4)

        _apply_constraints(state, "شعاع ۲..۳")

        self.assertEqual(state.radius_km, 4)

    def test_named_phone_model_does_not_trigger_clarification(self) -> None:
        self.assertFalse(_needs_clarification("گوشی سامسونگ S24 FE", {}))

    def test_broad_phone_request_triggers_one_clarification(self) -> None:
        self.assertTrue(_needs_clarification("گوشی می‌خوام", {}))
        self.assertFalse(
            _needs_clarification("گوشی می‌خوام", {"selectedProductId": "product-1"})
        )

    def test_unknown_payment_is_not_reported_as_negative(self) -> None:
        self.assertIsNone(supports_in_person_installments(None))
        self.assertIsNone(supports_tarob_pay_in_person("null"))
        self.assertFalse(supports_in_person_installments("[]"))
        self.assertTrue(
            supports_in_person_installments('[{"channel":"in_person"}]')
        )

    def test_overnight_hours_include_previous_day_shift(self) -> None:
        tehran = ZoneInfo("Asia/Tehran")
        now = datetime(2026, 10, 27, 1, 0, tzinfo=tehran)  # Tuesday
        hours = {
            "mon": {"status": "declared", "shifts": [
                {"start_time": "22:00", "end_time": "02:00"}
            ]},
            "tue": {"status": "closed", "shifts": []},
        }

        self.assertTrue(_is_open_at(hours, now))

    def test_alternative_results_stay_with_their_product(self) -> None:
        product_one = {"id": "p1", "titleFa": "محصول اول"}
        product_two = {"id": "p2", "titleFa": "محصول دوم"}
        result_one = {"offer": {"productId": "p1", "price": 10}, "distanceKm": 1}
        result_two = {"offer": {"productId": "p2", "price": 20}, "distanceKm": 2}

        options = _alternative_options({
            "products": [product_one, product_two],
            "results": [result_one, result_two],
        })

        self.assertEqual([option["product"]["id"] for option in options], ["p1", "p2"])
        self.assertEqual(options[0]["results"][0]["offer"]["productId"], "p1")
        self.assertEqual(options[1]["results"][0]["offer"]["productId"], "p2")

    def test_real_dataset_finds_samsung_s24_fe_and_offers(self) -> None:
        result = search_products.invoke({"query": "گوشی سامسونگ S24 FE", "limit": 5})
        if isinstance(result, str):
            result = json.loads(result)
        products = result["data"]

        self.assertTrue(products, "دیتاست محلی باید مدل S24 FE را پیدا کند")
        selected = next(
            (product for product in products if "s24" in product["titleFa"].lower().replace(" ", "")),
            products[0],
        )
        with database(readonly=True) as connection:
            offers = connection.execute(
                "SELECT COUNT(*) FROM offers WHERE product_id = ?", (selected["id"],)
            ).fetchone()[0]
        self.assertGreaterEqual(offers, 5)

    def test_compare_keeps_the_selected_offer_identity(self) -> None:
        with database(readonly=True) as connection:
            row = connection.execute(
                """
                SELECT product_id, shop_id, MIN(id) AS offer_id
                FROM offers
                GROUP BY product_id, shop_id
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(row, "دیتاست برای آزمون باید آفرهای تکراری داشته باشد")

        result = compare_shops.invoke({
            "product_id": row["product_id"],
            "offer_ids": [row["offer_id"]],
            "lat": 35.7219,
            "lng": 51.4097,
        })

        self.assertEqual([item["offer"]["id"] for item in result["data"]], [row["offer_id"]])

    def test_inquiry_cannot_be_sent_without_explicit_confirmation(self) -> None:
        from src.core.tools.shops import draft_inquiry, send_inquiry
        with database(readonly=True) as connection:
            row = connection.execute(
                "SELECT product_id, shop_id, id AS offer_id FROM offers LIMIT 1"
            ).fetchone()

        draft = draft_inquiry.invoke({
            "product_id": row["product_id"],
            "shop_id": row["shop_id"],
            "offer_id": row["offer_id"],
        })
        inquiry_id = draft["data"]["inquiry_id"]

        with self.assertRaises(ValueError) as ctx:
            send_inquiry.invoke({"inquiry_id": inquiry_id, "confirmed": False})
        self.assertIn("تأیید صریح کاربر", str(ctx.exception))

    def test_inquiry_lifecycle_and_timeline(self) -> None:
        from src.core.tools.shops import draft_inquiry, send_inquiry
        with database(readonly=True) as connection:
            row = connection.execute(
                "SELECT product_id, shop_id, id AS offer_id FROM offers LIMIT 1"
            ).fetchone()

        draft = draft_inquiry.invoke({
            "product_id": row["product_id"],
            "shop_id": row["shop_id"],
            "offer_id": row["offer_id"],
            "hold_requested": True,
            "eta_minutes": 25,
        })
        inquiry_id = draft["data"]["inquiry_id"]
        self.assertEqual(draft["data"]["kind"], "message_draft")
        self.assertIn(draft["data"]["channel"], {"panel", "sms", "chat", "ai_call"})

        sent = send_inquiry.invoke({
            "inquiry_id": inquiry_id,
            "confirmed": True,
        })
        inquiry_data = sent["data"]["inquiry"]
        self.assertIn(inquiry_data["status"], {"answered", "no_answer"})
        self.assertTrue(len(inquiry_data["timeline"]) >= 3)
        stages = [step["stage"] for step in inquiry_data["timeline"]]
        self.assertEqual(stages[0], "draft")
        self.assertEqual(stages[1], "sent")
        self.assertEqual(stages[2], "delivered")

    def test_batch_inquiry_and_auto_cancellation(self) -> None:
        from src.core.tools.shops import send_inquiry_batch
        with database(readonly=True) as connection:
            rows = connection.execute(
                """
                SELECT product_id, shop_id, id AS offer_id
                FROM offers
                GROUP BY product_id
                HAVING COUNT(DISTINCT shop_id) >= 2
                LIMIT 1
                """
            ).fetchone()
            product_id = rows["product_id"]
            shop_rows = connection.execute(
                "SELECT shop_id, id AS offer_id FROM offers WHERE product_id = ? LIMIT 3",
                (product_id,),
            ).fetchall()

        shop_ids = [r["shop_id"] for r in shop_rows]

        result = send_inquiry_batch.invoke({
            "product_id": product_id,
            "shop_ids": shop_ids,
            "confirmed": True,
        })
        self.assertEqual(result["data"]["kind"], "inquiry_batch")
        items = result["data"]["items"]
        self.assertEqual(len(items), len(shop_ids))
        # If any item was answered in stock, remaining items must be cancelled
        answered_in_stock = any(it["status"] == "answered" and it.get("answer", {}).get("inStock") for it in items)
        if answered_in_stock:
            cancelled_items = [it for it in items if it["status"] == "cancelled"]
            self.assertTrue(len(cancelled_items) >= 1)

    def test_eta_opening_hours_check(self) -> None:
        from src.core.inquiry_simulator import check_shop_open_at_eta
        hours_str = json.dumps({
            "mon": {"status": "declared", "shifts": [{"start_time": "09:00", "end_time": "18:00"}]},
            "tue": {"status": "declared", "shifts": [{"start_time": "09:00", "end_time": "18:00"}]},
            "wed": {"status": "declared", "shifts": [{"start_time": "09:00", "end_time": "18:00"}]},
            "thu": {"status": "declared", "shifts": [{"start_time": "09:00", "end_time": "18:00"}]},
            "fri": {"status": "closed", "shifts": []},
            "sat": {"status": "declared", "shifts": [{"start_time": "09:00", "end_time": "18:00"}]},
            "sun": {"status": "declared", "shifts": [{"start_time": "09:00", "end_time": "18:00"}]},
        })
        res = check_shop_open_at_eta(hours_str, eta_minutes=30)
        self.assertIn(res, {True, False})
        self.assertIsNone(check_shop_open_at_eta(None, eta_minutes=30))

    def test_price_freshness_calculation(self) -> None:
        from src.core.tools.common import calculate_price_freshness
        from datetime import datetime, timezone, timedelta

        now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        fresh_time = (now - timedelta(days=1)).isoformat()
        moderate_time = (now - timedelta(days=5)).isoformat()
        stale_time = (now - timedelta(days=20)).isoformat()

        self.assertEqual(calculate_price_freshness(fresh_time, now=now).level, "fresh")
        self.assertEqual(calculate_price_freshness(moderate_time, now=now).level, "moderate")
        self.assertEqual(calculate_price_freshness(stale_time, now=now).level, "stale")

    def test_dataset_price_remains_untouched_after_inquiry(self) -> None:
        from src.core.tools.shops import draft_inquiry, send_inquiry
        with database(readonly=True) as connection:
            offer = connection.execute("SELECT id, product_id, shop_id, price FROM offers LIMIT 1").fetchone()
        orig_price = offer["price"]

        draft = draft_inquiry.invoke({
            "product_id": offer["product_id"],
            "shop_id": offer["shop_id"],
            "offer_id": offer["id"],
        })
        sent = send_inquiry.invoke({
            "inquiry_id": draft["data"]["inquiry_id"],
            "confirmed": True,
        })
        # Verify in DB that offers.price is unchanged
        with database(readonly=True) as connection:
            current_offer = connection.execute("SELECT price FROM offers WHERE id = ?", (offer["id"],)).fetchone()
        self.assertEqual(current_offer["price"], orig_price)


if __name__ == "__main__":
    unittest.main()
