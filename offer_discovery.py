"""Deterministic, account-agnostic display model for offers found during Step 1.

This module never starts checkout. Unknown offers are INSPECT-ONLY.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_PRO = "g1.2tb.ai.subs_variant"
_FIXED_IDS = {"12months-eft", "6months-eft", "6months-eft-2"}
_OPTIONAL_ID = "6months-eft-ss-2026"
_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
MAX_EXTRA_OFFERS = 12


@dataclass(frozen=True)
class ExtraOffer:
    product: str
    offer_id: str
    base_plan: str = ""
    period: str = ""
    price_micros: str = ""
    currency: str = ""
    source: str = "step1"

    @property
    def legacy_checkout_supported(self) -> bool:
        # Only the repository's pre-existing Step 5 is explicitly implemented.
        return self.product == _PRO and self.offer_id == _OPTIONAL_ID

    @property
    def key(self) -> tuple[str, str, str]:
        return self.product, self.offer_id, self.base_plan


def _safe(value: object) -> str:
    return value if isinstance(value, str) and _SAFE.fullmatch(value) else ""


def _micros(value: object) -> str:
    value = str(value) if isinstance(value, (int, str)) and not isinstance(value, bool) else ""
    return value if value.isascii() and value.isdecimal() and len(value) <= 18 else ""


def parse_step1(report: dict | None, *, include_fixed: bool = False) -> list[ExtraOffer]:
    """Parse only the sanitized offer identifiers from a fresh Step 1 report."""
    if not isinstance(report, dict) or not isinstance(report.get("offers"), list):
        return []
    entries = []
    for raw in report["offers"][:100]:
        if not isinstance(raw, dict):
            continue
        product, offer_id = _safe(raw.get("product")), _safe(raw.get("id"))
        if not product or not offer_id or (not include_fixed and product == _PRO and offer_id in _FIXED_IDS):
            continue
        entries.append(ExtraOffer(
            product=product, offer_id=offer_id, period=_safe(raw.get("period")),
            price_micros=_micros(raw.get("micros")), source="step1"))
    return entries


def parse_sku_check(result: dict | None) -> list[ExtraOffer]:
    """Map token-free ProductDetails observations to offer descriptions."""
    if not isinstance(result, dict) or result.get("status") != "observed":
        return []
    rows = result.get("items")
    if not isinstance(rows, list):
        return []
    entries = []
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        product = _safe(row.get("sku"))
        offer_id = _safe(row.get("offer_id"))
        base = _safe(row.get("base_plan_id"))
        if not product or not base or (product == _PRO and offer_id in _FIXED_IDS):
            continue
        if row.get("offer_id") not in ("", None) and not offer_id:
            continue
        phases = row.get("phases")
        first = phases[0] if isinstance(phases, list) and phases and isinstance(phases[0], dict) else {}
        entries.append(ExtraOffer(
            product=product, offer_id=offer_id, base_plan=base,
            period=_safe(first.get("billing_period")), currency=_safe(first.get("currency")),
            price_micros=_micros(first.get("price_amount_micros")), source="sku"))
    return entries


def merge_extra_offers(*groups: list[ExtraOffer]) -> list[ExtraOffer]:
    """Deduplicate and allocate stable positions. Prefer the known optional offer at Step 5."""
    by_key: dict[tuple[str, str, str], ExtraOffer] = {}
    for group in groups:
        for item in group:
            if not isinstance(item, ExtraOffer):
                continue
            existing = by_key.get(item.key)
            if existing is None or (item.source == "sku" and existing.source != "sku"):
                by_key[item.key] = item
    # A primary report has no base-plan ID. Prefer the concrete observations
    # without collapsing distinct base plans into one record.
    concrete = {(x.product, x.offer_id) for x in by_key.values() if x.base_plan}
    return sorted(
        (x for x in by_key.values()
         if x.base_plan or (x.product, x.offer_id) not in concrete),
        key=lambda x: (0 if x.legacy_checkout_supported else 1,
                       x.product, x.offer_id, x.base_plan)
    )[:MAX_EXTRA_OFFERS]


def offer_step_label(step: int, offer: ExtraOffer) -> str:
    """Compact label safe for narrow TUI sidebar."""
    if offer.legacy_checkout_supported:
        return f"{step}. Optional +6 months"
    kind = "Ultra" if ("20tb" in offer.product or "30tb" in offer.product) else "Offer"
    label = offer.offer_id or f"base-plan-{offer.base_plan}"
    return f"{step}. {kind}: {label[:17]} (view)"


def offer_details(offer: ExtraOffer) -> str:
    lines = [
        f"Product: {offer.product}", f"Offer: {offer.offer_id or '(base plan)'}",
        f"Base plan: {offer.base_plan or 'Not returned'}",
        f"First phase: {offer.price_micros or 'Unknown'} micros / {offer.period or 'Unknown'}",
        f"Currency: {offer.currency or 'Not returned by Step 1'}",
        "Eligibility: NOT VERIFIED",
        "Newly discovered offers are metadata only; no automatic checkout.",
    ]
    return "\n".join(lines)
