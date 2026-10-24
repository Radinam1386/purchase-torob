"""Import source CSV files into the SQLite and FTS5 shopping database."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.config import project_path, settings
from src.core.database import database_write_lock
from src.core.market_hubs import MARKET_HUBS
from src.core.text import normalize_fa, parse_address, parse_json


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
DROP TABLE IF EXISTS offers;
DROP TABLE IF EXISTS shops;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS product_fts;
CREATE TABLE products (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, title_norm TEXT NOT NULL,
    model TEXT, brand TEXT, category TEXT, category_norm TEXT, images TEXT, specs TEXT
);
CREATE TABLE shops (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, has_real_name INTEGER NOT NULL,
    instagram TEXT, website TEXT, lat REAL, lng REAL, address TEXT,
    mall TEXT, floor TEXT, unit TEXT, location_label TEXT, categories TEXT,
    payment_options TEXT, fast_delivery INTEGER, weekly_hours TEXT
);
CREATE TABLE offers (
    id TEXT PRIMARY KEY, shop_id TEXT NOT NULL, product_id TEXT NOT NULL,
    price INTEGER, price_updated_at TEXT, warranty TEXT, description TEXT,
    FOREIGN KEY(shop_id) REFERENCES shops(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
);
CREATE INDEX offers_product_idx ON offers(product_id);
CREATE INDEX offers_shop_idx ON offers(shop_id);
CREATE INDEX offers_price_idx ON offers(price);
CREATE VIRTUAL TABLE product_fts USING fts5(
    product_id UNINDEXED, title, brand, category, tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY, preferences_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inquiries (
    id TEXT PRIMARY KEY, session_id TEXT, shop_id TEXT NOT NULL, product_id TEXT NOT NULL,
    offer_id TEXT, channel TEXT NOT NULL DEFAULT 'panel', status TEXT NOT NULL,
    message TEXT, requests_json TEXT, answer_json TEXT, created_at TEXT NOT NULL,
    sent_at TEXT, delivered_at TEXT, read_at TEXT, answered_at TEXT, expires_at TEXT,
    persona TEXT, simulated INTEGER DEFAULT 1, batch_id TEXT, payload_json TEXT
);
CREATE TABLE market_hubs (
    category TEXT NOT NULL, name TEXT NOT NULL, neighborhood TEXT NOT NULL,
    lat REAL NOT NULL, lng REAL NOT NULL, note TEXT NOT NULL,
    coordinate_source TEXT NOT NULL, coordinate_verified INTEGER NOT NULL
);
"""


def load_data() -> dict:
    source_dir = project_path(os.getenv("DATA_DIR", "torob-dataset"))
    if not source_dir.exists():
        raise FileNotFoundError(f"پوشه‌ی دیتاست پیدا نشد: {source_dir}")

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = settings.database_path.with_name(f"{settings.database_path.stem}.staging.sqlite")
    for sidecar in (staging_path, Path(f"{staging_path}-wal"), Path(f"{staging_path}-shm")):
        sidecar.unlink(missing_ok=True)
    connection = sqlite3.connect(staging_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA)
        _seed_market_hubs(connection)
        products = _load_products(connection, source_dir / "products.csv")
        shops = _load_shops(connection, source_dir / "shops.csv")
        offers = _load_offers(connection, source_dir / "offers.csv")
        connection.execute("ANALYZE main")
        report = _quality_report(connection, products, shops, offers)
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()

    with database_write_lock(settings.database_path, exclusive=True):
        connection = sqlite3.connect(staging_path)
        try:
            _preserve_user_data(connection, settings.database_path)
            connection.commit()
            if settings.database_path.exists():
                connection.execute("DETACH DATABASE previous_database")
            connection.execute("ANALYZE main")
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()
        staging_path.replace(settings.database_path)
    report_path = settings.database_path.parent / "quality-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _preserve_user_data(connection: sqlite3.Connection, database_path: Path) -> None:
    """Carry application-owned records into the replacement dataset database."""
    if not database_path.exists():
        return

    connection.execute("ATTACH DATABASE ? AS previous_database", (str(database_path),))
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM previous_database.sqlite_master WHERE type='table'"
        )
    }
    if "user_preferences" in tables:
        connection.execute(
            "INSERT OR REPLACE INTO user_preferences(user_id, preferences_json, updated_at) "
            "SELECT user_id, preferences_json, updated_at FROM previous_database.user_preferences"
        )
    if "inquiries" in tables:
        prev_cols = {
            row[1]
            for row in connection.execute("PRAGMA previous_database.table_info(inquiries)")
        }
        all_cols = (
            "id", "session_id", "shop_id", "product_id", "offer_id",
            "channel", "status", "message", "requests_json", "answer_json",
            "created_at", "sent_at", "delivered_at", "read_at",
            "answered_at", "expires_at", "persona", "simulated",
            "batch_id", "payload_json"
        )
        common_cols = [col for col in all_cols if col in prev_cols]
        if common_cols:
            cols_str = ", ".join(common_cols)
            connection.execute(
                f"INSERT OR REPLACE INTO inquiries({cols_str}) SELECT {cols_str} FROM previous_database.inquiries"
            )


def _seed_market_hubs(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT INTO market_hubs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (*hub[:5], "پیشنهاد مبتنی بر شناخت عمومی بازار", hub[5], int(hub[6]))
            for hub in MARKET_HUBS
        ],
    )


def _load_products(connection: sqlite3.Connection, path: Path) -> int:
    insert_product = "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    insert_fts = "INSERT INTO product_fts VALUES (?, ?, ?, ?)"
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            title = row.get("persian_title") or row.get("model") or ""
            brand = _value(row.get("brand_name"))
            category = _value(row.get("category_name"))
            connection.execute(
                insert_product,
                (
                    row["product_id"], title, normalize_fa(title), _value(row.get("model")),
                    brand, category, normalize_fa(category), row.get("image_urls"), row.get("specs"),
                ),
            )
            connection.execute(
                insert_fts,
                (row["product_id"], normalize_fa(title), normalize_fa(brand), normalize_fa(category)),
            )
            count += 1
            _report_progress("products", count)
    return count


def _load_shops(connection: sqlite3.Connection, path: Path) -> int:
    insert = "INSERT INTO shops VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            website = _value(row.get("website_url"))
            instagram = _value(row.get("instagram"))
            address = _value(row.get("address"))
            parsed = parse_address(address)
            raw_delivery = row.get("supports_fast_delivery")
            delivery = None if raw_delivery in (None, "null", "") else int(raw_delivery == "true")
            connection.execute(
                insert,
                (
                    row["shop_id"], row["name"], int(bool(website or instagram)), instagram,
                    website, _float_or_none(row.get("lat")), _float_or_none(row.get("lon")),
                    address, parsed.mall, parsed.floor, parsed.unit, _value(row.get("location_label")),
                    row.get("category_names"), row.get("payment_options"), delivery,
                    row.get("weekly_hours"),
                ),
            )
            count += 1
            _report_progress("shops", count)
    return count


def _load_offers(connection: sqlite3.Connection, path: Path) -> int:
    insert = "INSERT INTO offers VALUES (?, ?, ?, ?, ?, ?, ?)"
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            price = _int_or_none(row.get("price_toman"))
            if price is not None and price <= 0:
                price = None
            connection.execute(
                insert,
                (
                    row["offer_id"], row["shop_id"], row["product_id"], price,
                    _value(row.get("last_price_changed_at")), row.get("warranty"),
                    row.get("description"),
                ),
            )
            count += 1
            _report_progress("offers", count)
    return count


def _quality_report(connection, product_count: int, shop_count: int, offer_count: int) -> dict:
    shops = connection.execute(
        """
        SELECT COUNT(*) AS total, SUM(has_real_name) AS real_names,
               SUM(lat IS NULL OR lng IS NULL) AS missing_coordinates,
               SUM(mall IS NOT NULL) AS malls, SUM(floor IS NOT NULL) AS floors,
               SUM(unit IS NOT NULL) AS units,
               SUM(fast_delivery IS NULL) AS missing_delivery
        FROM shops
        """
    ).fetchone()
    offers = connection.execute(
        """
        SELECT SUM(price IS NULL) AS missing_prices,
               SUM(price_updated_at IS NULL) AS missing_price_dates,
               MAX(price_updated_at) AS latest_price_update,
               SUM(shop_id NOT IN (SELECT id FROM shops)
                   OR product_id NOT IN (SELECT id FROM products)) AS orphan_offers
        FROM offers
        """
    ).fetchone()
    payment_counts = _payment_quality(connection)
    invalid_specs = sum(
        1 for row in connection.execute("SELECT specs FROM products")
        if row["specs"] and parse_json(row["specs"]) is None
    )
    latest_update = offers["latest_price_update"]
    age_days = None
    if latest_update:
        try:
            age_days = (datetime.now() - datetime.fromisoformat(latest_update.replace("Z", "+00:00")).replace(tzinfo=None)).days
        except ValueError:
            pass

    return {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "database": str(settings.database_path),
        "rows": {"products": product_count, "shops": shop_count, "offers": offer_count},
        "quality": {
            "expectedRealNames": 112,
            "detectedRealNames": shops["real_names"] or 0,
            "missingCoordinates": shops["missing_coordinates"] or 0,
            "missingOrInvalidPrices": offers["missing_prices"] or 0,
            "missingPriceUpdateTimes": offers["missing_price_dates"] or 0,
            "orphanOffers": offers["orphan_offers"] or 0,
            "invalidSpecsJson": invalid_specs,
            "latestPriceUpdateAt": latest_update,
            "latestPriceAgeDays": age_days,
            "parsedAddresses": {
                "shops": shops["total"], "malls": shops["malls"],
                "floors": shops["floors"], "units": shops["units"],
            },
            "paymentOptions": payment_counts,
            "marketHubs": {
                "count": len(MARKET_HUBS),
                "coordinateVerified": sum(bool(item[6]) for item in MARKET_HUBS),
                "coordinateUnverified": sum(not item[6] for item in MARKET_HUBS),
            },
            "nullDeliveryFlags": shops["missing_delivery"] or 0,
            "priceFreshnessNote": "قیمت ثبت‌شده، زمان تغییر و موجودی سه داده‌ی جدا هستند؛ موجودی آفرها تأییدنشده است.",
        },
        "interpretation": {
            "installment": "فقط payment_options با channel=in_person پرداخت حضوری محسوب می‌شود.",
            "shopName": "نام واقعی تنها برای فروشگاه دارای وب‌سایت یا اینستاگرام ثبت می‌شود.",
        },
    }


def _payment_quality(connection) -> dict:
    in_person = 0
    torob_pay = 0
    for row in connection.execute("SELECT payment_options FROM shops"):
        options = parse_json(row["payment_options"], default=[])
        if not isinstance(options, list):
            continue
        if any(item.get("channel") == "in_person" for item in options if isinstance(item, dict)):
            in_person += 1
        if any(
            item.get("channel") == "in_person"
            and "ترب پی" in normalize_fa(item.get("provider_name", ""))
            for item in options if isinstance(item, dict)
        ):
            torob_pay += 1
    return {
        "shopsWithInPersonOption": in_person,
        "shopsWithTarobPayInPerson": torob_pay,
        "mapping": "فقط channel=in_person به‌عنوان پرداخت حضوری در نظر گرفته می‌شود.",
    }


def _value(value: str | None) -> str | None:
    return value if value and value != "null" else None


def _float_or_none(value: str | None) -> float | None:
    try:
        parsed = float(value)
        return parsed if parsed else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _report_progress(table: str, count: int) -> None:
    if count % 10_000 == 0:
        print(f"{table}: {count:,} rows", end="\r", flush=True)


def main() -> None:
    report = load_data()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
