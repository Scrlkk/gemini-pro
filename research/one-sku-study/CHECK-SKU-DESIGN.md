# Check SKU / SKU Explorer — implementation design

> **Implemented design supersedes this historical proposal (PR #85):**
> Step 1 has **one** `Check Device & Offers` button. Its successful verified
> offer check automatically queries the known ProductDetails SKU shortlist and
> lists SKU, offer/base plan and pricing phases in the **Available Offers** panel.
> No independent SKU Explorer button, modal, or Step 1A is exposed.
> Steps 2–4 remain fixed; new observations appear in the read-only catalog.
> The original optional Step 5 requires a matching primary Step 1 report and separate approval.
> See [Step 1 — Unified SKU and Offer Discovery](../../docs/SKU-EXPLORER.md).
> The remaining sections below are historical research notes, **not current UI instructions**.
>

**Historical proposal:** the current bounded read-only implementation is described in the note above; the remaining design notes are archival.

**Scope:** a manually initiated, bounded Google Play product-details inspection in the existing Textual dashboard. The process may attach to an authorized Android / Google One runtime, but must not request purchases, open a billing sheet, change accounts, modify subscription state or automatically install/repair Android tooling. No hidden subscription unlocks, and no changes to existing Steps 2–5.

## 1. Findings from the current main baseline

| Existing file | What it already does | Risk / decision |
| --- | --- | --- |
| `query_sku.py` | Attaches to Frida and overrides the product list in `ultra0.build_js("5x", True)` | Prints the offer token for zero-priced first phases, uses a script that also contains checkout functions, has a hard-coded Frida endpoint and does not enforce verified ADB device binding. **Do not reuse directly in TUI.** |
| `assets/frida/billing.js` | Queries `queryProductDetailsAsync`, selects a preferred offer and can launch/replace subscriptions | Contains `launchBillingFlow`, `queryPurchasesAsync`, purchase tokens and subscription-update branches. **Never use this as the new read-only payload.** |
| `ultra0.py` | Device/Frida integration, `build_js`, `run_trial`, `get_target_frida_device`, account handling, reports | Reuse safe validated **identity/device lookup concepts** only. Avoid importing execution paths that initialize or modify the device automatically. |
| `tui_core.py` | Stage/command routing, sanitized Step 1 offer display with *first phase only* | Put pure validation, result models, formatting and status mapping in a separate module. Do not change the meaning of Steps 0–5. |
| `tui.py` | Displays `Check Device & Offers`, Step 1 offers and account/device state | Put SKU Explorer beside the existing Step 1 results, not another paid step. Share the same busy/stop guards. |
| `research/one-sku-study/sku_research.py` | Offline SKU candidates and token-stripping first-phase projection | Keep as offline research prototype; extend or replace its output contract with **all pricing phases** only after unit tests. |

The input archive `one-sku-study.zip` has no verified redistribution license. Do not paste its third-party source or binaries into the repository. The product IDs and duration claims in it are discovery hypotheses, not authenticated Google entitlements.

**Important:** A source-level `LIST_ONLY=true` toggle in a JS program that still contains `launchBillingFlow` is less robust than a physically separate JS module that **does not implement any purchase method**.

## 2. Intended UX (Textual, Windows and macOS)

Keep the default `Check Device & Offers` action untouched. Add an opt-in `Advanced → SKU Explorer (read-only)` section inside Step 1.

```text
ePlus AI Toolkit                      Android: Connected | Play account: review
┌─ Workflow ─────────┐ ┌─ Step 1 — Available Offers / SKU Explorer ──────────────┐
│ 0 Environment      │ │ [Check Device & Offers]   [Advanced: SKU Explorer ▾]  │
│ 1 Available Offers │ │                                                            │
│ 2 Pro 12 months    │ │ Group: [AI Pro ▾]    Product ID: [g1.2tb.ai.subs_variant] │
│ 3 Pro +6 months    │ │ [Check SKU — read only]   [Clear]                         │
│ 4 Pro +6 months    │ │                                                            │
│ 5 Optional +6 mo.  │ │ Result: OBSERVED / NOT RETURNED / ERROR                 │
└────────────────────┘ │ SKU                 Offer ID       Initial | Renewal*   │
                        │ g1.2tb.ai...        example-id     0 USD   | unknown    │
                        │                                                            │
                        │ * Renewal shown only when returned as a distinct phase.     │
                        │ Listed metadata ≠ eligibility or subscription activation.  │
                        └────────────────────────────────────────────────────────────┘
```

These are **mock values**, never claimed to be current offers.

UI behavior:
- Three presets (AI Pro, Ultra, Custom) simply fill *candidate input*. Presets must not state "free" or "available".
- Limit to **10 explicit SKUs per click**, allow manual comma/newline-separated entry; no automatic dictionary brute-force, no all-SKU background discovery.
- Show result count, query time, selected device, masked/verification-state account indicator, and one row per returned offer. Show all returned pricing phases on selection, including `currency`, `billing_period`, `billing_cycle_count` and `recurrence_mode`.
- If Play account cannot be reliably identified, **do not query**, and show specific manual account-validation instructions. Never pick the first Google account automatically.
- `Check SKU` disabled during other steps, when Android/Frida is not ready or while another query runs. `Stop` only cancels the read-only checker and must detach its session; it has no relation to paid-step cancellation.
- At compact 90×20 render the condensed table and a scrollable details overlay; at 110×35 show a wider table. Maintain keyboard focus, no clipped buttons.
- The read-only results panel has **no Subscribe, Activate, Apply or Continue to checkout button**. Even a first-phase price of zero should only display `First phase: 0 [currency], eligibility unverified`.

## 3. Proposed files and responsibilities

| Target | Responsibility | In current branch? |
| --- | --- | --- |
| `research/one-sku-study/CHECK-SKU-DESIGN.md` | This architecture and security contract | Yes |
| `assets/frida/sku-query-readonly.js` | Dedicated query-only BillingClient script; no checkout APIs, no token emission | **Proposed** |
| `sku_check_core.py` | `validate_skus`, `sanitize_result`, typed result/status, full phase model, renderer | **Proposed** |
| `sku_check_runner.py` | Explicit device/Frida bridge, bounded query, lifecycle cleanup and safe transport | **Proposed** |
| `tui.py` | Advanced SKU Explorer controls, read-only results and state machine | **Proposed** |
| `tests/test_sku_check_core.py` | Input, phase, sanitization and freshness fixtures | **Proposed** |
| `tests/test_sku_check_runner.py` | Mocked device, timeouts, errors, cleanup and no-checkout tests | **Proposed** |
| `tests/test_sku_readonly_static.py` | Scan the dedicated JS and CLI command builder for prohibited purchase paths | **Proposed** |

Do not wire `sku_check_runner.py` to `query_sku.py`, `run_trial(...list_only=False)`, `confirm_zero`, `launch`, `launchWithStack`, or `--force`.

## 4. Exact query contract

Input command design (not yet implemented):

```sh
python sku_check_runner.py --serial <validated-adb-serial> \
  --sku g1.2tb.ai.subs_variant --json
```

There is deliberately **no** `--purchase`, `--checkout`, `--force`, `--stack` or `--subscribe` flag. The runner must refuse all unknown arguments.

Minimal JSON output shape (example, synthetic only):

```json
{
  "schema_version": 1,
  "status": "observed",
  "queried_at_utc": "2026-11-24T00:00:00Z",
  "items": [{
    "sku": "g1.example.product",
    "offer_id": "example-offer",
    "base_plan_id": "base-example",
    "phases": [
      {"price_amount_micros": "0", "currency": "USD", "billing_period": "P1M",
       "billing_cycle_count": 1, "recurrence_mode": 2},
      {"price_amount_micros": "19990000", "currency": "USD", "billing_period": "P1M",
       "billing_cycle_count": 0, "recurrence_mode": 1}
    ],
    "eligibility_verified": false,
    "subscription_active_verified": false
  }],
  "missing_skus": [],
  "errors": []
}
```

The example prices are **fake**; neither `USD 0` nor a returned offer means an eligible or active subscription.

**Allowed output fields:** version, status, timestamp, SKU, nonsecret offer/base-plan IDs, numeric pricing phase fields, bounded errors. **Forbidden output fields:** account/email, device serial, offer token, purchase token, auth headers, passwords, card/payment info, unredacted Frida payloads, raw Android databases, screenshots or customer-identifiable Google Play text.

Never infer the final renewal price from only the first phase; explicitly show `unknown` if no later phase was returned. Do not transform `price_amount_micros` into a `$` value unless the currency is **explicitly returned**.

Status semantics:
- `observed`: one or more ProductDetails offer rows returned for the requested SKU at this instant; **not verified eligibility**
- `no_offers`: product details returned but no subscription offer rows
- `not_returned`: SKU absent from successful query; not proof that product does not exist
- `account_unverified`: active Play identity not established; no query executed
- `device_not_ready`, `billing_unavailable`, `timeout`, `query_error`, `cancelled`: explicit failures
- `stale`: result no longer fresh; cannot authorize or unlock anything

## 5. Query-only implementation constraints

JavaScript payload must contain only:
1. Context and Google Play Billing client setup;
2. `QueryProductDetailsParams` for **explicit** requested `SUBS` SKUs;
3. `queryProductDetailsAsync` and callback;
4. Enumerating `ProductDetails.getSubscriptionOfferDetails()`, base plan ID, offer ID and **every** pricing phase;
5. Redacted, bounded messages back to Python; clean `endConnection()`.

Source-level hard prohibitions in this dedicated payload:
- `launchBillingFlow`, `BillingFlowParams`, `setOfferToken`, `setOldPurchaseToken`, `queryPurchasesAsync`, `input tap`, `Subscribe`, `Purchase.getPurchaseToken`.
- No `offerToken` reporting, even in Debug.
- Do not depend on changing the existing mutable `LIST_ONLY` flag in `billing.js`.

Runtime:
- The user must explicitly select one ADB device; validate the serial and exact `com.google.android.apps.subscriptions.red` PID belongs to it. Reject ambiguity/disconnect/change.
- Validate and freeze the active Google Play account where possible. Do not switch/add/sign in accounts. Recheck if the run crosses a device/account change; suppress the result if uncertain.
- Do not silently run `ensure_network`, `ensure_module_apk`, `ensure_frida_server`, device setup, proxy reset or Play Store restart as part of Check SKU. If prerequisites are absent, report them.
- A live Frida query **does instrument the process**; "read-only" here means no requested **billing** mutation, not a promise of zero operational side effects on Android. Obtain explicit user initiation and keep the session bounded.
- Budget: 10 product IDs max per request; 30-second timeout, one active request, no automatic retries, at least 60 seconds between consecutive requests per device. No multi-account loop. A failed request never falls through to a checkout code path.
- Always detach Frida and release handles in `finally`; avoid outputting raw exception payloads or tokens.

## 6. Migration phases

### Phase A — safe core (no device)
- Extend existing offline sample parser to support ordered, multi-phase pricing and explicit `currency`, preserving unknowns.
- Add SKU allowlist/length, max count, JSON schema, fixture redaction and command-builder tests.
- Add tests proving that untrusted fields like `token`, `email`, `purchaseToken`, `password` never reach CLI logs, report or TUI.
- Document feature limitations. This phase is safe to run in CI.

### Phase B — isolated live query
- Implement the dedicated minimal Frida JS with **zero purchase methods**.
- Implement a runner with explicit Android/Frida device binding and fail-closed account verification, but no setup/recovery mutation.
- Mock `frida`, `adb`, callbacks, timeouts and disconnection; CI must not contact a real Google account or subscription.
- Manual test on a personally authorized rooted device **only** after code review; no checkout.

### Phase C — TUI integration
- Add the Advanced SKU Explorer panel and use a worker/subprocess protocol to avoid blocking UI.
- Ensure cancelling/closing query cannot trigger existing Step 2–5 approval flow. A SKU result never updates `_offer_check_ready` or `_initial_offer_ready`, which are currently used for paid-step gating.
- Preserve existing Step 1 and Steps 2–5 output and report schemas.
- Test compact and regular terminal sizes; test keyboard shortcuts and simultaneous actions; update end-user guides in all supported locales once UI actually ships.

### Phase D — review
- Open a focused Draft PR to `dev` only after `dev` is safely synchronized with `main` (at design time `dev` was four commits behind).
- Run offline Python/JS static tests on Linux/Windows/macOS as applicable; green mocks never prove real Play availability.
- Promote to `main` only in a separate reviewed PR. Do not auto-merge this research branch.

## 7. Acceptance criteria / fail-closed tests

- [ ] `Check SKU` never invokes `launchBillingFlow` or any subscription update, even with malformed/hostile inputs.
- [ ] Dedicated JS contains no checkout, subscription-replacement or purchase-token access.
- [ ] No offer, purchase, account or payment token reaches console/JSON/UI/debug logs.
- [ ] No account switching, device guessing, background scan or silent Android setup.
- [ ] Missing device/Frida/account, timeout, cancellation and Google API error yield clear harmless statuses.
- [ ] Multiple pricing phases render in correct order with precise returned currency; unknown renewal stays unknown.
- [ ] SKU query cannot set Step 1 paid-step readiness or automatically launch Steps 2–5.
- [ ] All unit/integration tests pass without Android/Google Play; device verification reported separately.
- [ ] Original Google AI Pro Step 1 and payment approval gates behave unchanged.
- [ ] Third-party code is not copied without confirming license/permission.

## 8. References

- Android Developers, Integrate the Google Play Billing Library:
  https://developer.android.com/google/play/billing/integrate
- Android Developers, subscription compatibility:
  https://developer.android.com/google/play/billing/compatibility
- Source of research ZIP:
  https://drive.google.com/file/d/1Ne4izEP3gUTrbKYVrMxVyWFmRoL4BoT7/view

**No real SKU availability, pricing, eligibility or account changes were verified during this design.**
