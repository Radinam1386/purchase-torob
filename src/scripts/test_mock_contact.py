"""Run with python -m src.scripts.test_mock_contact; no model or phone credentials needed."""

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api import app
from src.core.config import settings
from src.core.tools.shops import get_inquiry_status, list_inquiries
from src.scripts.load_data import SCHEMA, _preserve_user_data


class MockContactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.sqlite"
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.executescript(SCHEMA)
            for product_id, category in [("p0", "هدفون"), ("p1", "هدفون"), ("p2", "تنها"), ("p3", "بی‌قیمت")]:
                connection.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)",
                    (product_id, "محصول " + product_id, product_id, None, "برند", category, category, "[]", "[]"))
            for shop_id in ("s0", "s1"):
                connection.execute("INSERT INTO shops VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (shop_id, "نام ناشناس مخفی", 0, None, None, 35.7, 51.4, "تهران", None, None, None, "تهران", "[]", "[]", 0, "{}"))
            connection.executemany("INSERT INTO offers VALUES (?,?,?,?,?,?,?)", [
                ("o0", "s0", "p0", 1000, None, None, None),
                ("o1", "s1", "p1", 900, None, None, None),
                ("o2", "s0", "p2", 2000, None, None, None),
                ("o3", "s0", "p3", None, None, None, None),
            ])
        self.patcher = patch("src.core.database.settings", replace(settings, database_path=self.db))
        self.patcher.start()
        self.client = TestClient(app)
        self.other = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.other.close()
        self.patcher.stop()
        self.temp.cleanup()

    def create(self, scenario="confirmed", offer_id="o0", **extra):
        response = self.client.post("/api/mock-calls", json={"offerId": offer_id, "scenario": scenario, **extra})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["run"]

    def test_all_scenarios_persist_without_network_or_offer_mutations(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            before = connection.execute("SELECT * FROM offers ORDER BY id").fetchall()
        with patch("socket.create_connection", side_effect=AssertionError("No external contact in Mock")), patch("src.api._agent", side_effect=AssertionError("No LLM in Mock")):
            runs = [self.create(scenario) for scenario in ["confirmed", "price_changed", "out_of_stock", "needs_review", "no_answer", "alternative"]]
        self.assertEqual([run["status"] for run in runs], ["completed", "completed", "completed", "needs_review", "no_answer", "completed"])
        self.assertEqual(runs[0]["simulatedPrice"], 1000)
        self.assertEqual(runs[1]["simulatedPrice"], 1050)
        self.assertEqual(runs[1]["priceDifference"], 50)
        self.assertIs(runs[2]["simulatedInStock"], False)
        self.assertIsNone(runs[4]["simulatedInStock"])
        self.assertIsNone(runs[4]["simulatedPrice"])
        self.assertEqual(runs[5]["alternatives"][0]["offer"]["id"], "o1")
        for run in runs:
            self.assertEqual(run["source"], "simulated")
            self.assertEqual(run["provider"], "mock")
            self.assertEqual(run["datasetOffer"]["stock"], "unverified")
            self.assertEqual([stage["id"] for stage in run["stages"]], ["prepared", "started", "requested", "responded", "analysis", "saved"])
            self.assertIn("عامل تحلیل", run["transcript"][-1]["text"])
            self.assertTrue(run["limitation"])
            self.assertIn("شبیه", run["analysis"])
            self.assertEqual(self.client.get("/api/mock-calls/" + run["id"]).json()["run"], run)
        self.assertEqual(self.client.get("/api/mock-calls?page=1&page_size=4").json()["total"], 6)
        self.assertEqual(len(self.client.get("/api/mock-calls?page=2&page_size=4").json()["data"]), 2)
        with TestClient(app) as reopened:
            reopened.cookies.set("torob_session", self.client.cookies["torob_session"])
            self.assertEqual(reopened.get("/api/mock-calls").json()["total"], 6)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("SELECT * FROM offers ORDER BY id").fetchall(), before)

    def test_cookie_selection_masking_and_history_isolation(self):
        response = self.client.get("/api/contact/selection?offer_id=o0")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        selection = response.json()
        self.assertEqual(selection["source"], "dataset")
        self.assertEqual(selection["shop"]["displayName"], "فروشگاه #s0")
        self.assertNotIn("نام ناشناس مخفی", json.dumps(selection, ensure_ascii=False))
        self.assertNotIn("phone", json.dumps(selection))
        run = self.create()
        self.assertEqual(self.other.get("/api/mock-calls").json()["total"], 0)
        self.assertEqual(self.other.get("/api/mock-calls/" + run["id"]).status_code, 404)
        self.assertEqual(self.other.get("/api/inquiries/" + run["id"]).status_code, 404)
        self.assertEqual(self.other.get("/api/inquiries").json()["inquiries"], [])
        self.assertEqual(self.other.post("/api/inquiries/" + run["id"] + "/seller-reply", json={"action": "out_of_stock"}).status_code, 404)
        self.assertEqual(list_inquiries.invoke({})["data"], [])
        with self.assertRaises(ValueError):
            get_inquiry_status.invoke({"inquiry_id": run["id"]})
        self.assertEqual(self.client.get("/api/mock-calls/" + run["id"]).json()["run"], run)

    def test_missing_price_alternative_absence_and_validation(self):
        run = self.create("confirmed", "o3")
        self.assertEqual(run["status"], "needs_review")
        self.assertIsNone(run["simulatedPrice"])
        self.assertIsNone(run["priceDifference"])
        self.assertEqual(self.create("alternative", "o2")["alternatives"], [])
        self.assertEqual(self.create("price_changed", newPrice=1234)["simulatedPrice"], 1234)
        for body in [{"offerId": "o0", "scenario": "confirmed", "newPrice": 1234},
                     {"offerId": "o0", "scenario": "price_changed", "newPrice": 1000},
                     {"offerId": "o0", "scenario": "price_changed", "newPrice": -1},
                     {"offerId": "o0", "scenario": "unsupported"},
                     {"offerId": "o0", "scenario": "confirmed", "shopId": "s1"}]:
            self.assertEqual(self.client.post("/api/mock-calls", json=body).status_code, 422, body)
        self.assertEqual(self.client.post("/api/mock-calls", json={"offerId": "missing", "scenario": "confirmed"}).status_code, 404)
        self.assertEqual(self.client.get("/api/contact/selection?offer_id=missing").status_code, 404)
        first = self.create(runKey="same-request")
        self.assertEqual(first, self.create(runKey="same-request"))
        self.assertEqual(self.client.post("/api/mock-calls", json={"offerId": "o0", "scenario": "no_answer", "runKey": "same-request"}).status_code, 422)

    def test_real_buyer_reports_are_distinct_scoped_and_validate_actual_contact_time(self):
        self.create()
        report = {"productId": "p0", "shopId": "s0", "offerId": "o0", "outcome": "confirmed",
                  "reportedPrice": 1100, "inStock": True, "method": "phone", "observedAt": "2026-01-01T12:30:00+03:30"}
        saved = self.client.post("/api/price-checks", json=report)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["source"], "buyer_report")
        self.assertEqual(saved.json()["observedAt"], "2026-01-01T09:00:00+00:00")
        self.assertNotEqual(saved.json()["checkedAt"], saved.json()["observedAt"])
        checks = self.client.get("/api/price-checks").json()["checks"]
        self.assertEqual(len(checks), 1)
        self.assertIs(checks[0]["inStock"], True)
        self.assertEqual(self.other.get("/api/price-checks").json()["checks"], [])
        self.assertEqual(self.client.get("/api/mock-calls").json()["total"], 1)
        for extra in [{"observedAt": "bad"}, {"observedAt": "2999-01-01T00:00:00Z"},
                      {"observedAt": "2026-01-01T12:30:00"}, {"inStock": "unknown"}, {"shopId": "s1"}]:
            response = self.client.post("/api/price-checks", json={**report, **extra})
            self.assertIn(response.status_code, (404, 422), response.text)
        unknown = self.client.post("/api/price-checks", json={**report, "outcome": "unclear", "inStock": None, "reportedPrice": None})
        self.assertEqual(unknown.status_code, 200, unknown.text)
        self.assertIsNone(unknown.json()["inStock"])

    def test_legacy_unowned_reports_remain_private_after_migration(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("""CREATE TABLE price_checks (id TEXT PRIMARY KEY,product_id TEXT,shop_id TEXT,offer_id TEXT,outcome TEXT,
                reported_price INTEGER,method TEXT,note TEXT,source TEXT,checked_at TEXT)""")
            connection.execute("INSERT INTO price_checks VALUES ('old','p0','s0','o0','confirmed',1,'phone',NULL,'buyer_report','2026-01-01')")
        self.assertEqual(self.client.get("/api/price-checks").json()["checks"], [])
        response = self.client.post("/api/price-checks", json={"productId": "p0", "shopId": "s0", "offerId": "o0", "outcome": "unclear", "method": "phone"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.client.get("/api/price-checks").json()["checks"]), 1)
        self.assertEqual(self.other.get("/api/price-checks").json()["checks"], [])

    def test_reported_price_is_a_storage_safe_positive_integer(self):
        report = {"productId": "p0", "shopId": "s0", "offerId": "o0", "outcome": "unclear", "method": "visit"}
        for value in (9223372036854775808, 9_000_000_000_000_001, True, 12.5, "100", -1, 0):
            response = self.client.post("/api/price-checks", json={**report, "reportedPrice": value})
            self.assertEqual(response.status_code, 422, response.text)

    def test_missing_observation_time_is_not_invented(self):
        response = self.client.post("/api/price-checks", json={"productId": "p0", "shopId": "s0", "offerId": "o0", "outcome": "unclear", "method": "visit"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["observedAt"])
        self.assertTrue(response.json()["checkedAt"])

    def test_dataset_reload_preserves_mock_and_real_report_history(self):
        run = self.create()
        response = self.client.post("/api/price-checks", json={"productId": "p0", "shopId": "s0", "offerId": "o0", "outcome": "unclear", "method": "visit"})
        self.assertEqual(response.status_code, 200, response.text)
        replacement = Path(self.temp.name) / "replacement.sqlite"
        with closing(sqlite3.connect(replacement)) as connection, connection:
            connection.executescript(SCHEMA)
            _preserve_user_data(connection, self.db)
            self.assertEqual(json.loads(connection.execute("SELECT payload_json FROM inquiries WHERE id=?", (run["id"],)).fetchone()[0]), run)
            owner = connection.execute("SELECT session_id FROM price_checks WHERE id=?", (response.json()["id"],)).fetchone()[0]
            self.assertEqual(owner, self.client.cookies["torob_session"])


if __name__ == "__main__":
    unittest.main()
