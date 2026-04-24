from __future__ import annotations

import re
from typing import Any

from .models import LoadoutReport

_ITEM_PREFIX_RE = re.compile(r"^\s*(?:\[[^\]]+\]\s*)?(?:\d+x\s+)?(.+?)\s+—")
_GENERIC_NAMES = {"s1 missiles", "s2 missiles", "s3 missiles", "s4 missiles", "s5 missiles", "s6 missiles", "s7 missiles", "s8 missiles"}
_BLOCKED_DESCRIPTORS = ("armor", "helmet", "clothing", "legwear", "torso", "personal weapons", "medical", "food", "drink")


def _extract_recommended_name(line: str) -> str | None:
    match = _ITEM_PREFIX_RE.search(line or "")
    if not match:
        return None
    name = match.group(1).strip()
    if not name or name.casefold() in _GENERIC_NAMES:
        return None
    return name


def _scope_for_line(line: str) -> str:
    lower = line.lower()
    if "missile" in lower or "torpedo" in lower:
        return "missile"
    if "shield" in lower:
        return "shield"
    if "power plant" in lower:
        return "power"
    if "cooler" in lower:
        return "cooler"
    if "quantum drive" in lower:
        return "quantum"
    return "ship_weapon"


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


def _descriptor_is_safe(descriptor: str) -> bool:
    lower = descriptor.lower()
    return not any(term in lower for term in _BLOCKED_DESCRIPTORS)


async def enrich_loadout_report_with_uex(client: Any, report: LoadoutReport) -> LoadoutReport:
    """Cross-check recommended loadout components against UEX's scoped ship-component index."""
    requested: list[tuple[str, str | None]] = []
    for line in [*report.weapons, *report.systems]:
        name = _extract_recommended_name(line)
        if not name:
            continue
        pair = (name, _scope_for_line(line))
        if pair not in requested:
            requested.append(pair)

    if not requested:
        report.notes.append("UEX catalog match: no named ship components were available to cross-check.")
        return report

    try:
        if hasattr(client, "resolve_ship_components"):
            resolved = await client.resolve_ship_components(requested)
        else:
            resolved = {name: await client.resolve_ship_component(name, scope=scope) for name, scope in requested}
    except Exception:
        report.notes.append("UEX catalog match: unavailable; loadout recommendations still used live ship slot data.")
        return report

    matched: list[str] = []
    for name, _scope in requested:
        item = resolved.get(name)
        if not item:
            continue
        display = _uex_display_name(item)
        descriptor = _uex_descriptor(item)
        if not display or not _descriptor_is_safe(descriptor):
            continue
        matched.append(f"{name} → {display} ({descriptor})" if descriptor else f"{name} → {display}")

    if matched:
        report.notes.append(f"UEX catalog match: {len(matched)}/{len(requested)} named ship components resolved.")
        report.notes.extend(matched[:6])
    else:
        report.notes.append("UEX catalog match: no safe ship-component matches found; suppressed broad item matches.")
    return report
