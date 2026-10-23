"""Fast smoke checks for every local tool and the external tool response shape."""

from __future__ import annotations

import asyncio
from src.core.database import database
from src.core.tools.registry import TOOLS


def _seed_offer() -> dict:
    with database(readonly=True) as connection:
        row = connection.execute(
            """
            SELECT o.product_id, o.shop_id, s.lat, s.lng
            FROM offers AS o
            JOIN shops AS s ON s.id = o.shop_id
            WHERE o.price > 0 AND s.lat IS NOT NULL AND s.lng IS NOT NULL
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("برای smoke test آفر معتبر پیدا نشد؛ ابتدا دیتاست را بارگذاری کنید.")
    return dict(row)


async def run_smoke_checks() -> list[tuple[str, str]]:
    seed = _seed_offer()
    tool_map = {item.name: item for item in TOOLS}
    required_names = {
        "search_products", "get_offers", "compare_shops", "check_open_now",
        "inquire_shop", "find_alternatives", "get_shop_location_hint",
        "suggest_market_hub", "product_quick_look", "web_search", "resolve_location",
        "save_user_preference", "load_user_preferences",
    }
    missing = required_names - tool_map.keys()
    if missing:
        raise AssertionError(f"ابزارها در registry نیستند: {sorted(missing)}")

    cases = [
        ("search_products", {"query": "کتونی", "limit": 3}),
        ("get_offers", {"product_id": seed["product_id"], "lat": 35.7219, "lng": 51.4097, "radius": 30}),
        ("compare_shops", {"shop_ids": [seed["shop_id"]], "product_id": seed["product_id"]}),
        ("check_open_now", {"shop_id": seed["shop_id"]}),
        ("inquire_shop", {"shop_id": seed["shop_id"], "product_id": seed["product_id"]}),
        ("find_alternatives", {"product_id": seed["product_id"], "shop_id": seed["shop_id"], "lat": 35.7219, "lng": 51.4097, "radius": 30}),
        ("get_shop_location_hint", {"shop_id": seed["shop_id"]}),
        ("suggest_market_hub", {"category_or_product": "چاپگر صنعتی چاپ روی پارچه"}),
        ("product_quick_look", {"product_id": seed["product_id"]}),
        ("save_user_preference", {"key": "mode", "value": "in_person"}),
        ("load_user_preferences", {}),
    ]
    results: list[tuple[str, str]] = []
    for name, arguments in cases:
        output = await tool_map[name].ainvoke(arguments)
        _assert_result(name, output)
        results.append((name, output["source"]))
    return results


def _assert_result(name: str, output) -> None:
    if not isinstance(output, dict) or "data" not in output or "source" not in output:
        raise AssertionError(f"{name}: خروجی باید data و source داشته باشد")
    if output["source"] not in {"dataset", "web", "ai_knowledge", "simulated"}:
        raise AssertionError(f"{name}: منبع نامعتبر است")


def main() -> None:
    results = asyncio.run(run_smoke_checks())
    for name, source in results:
        print(f"PASS {name} [{source}]")
    print(f"\nابزارهای محلی: {len(results)}/{len(results)} موفق")


if __name__ == "__main__":
    main()
