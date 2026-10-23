"""Persian text normalization and address parsing."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def normalize_fa(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"}))
    digit_map = {digit: str(index) for index, digit in enumerate(_ARABIC_DIGITS)}
    digit_map.update({digit: str(index) for index, digit in enumerate(_PERSIAN_DIGITS)})
    normalized = normalized.translate(str.maketrans(digit_map))
    normalized = re.sub(r"[\u064b-\u065f\u0670]", "", normalized)
    normalized = re.sub(r"[\u200c\u200e\u200f]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()


@dataclass(frozen=True)
class ParsedAddress:
    mall: str | None
    floor: str | None
    unit: str | None


def parse_address(address: str | None) -> ParsedAddress:
    if not address:
        return ParsedAddress(None, None, None)

    mall = _capture(r"(?:پاساژ|مجتمع|مرکز خرید|بازار)\s+([^،,]+)", address)
    floor = _capture(r"طبقه\s*([\w۰-۹٠-٩-]+)", address)
    unit = _capture(r"واحد\s*([\w۰-۹٠-٩-]+)", address)
    return ParsedAddress(mall=mall, floor=floor, unit=unit)


def _capture(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def parse_json(value: str | None, default=None):
    import json

    if not value or value == "null":
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
