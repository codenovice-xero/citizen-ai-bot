from __future__ import annotations

from difflib import SequenceMatcher


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def slugify(value: str | None) -> str:
    return normalize_text(value).replace(" ", "-")


def fuzzy_score(a: str | None, b: str | None) -> float:
    left = normalize_text(a)
    right = normalize_text(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 100.0
    if left in right or right in left:
        return 92.0
    return SequenceMatcher(None, left, right).ratio() * 100.0


def fmt_credits(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):,.0f} aUEC"


def fmt_number(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):,.{digits}f}"
