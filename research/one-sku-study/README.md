# One-SKU / Play Billing research (isolated)

Status: **research branch**. The offline helper in this directory is not imported by production. A bounded, read-only SKU query automatically follows a verified Step 1 and is integrated into the Textual UI on this research branch; see [usage](../../docs/SKU-EXPLORER.md). It has not been validated against a real Android/Google Play session.

## Source and provenance

Research input: user-provided `one-sku-study.zip` from https://drive.google.com/file/d/1Ne4izEP3gUTrbKYVrMxVyWFmRoL4BoT7/view (reviewed 2026-11-24). The archive includes `pro0.py`, `query_sku.py`, `scan_family.py`, `scan_hidden.py`, `scan_wide.py`, `proto_dump.js`, setup scripts and Chinese-language instructions. **No explicit redistribution license was found in the archive.** We have intentionally **not copied** its executable code, APKs or assets into this public repository. This research implementation is independent and standard-library-only. Verify rights and provenance before importing any third-party source.

The source describes querying SKU families through Android Play Billing, including Google AI Pro free-trial and discounted variants. Prices, periods, stacking claims and product names in that archive are **unverified assertions**; returned metadata, including a zero-price first phase, does not prove an account is eligible or a subscription was activated. The archive's statement about Ultra availability must not be treated as an authoritative Google announcement.

## Existing architecture on main

- `ultra0.py`: existing Android / ADB / Frida / Play Billing engine. The SKU runner delegates device and PID verification to its `get_target_frida_device` helper. The read-only JS payload is intentionally separate from the checkout-capable payload so it cannot accidentally launch checkout. It owns only its own short-lived read-only connection, never calls the checkout engine, and is independently checked for forbidden purchase operations.
- `tui_core.py`: pure state, step model, report/outcome interpretation.
- `tui.py`: Textual presentation and user approval gates.
- Step 1: list/check offers; no checkout. Steps 2–5 may initiate a real transaction and require separate explicit approvals.
- Existing safety contract: `AGENTS.md`, `SECURITY.md`, `DISCLAIMER.md`.

## What this branch adds

`sku_research.py` is an **offline** proof-of-concept, not a live SKU scanner. It:

1. Generates a deduplicated sample set of SKU-name candidates based on documented naming patterns, without accessing a device or network.
2. Reads **synthetic or manually redacted** offer metadata from local JSON.
3. Outputs a strict allowlist of non-sensitive fields, excluding account identifiers, passwords, purchase tokens, offer tokens, card data and raw reports.
4. Clearly marks eligibility and activation as **unverified**.

Example (offline only, Python 3.10+):

```sh
python research/one-sku-study/sku_research.py --candidates
python research/one-sku-study/sku_research.py --input research/one-sku-study/sample-offers.json
python -m unittest discover -s tests -p 'test_one_sku_research.py' -v
```

## Detailed Check SKU proposal

See [CHECK-SKU-DESIGN.md](CHECK-SKU-DESIGN.md) for the dedicated query-only architecture, UI layout, full pricing-phase response contract, threat model, tests and rollout gates. **The offline helper is not the live query implementation.** See the current usage guide for the integrated read-only scan.

## Historical integration design

1. **Inventory existing offer-query API** in `ultra0.py`. If safe and compatible, extend the existing read-only Step 1 query to accept a **bounded, manually chosen** list of SKU candidates. Avoid importing the third-party `pro0.py`, running unreviewed BAT scripts, or automatically brute-forcing the Play Store.
2. **Validate returned product details** against the active Google Play account, actual current offer and server-provided billing terms. Treat the full offer structure (introductory phases, recurrence, region, renewal pricing) separately from display labels.
3. **Present results in the existing Textual UI**, grouped by confirmed available metadata, without exposing offer/purchase tokens. Distinguish `observed offer`, `possibly eligible`, `user-verified`, and `confirmed active`.
4. **Preserve the payment gates**. Candidate discovery never automatically starts Steps 2–5, changes account, bypasses verification, applies a replacement/proration mode, or taps Subscribe.
5. **Verify with mocked offline fixtures first** (Windows + Linux + macOS), then review separately before any authorized real-device testing. Never run checkout in CI.

## Questions / blockers

- Establish third-party copyright/redistribution permission before any source-code import.
- Confirm supported SKU naming and product details from reliable, current documentation or authorized observation; do not hardcode unverified free-month/discount guarantees.
- Determine the existing `ultra0.py` read-only query interface and whether alternate SKUs can be passed without changing checkout behavior.
- Determine how to avoid polling storms, leaking offer tokens, stale reports, account mismatch or inadvertent paid transactions.
- The shared `dev` branch was observed **4 commits behind `main`** at branch creation. This independent research branch was based on latest `main`; refresh `dev` safely before opening a development integration PR. Do not merge this research branch straight to `main`.

No user account, purchase, emulator or live offer was tested as part of this research.
