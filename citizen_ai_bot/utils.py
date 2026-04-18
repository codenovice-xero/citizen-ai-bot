from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable


def fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def best_text_matches(query: str, candidates: Iterable[str], limit: int = 10) -> list[str]:
    scored = sorted(
        ((candidate, fuzzy_score(query, candidate)) for candidate in candidates),
        key=lambda x: x[1],
        reverse=True,
    )
    return [candidate for candidate, _ in scored[:limit]]


def clamp(n: float, low: float, high: float) -> float:
    return max(low, min(n, high))
