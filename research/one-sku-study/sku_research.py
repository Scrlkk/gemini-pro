#!/usr/bin/env python3
"""Offline research helpers for candidate Google Play SKU metadata.

No ADB, Frida, network, account access or checkout. Nothing in this file is
imported by the production application.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

_SKU_RE = re.compile(r"^g1\.[a-z0-9][a-z0-9._-]{2,127}$")
_PART_RE = re.compile(r"^[a-z0-9][a-z0-9._]{0,63}$")
_OFFER_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

# Example patterns for offline comparison, NOT a list of verified products.
EXAMPLE_TIERS = ("2tb.ai", "5tb.ai", "ai.pro", "20tb", "30tb", "ai.ultra")
EXAMPLE_PERIODS = ("1month", "3months", "6months", "12months", "18months")


def generate_candidates(
    tiers: tuple[str, ...] = EXAMPLE_TIERS,
    periods: tuple[str, ...] = EXAMPLE_PERIODS,
) -> list[str]:
    """Return SKU candidates only; do not query Google Play."""
    for part in (*tiers, *periods):
        if not _PART_RE.fullmatch(part):
            raise ValueError("Invalid SKU component")
    generated = set()
    for tier in tiers:
        for period in periods:
            generated.add(f"g1.{tier}.{period}_eft")
            generated.add(f"g1.{tier}.{period}_ip_90p")
            generated.add(f"g1.{tier}.{period}_ip_95p.acq")
    if any(not _SKU_RE.fullmatch(value) for value in generated):
        raise ValueError("Combined SKU components exceed the supported format or length")
    return sorted(generated)


def _price_micros(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("Invalid price")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str) and value.isascii() and value.isdecimal():
        amount = int(value)
    else:
        raise ValueError("Price must be an integer in micros")
    if amount < 0:
        raise ValueError("Price cannot be negative")
    return amount


def summarize_offer(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Keep a narrow metadata allowlist: never return tokens or account data.

    The summarized first-phase amount is not a claim about total subscription
    cost, eligibility, free-trial duration, or activation.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("Offer must be a mapping")
    sku = raw.get("product", raw.get("sku"))
    if not isinstance(sku, str) or not _SKU_RE.fullmatch(sku):
        raise ValueError("Invalid SKU")
    price = _price_micros(raw.get("micros"))
    currency = raw.get("currency", "UNKNOWN")
    if currency != "UNKNOWN" and (
        not isinstance(currency, str) or not _CURRENCY_RE.fullmatch(currency)
    ):
        raise ValueError("Invalid currency")
    offer_id = raw.get("offerId", raw.get("id", ""))
    if not isinstance(offer_id, str) or (offer_id and not _OFFER_ID_RE.fullmatch(offer_id)):
        raise ValueError("Invalid offer ID")
    return {
        "sku": sku,
        "offer_id": offer_id,
        "first_phase_price_micros": price,
        "currency": currency,
        "first_phase_zero_price": price == 0,
        "eligibility_verified": False,
        "subscription_active_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--candidates", action="store_true", help="Generate offline SKU candidates")
    modes.add_argument("--input", type=Path, help="JSON list of sanitized offer metadata")
    args = parser.parse_args()
    if args.candidates:
        output: Any = generate_candidates()
    else:
        with args.input.open(encoding="utf-8") as stream:
            source = json.load(stream)
        if not isinstance(source, list):
            parser.error("Input must be a JSON list")
        output = [summarize_offer(row) for row in source]
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
