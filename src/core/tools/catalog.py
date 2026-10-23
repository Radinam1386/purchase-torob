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
    category = category or (filters or {}).get("category") or ""
    max_price = max_price if max_price is not None else (filters or {}).get("max_price")
    if not normalize_fa(query):
        return tool_result("dataset", [])
    where, params, ranked = catalog_filter(query, category=category, min_price=(filters or {}).get("min_price"), max_price=max_price)
    order = "bm25(product_fts, 0, 8, 2, 1),p.id" if ranked else "p.title,p.id"
    with database(readonly=True) as connection:
        rows = connection.execute(
            "SELECT p.* FROM product_fts JOIN products p ON p.id=product_fts.product_id "
            + where + " ORDER BY " + order + " LIMIT ?", [*params, max(1,min(limit,100))]).fetchall()
    return tool_result("dataset", [product_from_row(row) for row in rows])


def _is_phone_query(query: str) -> bool:
    if "گوشی پزشکی" in query or re.search(r"(?<!\w)(?:هدفون|هندزفری|هدست)(?!\w)", query):
        return False
    if re.search(r"(?<!\w)(?:گوشی|موبایل|تلفن همراه)(?!\w)", query):
        return True
    # Common Samsung Galaxy S/A series queries are often written without "گوشی".
    return bool(
        re.search(r"(?:samsung|سامسونگ|galaxy|گلکسی)\s*(?:s|a|z)?\s*\d{2}\s*(?:fe|ultra|plus)?", query)
    )


_CATALOG_INTENT_WORDS = {
    "میخوام", "میخوامش", "می", "خوام", "میخواهم", "میخواستم", "میخرم",
    "بخرم", "بگیرم", "میگیرم", "برای", "واسه", "لطفا", "لطفاً",
    "پیشنهاد", "پیشنهاد بده", "پیدا", "کن", "بهم", "یه", "یک",
    "موسیقی", "موزیک", "روزمره", "دانشگاه", "کار", "عکاسی", "بازی",
    "گیم", "ورزش", "استفاده", "حدود", "بودجه", "تومان", "میلیون",
    "گوش", "دادن", "به", "موسیقی",
}


def _catalog_terms(query: str) -> list[str]:
    normalized = query
    if re.search(r"تومان|میلیون|میلیارد|هزار|بودجه|سقف", normalized):
        normalized = re.sub(r"[0-9۰-۹٠-٩][0-9۰-۹٠-٩,.٫]*", " ", normalized)
        normalized = re.sub(r"تومان|میلیون|میلیارد|هزار|بودجه|سقف|حداکثر|تا", " ", normalized)
    return [term for term in normalized.split() if term not in _CATALOG_INTENT_WORDS]

def catalog_filter(q: str = "", brand: str = "", category: str = "",
                    min_price: int | None = None, max_price: int | None = None):
    """One relevance/price predicate shared by the grid and its store map."""
    from src.core.text import normalize_fa
    query = normalize_fa(q)
    terms = _catalog_terms(query)
    clauses, params = [], []
    if terms:
        if _is_phone_query(query):
            clauses.append("p.category_norm LIKE '%گوشی موبایل%'")
            clauses.extend(["p.title_norm NOT LIKE '%طرح%'", "p.title_norm NOT LIKE '%ماکت%'"])
            for term in terms:
                if term in {"گوشی", "موبایل", "تلفن", "همراه", "galaxy", "گلکسی"}:
                    continue
                aliases = list(dict.fromkeys((term, _PHONE_MODEL_ALIASES.get(term, term))))
                fragments = []
                for alias in aliases:
                    fragments.append("(p.title_norm LIKE ? OR replace(lower(coalesce(p.model,'')), ' ', '') LIKE ? OR lower(coalesce(p.brand,'')) LIKE ?)")
                    params.extend((f"%{alias}%", f"%{alias.replace(' ', '')}%", f"%{alias}%"))
                clauses.append("(" + " OR ".join(fragments) + ")")
        else:
            match = " AND ".join('("روگوشی" OR ("رو" AND "گوشی"))' if term == "روگوشی"
                                 else '"' + term.replace('"', '""') + '"' for term in terms)
            clauses.append("product_fts MATCH ?")
            params.append(match)
        if any(term in query for term in ("هدفون", "هندزفری", "هدست")):
            clauses.append("p.category_norm LIKE 'هدفون%'")
        elif any(term in query for term in ("لپ تاپ", "لپتاپ")):
            clauses.append("p.category_norm LIKE 'لپ%'")
    if brand.strip():
        clauses.append("lower(coalesce(p.brand,'')) = ?")
        params.append(normalize_fa(brand))
    if category.strip():
        clauses.append("p.category_norm LIKE ?")
        params.append(normalize_fa(category) + "%")
    # Bounds must apply to the SAME offer, not two unrelated prices.
    price_clauses = _price_filter("ox", min_price, max_price)
    if min_price is not None or max_price is not None:
        clauses.append("EXISTS (SELECT 1 FROM offers ox WHERE ox.product_id=p.id AND " + price_clauses[0] + ")")
        params.extend(price_clauses[1])
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params, bool(terms) and not _is_phone_query(query)


def _price_filter(alias: str, minimum: int | None, maximum: int | None):
    clauses = [f"{alias}.price>0"]
    params = []
    if minimum is not None:
        clauses.append(f"{alias}.price>=?")
        params.append(minimum)
    if maximum is not None:
        clauses.append(f"{alias}.price<=?")
        params.append(maximum)
    return " AND ".join(clauses), params
