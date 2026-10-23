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


class PurchaseRegressionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
