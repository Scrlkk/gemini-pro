# Step 1 — Unified SKU and Offer Discovery

Step 1 includes **SKU inspection automatically**. There is only one action: **Check Device & Offers**. Do not click a separate SKU button or open a SKU Explorer window.

## Usage

1. Start ePlus AI Toolkit, select the intended Android device and Google Play account.
2. Click **Check Device & Offers** (Step 1). The existing checks verify the device/account and fetch the normal Pro offer listing.
3. After a successful **real, verified** Step 1, the toolkit also queries the following known ProductDetails SKUs **automatically**, using the same verified device:
   - `g1.2tb.ai.subs_variant`
   - `g1.play.20tb`
   - `g1.play.ai.pro`
   - `g1.30tb`
4. **SUPPORTED OFFERS · FIRST PHASE ONLY** shows observed offers that match an existing checkout step and have a zero-priced first phase.
5. The existing Steps **2, 3 and 4** remain in the step picker. The optional **Step 5** appears only when the primary Step 1 report returns its exact supported product/offer with a zero-priced first phase. Additional SKU results are inspect-only. The catalogue explicitly labels them **PLAY ACCOUNT UNVERIFIED** before displaying prices; the serial and stored account used for the callback only identify the original Step 1 session, not the active Play profile that produced these observations. They never populate the optional Step 5 choice.

## Supported operations and safety

The original Pro optional +6-month operation is only available as Step 5 when its exact product/offer is observed in the primary Step 1 report; it retains its original explicit approval and checkout preflight. Unknown discovered offers are **inspect-only** and never initiate a generic purchase. The guided checkout sequence ends at Step 4. SKU observations appear in the existing scrollable panel and do not authorize additional checkout steps. Use Stop SKU scan to cancel; Exit waits for cancellation.

Step 1's SKU check invokes `sku_check_runner.py` using a separate read-only Frida `queryProductDetailsAsync` script. It does **not** call `launchBillingFlow`, read a purchase token, switch accounts or automatically activate any plan. Finding a SKU, seeing a zero-priced phase, or seeing an offer ID **does not prove account eligibility, an active subscription, a free month or successful payment**. Verify terms and charges in Google Play before any optional checkout.

The SKU runner reuses `ultra0.get_target_frida_device` for strict device/PID mapping. The separate query-only JavaScript is intentional: unlike the existing checkout-capable billing script, it has no checkout or purchase operation. Offline tests verify both the shared lookup delegation and this isolation.

The candidate SKUs are a **bounded, known shortlist**, not an exhaustive Google Play catalogue, and returned offers may vary by region, time and account. GitHub Actions cannot confirm the device integration without a real authorized emulator.

New scans clear stale extra steps and SKU results. When the selected account/device changes, the old offer catalog is cleared so it cannot be mistaken for the current account.

## Historical CI screenshots and tests

See [PR #85](https://github.com/hoangsvit/google-ai/pull/85), the **Terminal UI previews** comment. GitHub Actions captures the actual running Textual dashboard with synthetic data and posts the images directly:

- `09-step1-sku-offers.png`: one Step 1 button, supported offers and read-only SKU metadata.
- `10-step1-sku-missing.png`: synthetic missing SKU and no-offer statuses.
- `11-step1-discovered-offers.png`: the supported optional Step 5 is visible in a synthetic scan; unsupported offers are not shown as extra steps.

Additional synthetic terminal previews cover Step 0 environment checks, account selection, Step 1 progress and failures, individual Step 2–5 approval and review screens, retry safety, and optional Step 5 selection. The 26 screenshots are captured from real Textual widgets; no emulator, purchase, or real account is used. CI validates expected labels before publishing.

Automated tests: `tests/test_sku_check.py`, `tests/test_offer_discovery.py`, plus the existing TUI, Linux, macOS and Windows regression suites.

## Source files

- `tui.py`: Step 1 workflow, automatic SKU candidate scan and supported offer display.
- `sku_check_runner.py`: bounded device-bound ProductDetails query.
- `sku_check_core.py`: validation, sanitized offer data and safe pricing display.
- `offer_discovery.py`: base-plan-aware deduplication and optional Step 5 metadata.
- `assets/frida/sku_query_readonly.js`: query-only Android Billing instrumentation.
