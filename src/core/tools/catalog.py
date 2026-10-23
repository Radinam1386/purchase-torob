"""Product search against the local SQLite and FTS5 dataset."""

from __future__ import annotations

import re

from langchain_core.tools import tool

from src.core.database import database
from src.core.text import normalize_fa
from src.core.tools.common import product_from_row, tool_result
from src.core.tools.schemas import SearchProductsInput

_PHONE_MODEL_ALIASES = {
    "آیفون": "iphone",
    "اپل": "iphone",
    "سامسونگ": "samsung",
    "شیائومی": "xiaomi",
    "هواوی": "huawei",
    "samsung": "سامسونگ",
    "iphone": "آیفون",
    "xiaomi": "شیائومی",
    "huawei": "هواوی",
}


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

    phone_query = _is_phone_query(normalized)
    with database(readonly=True) as connection:
        if phone_query:
            model_terms = _phone_model_terms(normalized)
            if model_terms:
                results = _search_exact_phone_model(
                    connection, model_terms, category, max_price, limit
                )
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


def _phone_model_terms(query: str) -> list[str]:
    ignored = {
        "گوشی", "موبایل", "تلفن", "همراه", "برای", "مدل", "میخوام", "می", "خوام",
        "عکاسی", "بازی", "گیم", "روزمره", "دانشگاه", "کار", "سفر", "بودجه",
        "galaxy", "گلکسی",
        "حداکثر", "میلیون", "هزار", "تا", "تومان",
        "camera", "photo", "photography", "video", "selfie", "gaming", "game",
        "battery", "storage", "for", "the", "with", "phone", "smartphone", "mobile",
    }
    query = re.sub(r"\d+\s*(?:gb|tb|گیگ(?:ابایت)?|ترابایت|رم)", " ", query)
    terms = [
        term
        for term in re.findall(r"[a-z0-9]+|[آ-ی]+", query)
        if term not in ignored
    ]
    has_model_identifier = any(re.search(r"\d", term) for term in terms) or any(
        re.search(r"[a-z]", term) for term in terms
    )
    return terms if has_model_identifier else []


def _is_phone_query(query: str) -> bool:
    if "گوشی پزشکی" in query:
        return False
    if re.search(r"گوشی|موبایل|تلفن همراه", query):
        return True
    # Common Samsung Galaxy S/A series queries are often written without "گوشی".
    return bool(
        re.search(r"(?:samsung|سامسونگ|galaxy|گلکسی)\s*(?:s|a|z)?\s*\d{2}\s*(?:fe|ultra|plus)?", query)
    )


def _search_exact_phone_model(
    connection, terms: list[str], category: str | None, max_price: int | None, limit: int,
):
    conditions = [
        "p.category_norm = 'گوشی موبایل'",
        "o.price > 0",
        "p.title_norm NOT LIKE '%طرح%'",
        "p.title_norm NOT LIKE '%ماکت%'",
    ]
    parameters: list[object] = []
    for term in terms:
        conditions.append(
            "(p.title_norm LIKE ? OR lower(coalesce(p.model, '')) LIKE ? "
            "OR lower(coalesce(p.brand, '')) LIKE ? OR p.title_norm LIKE ? "
            "OR lower(coalesce(p.model, '')) LIKE ? OR lower(coalesce(p.brand, '')) LIKE ?)"
        )
        patterns = (f"%{term}%", f"%{_PHONE_MODEL_ALIASES.get(term, term)}%")
        parameters.extend((*([patterns[0]] * 3), *([patterns[1]] * 3)))
    normalized_terms = list(
        dict.fromkeys(_PHONE_MODEL_ALIASES.get(term, term) for term in terms)
    )
    model_terms = [
        term for term in normalized_terms
        if re.fullmatch(r"[a-z0-9]+", term)
        and term not in {"samsung", "iphone", "xiaomi", "huawei"}
    ]
    if category:
        conditions.append("p.category_norm LIKE ?")
        parameters.append(f"%{normalize_fa(category)}%")
    if max_price is not None:
        conditions.append("o.price <= ?")
        parameters.append(max_price)
    parameters.extend(("".join(model_terms), min(limit, 20)))
    rows = connection.execute(
        f"""
        SELECT p.*
        FROM products AS p
        JOIN offers AS o ON o.product_id = p.id
        WHERE {' AND '.join(conditions)}
        GROUP BY p.id
        ORDER BY CASE WHEN replace(lower(coalesce(p.model, '')), ' ', '') = ? THEN 0 ELSE 1 END,
                 MIN(o.price), p.title
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return [product_from_row(row) for row in rows]
