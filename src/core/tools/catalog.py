"""Product search against the local SQLite and FTS5 dataset."""

from __future__ import annotations

import re

from langchain_core.tools import tool

from src.core.database import database
from src.core.text import normalize_fa
from src.core.tools.common import product_from_row, tool_result
from src.core.tools.schemas import SearchProductsInput


@tool(args_schema=SearchProductsInput)
def search_products(
    query: str,
    category: str | None = None,
    max_price: int | None = None,
    filters: dict | None = None,
    limit: int = 8,
) -> dict:
    """جستجوی محصولات دیتاست ترب با تطبیق فارسی و FTS5."""
    normalized = normalize_fa(query)
    category = category or (filters or {}).get("category")
    max_price = max_price if max_price is not None else (filters or {}).get("max_price")
    if not normalized:
        return tool_result("dataset", [])

    phone_query = bool(re.search(r"گوشی|موبایل|تلفن همراه", normalized)) and "گوشی پزشکی" not in normalized
    with database(readonly=True) as connection:
        if phone_query:
            results = _search_phones(connection, category, max_price, limit)
            if results:
                return tool_result("dataset", results)

        terms = normalized.split()
        if phone_query:
            terms = [term for term in terms if term not in {"گوشی", "موبایل", "تلفن", "همراه"}]
            terms.extend(["موبایل", "تلفن", "همراه"])
        quoted_terms = ['"' + term.replace('"', '""') + '"' for term in dict.fromkeys(terms)]
        match_query = " OR ".join(quoted_terms)
        if not match_query:
            return tool_result("dataset", [])

        conditions = ["product_fts MATCH ?"]
        parameters: list[object] = [match_query]
        if category:
            conditions.append("p.category_norm LIKE ?")
            parameters.append(f"%{normalize_fa(category)}%")
        if max_price is not None:
            conditions.append(
                "EXISTS (SELECT 1 FROM offers AS offer "
                "WHERE offer.product_id = p.id AND offer.price > 0 AND offer.price <= ?)"
            )
            parameters.append(max_price)
        parameters.append(min(limit, 100))

        rows = connection.execute(
            f"""
            SELECT p.*
            FROM product_fts
            JOIN products AS p ON p.id = product_fts.product_id
            WHERE {' AND '.join(conditions)}
            ORDER BY bm25(product_fts, 0, 8, 2, 1)
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        products = [product_from_row(row) for row in rows]
        if phone_query:
            products = [
                product for product in products
                if re.search(r"گوشی|موبایل|تلفن همراه", normalize_fa(product.title_fa))
            ]
        return tool_result("dataset", products[:limit])


def _search_phones(connection, category: str | None, max_price: int | None, limit: int):
    conditions = ["p.category_norm = 'گوشی موبایل'", "o.price > 0"]
    parameters: list[object] = []
    if category:
        conditions.append("p.category_norm LIKE ?")
        parameters.append(f"%{normalize_fa(category)}%")
    if max_price is not None:
        conditions.append("o.price <= ?")
        parameters.append(max_price)
    parameters.append(min(limit, 20))
    rows = connection.execute(
        f"""
        SELECT p.*
        FROM products AS p
        JOIN offers AS o ON o.product_id = p.id
        WHERE {' AND '.join(conditions)}
        GROUP BY p.id
        ORDER BY MIN(o.price)
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return [product_from_row(row) for row in rows]
