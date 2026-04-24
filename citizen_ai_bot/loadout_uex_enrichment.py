from __future__ import annotations

import asyncio
import re
from typing import Any

from .models import LoadoutReport

_ITEM_PREFIX_RE = re.compile(r"^\s*(?:\d+x\s+)?(.+?)\s+—")
_GENERIC_NAMES = {
    "s1 missiles",
    "s2 missiles",
    "s3 missiles",
    "s4 missiles",
    "s5 missiles",
    "s6 missiles",
    "s7 missiles",
    "s8 missiles",
}


def _extract_recommended_name(line: str) -> str | None:
    match = _ITEM_PREFIX_RE.search(line or "")
    if not match:
        return None
    name = match.group(1).strip()
    if not name or name.casefold() in _GENERIC_NAMES:
        return None
    return name


def _uex_display_name(item: dict[str, Any]) -> str | None:
    for key in ("name", "name_full", "slug", "uuid"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _uex_descriptor(item: dict[str, Any]) -> str:
    bits: list[str] = []
    for key in ("category", "section", "company_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in bits:
            bits.append(value.strip())
    return " • ".join(bits)


async def enrich_loadout_report_with_uex(client: Any, report: LoadoutReport) -> LoadoutReport:
    """
    Cross-checks recommended loadout item names against UEX's item index.

    The Wiki/local loadout engine remains responsible for ship stats, hardpoints,
    and role scoring. UEX is used here as a second data source for catalog names
    and item identity without making /loadout fail if UEX is unavailable.
    """
    recommended_names = []
    for line in [*report.weapons, *report.systems]:
        name = _extract_recommended_name(line)
        if name and name not in recommended_names:
            recommended_names.append(name)

    if not recommended_names:
        report.notes.append("UEX source: no named components were available to cross-check.")
        return report

    async def resolve(name: str) -> tuple[str, dict[str, Any] | None]:
        try:
            return name, await client.resolve_item(name)
        except Exception:
            return name, None

    results = await asyncio.gather(*(resolve(name) for name in recommended_names))
    matched: list[str] = []
    for requested, item in results:
        if not item:
            continue
        display = _uex_display_name(item)
        if not display:
            continue
        descriptor = _uex_descriptor(item)
        if descriptor:
            matched.append(f"{requested} → {display} ({descriptor})")
        else:
            matched.append(f"{requested} → {display}")

    if matched:
        report.notes.append(
            f"UEX catalog match: {len(matched)}/{len(recommended_names)} named components resolved."
        )
        report.notes.extend(matched[:6])
    else:
        report.notes.append(
            "UEX catalog match: no recommended component names resolved; Wiki/local data was used as fallback."
        )

    return report
