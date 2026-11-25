"""Offer discovery and dynamic Step 5+ allocation tests (entirely offline)."""
from __future__ import annotations

import unittest

from offer_discovery import (
    ExtraOffer, MAX_EXTRA_OFFERS, merge_extra_offers, offer_details,
    offer_step_label, parse_sku_check, parse_step1,
)


class OfferDiscoveryTests(unittest.TestCase):
    def test_fixed_steps_2_to_4_not_duplicated(self):
        report = {"offers": [
            {"product": "g1.2tb.ai.subs_variant", "id": "12months-eft", "micros": "0"},
            {"product": "g1.2tb.ai.subs_variant", "id": "6months-eft", "micros": "0"},
            {"product": "g1.2tb.ai.subs_variant", "id": "6months-eft-2", "micros": "0"},
            {"product": "g1.2tb.ai.subs_variant", "id": "6months-eft-ss-2026", "micros": "0"},
            {"product": "g1.play.20tb", "id": "promo-2026", "micros": "19990000", "period": "P1M"},
            {"product": "g1.play.20tb", "id": "promo-2026", "micros": "19990000", "period": "P1M"},
        ]}
        offers = merge_extra_offers(parse_step1(report))
        self.assertEqual(len(offers), 2)
        self.assertTrue(offers[0].legacy_checkout_supported)
        self.assertEqual(offer_step_label(5, offers[0]), "5. Optional +6 months")
        self.assertIn("Ultra", offer_step_label(6, offers[1]))
        self.assertFalse(offers[1].legacy_checkout_supported)

    def test_no_extra_offers_does_not_create_step_five(self):
        self.assertEqual(merge_extra_offers(parse_step1({"offers": [
            {"product": "g1.2tb.ai.subs_variant", "id": "12months-eft"}
        ]})), [])

    def test_custom_sku_merge_is_deterministic_and_token_free(self):
        sku_result = {"status": "observed", "items": [{
            "sku": "g1.play.20tb",
            "offer_id": "promo-2026",
            "base_plan_id": "monthly",
            "token": "DO_NOT_DISPLAY",
            "phases": [{
                "price_amount_micros": "19990000", "currency": "USD",
                "billing_period": "P1M", "purchaseToken": "SECRET",
            }],
        }]}
        after = merge_extra_offers(
            parse_step1({"offers": [
                {"product": "g1.play.20tb", "id": "promo-2026", "micros": "19990000"},
            ]}), parse_sku_check(sku_result)
        )
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].currency, "USD")
        self.assertNotIn("DO_NOT_DISPLAY", repr(after))
        self.assertNotIn("SECRET", offer_details(after[0]))

    def test_distinct_base_plans_are_not_collapsed(self):
        primary = ExtraOffer("g1.play.20tb", "intro")
        monthly = ExtraOffer("g1.play.20tb", "intro", "monthly", source="sku")
        yearly = ExtraOffer("g1.play.20tb", "intro", "yearly", source="sku")
        self.assertEqual(merge_extra_offers([primary, yearly, monthly, monthly]),
                         [monthly, yearly])

    def test_bare_base_plan_does_not_collide_with_named_offer(self):
        raw = {"status": "observed", "items": [
            {"sku": "g1.example", "base_plan_id": "monthly", "offer_id": value}
            for value in ("", "base-plan-monthly", "")
        ]}
        rows = merge_extra_offers(parse_sku_check(raw))
        self.assertEqual({row.offer_id for row in rows}, {"", "base-plan-monthly"})
        self.assertEqual(len(rows), 2)

    def test_cannot_treat_an_arbitrary_offer_as_legacy_checkout(self):
        self.assertFalse(ExtraOffer("g1.play.20tb", "6months-eft-ss-2026").legacy_checkout_supported)
        self.assertFalse(ExtraOffer("g1.2tb.ai.subs_variant", "new-offer").legacy_checkout_supported)

    def test_bounded_sanitized_and_no_observation_on_error(self):
        items = [{"product": "g1.play.20tb", "id": "o" + str(i)}
                 for i in range(MAX_EXTRA_OFFERS + 10)]
        items.append({"product": "g1.play.20tb;rm -rf", "id": "bad"})
        self.assertEqual(parse_step1({"offers": [items[-1]]}), [])
        offers = merge_extra_offers(parse_step1({"offers": items}))
        self.assertEqual(len(offers), MAX_EXTRA_OFFERS)
        self.assertEqual(parse_sku_check({"status": "timeout", "items": items}), [])
        self.assertTrue(all(";" not in row.product for row in offers))


if __name__ == "__main__":
    unittest.main()
