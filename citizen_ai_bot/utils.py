from __future__ import annotations

from difflib import SequenceMatcher


def fuzzy_score(a: str, b: str) -> float:
    left = (a or "").strip().lower()
    right = (b or "").strip().lower()
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.92
    return SequenceMatcher(None, left, right).ratio()


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def fmt_credits(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f} aUEC"


def fmt_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{digits}f}"
