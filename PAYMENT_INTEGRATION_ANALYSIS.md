# Razorpay payment integration — reference

**Status:** Production-ready (Razorpay checkout, ledger, webhooks, native bridge).  
**Last reviewed:** 2026-04-27  
**Tests:** `PaymentIntegrationTests` and related cases in `guide_api/tests.py` — run `make test` for the current total count.

---

## 1. Products and flows

`POST /api/payments/create-order/` accepts `product` (default `subscription`):

| `product` | Extra body | Activates |
|-----------|------------|-----------|
| `subscription` | `plan`: `plus` \| `pro`, `currency`, billing fields | Plus/Pro on `verify` + webhook |
| `sadhana_cycle` | `program_slug`, `currency`, billing | Sadhana enrollment |
| `practice_workflow` | `workflow_slug`, `currency`, billing | `PracticeWorkflowEnrollment` |

**Practice workflow detail** (`GET /api/practice/workflows/<slug>/`) includes **`purchase_currency_options`** when the workflow has INR and/or USD prices configured (`purchase_price_minor_inr` / `purchase_price_minor_usd`).

**Ledger:** Every checkout creates or updates one **`BillingRecord`** per `razorpay_order_id` (`guide_api/models.py`). Metadata can include `purchase_kind` (`sadhana_cycle`, `practice_workflow`) plus `program_slug` / `workflow_slug`.

---

## 2. HTTP endpoints (`/api/` and `/api/v1/` mirror)

| Endpoint | Method | Auth | Role |
|----------|--------|------|------|
| `payments/create-order/` | POST | Yes | Create Razorpay order; upsert `BillingRecord` |
| `payments/verify/` | POST | Yes | HMAC verify; activate subscription / sadhana / workflow |
| `payments/webhook/` | POST | None | Razorpay `X-Razorpay-Signature`; `payment.captured` / `payment.failed` |
| `payments/history/` | GET | Yes | Paginated billing rows |
| `payments/status/` | POST | Yes | Client marks order failed/cancelled for ledger |
| `payments/checkout/bridge/` | GET | No | Minimal HTML Razorpay bridge for native `redirect_uri` flows |
| `subscription/status/` | GET | Yes | Plan + `latest_billing_record` + pricing matrix |

Implementation: **`guide_api/views.py`** (`CreateOrderView`, `VerifyPaymentView`, `RazorpayWebhookView`, `PaymentCheckoutBridgeView`, `PaymentHistoryView`, `PaymentStatusUpdateView`, `SubscriptionStatusView`). Routes: **`guide_api/urls.py`**.

---

## 3. Verify (`VerifyPaymentView`)

1. Resolves user (session / token / chat-ui session rules as elsewhere).
2. Validates **`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET`**, then HMAC-SHA256:  
   `message = f"{razorpay_order_id}|{razorpay_payment_id}"` vs `razorpay_signature`.
3. Loads **`BillingRecord`** for `razorpay_order_id`, then **`UserSubscription`** for the user.
4. **Order ownership:** If a billing row exists with `user_id` set, it must match the current user (stops cross-user verify). If the row has no `user_id`, `UserSubscription.razorpay_order_id` must still match. If there is **no** billing row, `subscription.razorpay_order_id` must match (legacy path).
5. Branches (first match wins): **sadhana** (metadata or session `pending_sadhana_orders`) → **practice workflow** (metadata or `pending_workflow_orders`) → **subscription**.
6. **Amount checks:** Sadhana and subscription paths compare **`BillingRecord.amount_minor`** (and workflow uses catalog price vs ledger) to expected catalog amounts. Wrong ledger amount → **400** `Order amount mismatch`.
7. **Subscription plan resolution:** Session `pending_subscription_plans`, request `plan`, then **`BillingRecord.plan`** (when metadata is not a sadhana/workflow purchase), default Pro.

This allows verify to succeed after a **new** `create-order` moved `UserSubscription.razorpay_order_id` forward, as long as the **billing row** for the completed order still belongs to the user.

---

## 4. Webhook (`RazorpayWebhookView`)

- Verifies body with **`RAZORPAY_WEBHOOK_SECRET`** (`X-Razorpay-Signature`).
- **`payment.captured`:** Resolves `BillingRecord` by `order_id`.  
  - **`practice_workflow`:** Activates enrollment and updates billing to **captured** only if webhook **amount** and **currency** match the workflow catalog price **and** the existing ledger row (`wf_amount_ok`). Otherwise skips activation; **`logger.info("razorpay_webhook_skip_practice_workflow_capture", extra=...)`**.  
  - **`sadhana_cycle`:** Same idea against **`_payment_amount_for_sadhana_cycle`** (`sad_amount_ok`); **`logger.info("razorpay_webhook_skip_sadhana_capture", ...)`** on skip.  
  - Else: subscription path (infer plan from amount where applicable).
- **`payment.failed`:** Marks billing row failed when `order_id` present.
- Always returns **`{"status": "ok"}`** on success path so Razorpay does not retry indefinitely.

---

## 5. Settings (`config/settings.py` / env)

- **`RAZORPAY_KEY_ID`**, **`RAZORPAY_KEY_SECRET`**, **`RAZORPAY_WEBHOOK_SECRET`**
- **`SUBSCRIPTION_PRICE_PLUS_INR`**, **`SUBSCRIPTION_PRICE_PLUS_USD`**, **`SUBSCRIPTION_PRICE_PRO_INR`**, **`SUBSCRIPTION_PRICE_PRO_USD`**
- Sadhana: **`SADHANA_CYCLE_PRICE_INR`**, **`SADHANA_CYCLE_PRICE_USD`**, **`SADHANA_CYCLE_DURATION_DAYS`**

See **`.env.example`** for placeholders.

---

## 6. Web (chat UI)

**File:** `guide_api/templates/guide_api/chat_ui.html` — **`initiatePayment`**, Razorpay Checkout.js, `POST /api/payments/create-order/` then `POST /api/payments/verify/` with CSRF. Upgrade UI supports Plus and Pro where applicable.

---

## 7. Mobile (Expo)

Native flows open **`GET /api/payments/checkout/bridge/`** with order fields and **`redirect_uri`** (e.g. app deep link **`…/payments/callback`**). The callback screen should **`POST /api/payments/verify/`** with Razorpay query params. Workflow checkout picks **currency** from API **`purchase_currency_options`** and locale heuristics when both INR and USD exist.

Repo: **`bhagavadgitaguide_mobile-main`** — see **`docs/MOBILE_APP_PARITY_BLUEPRINT.md`** and **`RELEASE_SMOKE_CHECKLIST.md`**.

---

## 8. Tests and docs

- **Tests:** `guide_api.tests.PaymentIntegrationTests` (subscription, webhook, sadhana, practice workflow, billing mismatch, stale `razorpay_order_id`, etc.).
- **Broader doc:** **`README.md`**, **`docs/DEVELOPER_GUIDE.md`** (billing sequence), **`docs/PRODUCTION_RUNBOOK.md`** (secrets + webhooks), **`docs/AI_AGENT_HANDOFF.md`** (API list).

---

## 9. Known gaps / backlog

- No automatic **subscription renewal** loop (single purchase extends `subscription_end_date`).
- No first-class **refund** or **chargeback** automation in-app.
- **Rate limiting** and Razorpay **IP allowlist** for webhooks are edge-layer concerns, not implemented in Django alone.

---

## 10. Security checklist

- [x] Verify and webhook signatures (HMAC-SHA256).
- [x] Authenticated verify; webhook uses shared secret only.
- [x] Billing row user match on verify when ledger exists.
- [x] Webhook amount/currency alignment for sadhana + practice workflow captures.
- [ ] Production: live keys, webhook URL, and log level so **`INFO`** skip lines are visible if you rely on them for support.
