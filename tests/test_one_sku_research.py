"""Offline regression checks for isolated One-SKU research helpers."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "research" / "one-sku-study" / "sku_research.py"
SPEC = importlib.util.spec_from_file_location("sku_research", MODULE)
assert SPEC and SPEC.loader
sku_research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sku_research)


class OneSkuResearchTests(unittest.TestCase):
    def test_candidate_generation_is_offline_and_unique(self):
        rows = sku_research.generate_candidates(("2tb.ai",), ("12months",))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows, sorted(set(rows)))
        self.assertIn("g1.2tb.ai.12months_eft", rows)

    def test_rejects_untrusted_candidate_components(self):
        with self.assertRaises(ValueError):
            sku_research.generate_candidates(("2tb.ai;rm -rf",), ("12months",))

    def test_rejects_oversized_combined_candidate(self):
        with self.assertRaises(ValueError):
            sku_research.generate_candidates(("a" * 64,), ("b" * 64,))

    def test_scrubs_tokens_and_account_identifiers(self):
        summary = sku_research.summarize_offer({
            "product": "g1.2tb.ai.12months_eft",
            "id": "example-offer",
            "micros": "0",
            "currency": "USD",
            "token": "SECRET",
            "purchaseToken": "SECRET",
            "account": "private@example.com",
            "card": "SECRET",
        })
        self.assertTrue(summary["first_phase_zero_price"])
        self.assertFalse(summary["eligibility_verified"])
        self.assertFalse(summary["subscription_active_verified"])
        self.assertEqual(
            set(summary),
            {"sku", "offer_id", "first_phase_price_micros", "currency",
             "first_phase_zero_price", "eligibility_verified",
             "subscription_active_verified"},
        )
        self.assertNotIn("SECRET", str(summary))
        self.assertNotIn("private@example.com", str(summary))

    def test_paid_first_phase_is_not_free(self):
        summary = sku_research.summarize_offer({
            "sku": "g1.ai.pro.3months_ip_90p",
            "offerId": "demo",
            "micros": 1990000,
            "currency": "USD",
        })
        self.assertFalse(summary["first_phase_zero_price"])
        self.assertEqual(summary["first_phase_price_micros"], 1990000)

    def test_rejects_non_string_offer_ids(self):
        for value in (None, False, 0, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sku_research.summarize_offer({
                    "sku": "g1.example", "micros": 0, "offerId": value
                })

    def test_rejects_invalid_prices_and_skus(self):
        for bad in (-1, True, "NaN", "1.5", None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    sku_research.summarize_offer({
                        "product": "g1.2tb.ai.12months_eft",
                        "micros": bad,
                    })
        with self.assertRaises(ValueError):
            sku_research.summarize_offer({
                "product": "not-a-sku", "micros": "0"
            })


if __name__ == "__main__":
    unittest.main()
