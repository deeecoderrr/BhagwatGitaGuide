# Mobile App Parity Blueprint (Rork / AI Handoff)

This document is the single source of truth for building a mobile app that
matches current BhagwatGitaGuide web product behavior without re-implementing
web-template logic.

Use this with either API base:

- `/api/...`
- `/api/v1/...` (recommended for mobile)

---

## 1) Goal

Build mobile with full feature parity:

- guest ask flow + guest quota + guest history
- authenticated ask flow + threads + saved reflections
- verse reader + search + daily verse + quote art
- support + feedback + engagement/reminder prefs
- payment/subscription + plan gating
- sadhana enrollment flow

Core rule: backend owns business logic; mobile only handles UI/UX.

---

## 2) Backend-vs-Frontend Responsibility

Backend-owned (do not duplicate in mobile business logic):

- safety blocking (`safety_blocked`)
- quota evaluation (`429`, plan limits, deep limits, guest limits)
- plan enforcement (free/plus/pro)
- verse retrieval/reranking/fallback
- payment signature verification + plan activation
- ownership checks (history, conversations, reflections, support tickets)
- thread/message persistence for authenticated users
- guest session transcript + recent question state APIs

Frontend/mobile-owned:

- screen layout, animation, local loading states, navigation
- optimistic UX where desired (must still reconcile with API responses)
- copy/share UI wrappers (Web Share equivalent in native)

---

## 3) Canonical Feature Inventory

### Auth / Account

- `POST /auth/register/`
- `POST /auth/login/`
- `POST /auth/google/`
- `POST /auth/logout/`
- `GET /auth/me/`
- `PATCH /auth/profile/`
- `POST /auth/change-password/`
- `POST /auth/forgot-password/`
- `POST /auth/reset-password/confirm/`
- `POST /auth/plan/` (debug/local mock only)

### Onboarding + Plans

- `GET /starter-prompts/`
- `GET /plans/catalog/`

### Guidance

- `POST /guest/ask/` (no auth)
- `POST /ask/` (auth)
- `POST /follow-ups/` (auth)
- `POST /eval/retrieval/` (auth, debug)

### Guest session helpers

- `GET /guest/history/`
- `POST /guest/history/reset/`
- `GET /guest/recent-questions/`

### Reader / content

- `GET /daily-verse/`
- `GET /daily-verse/history/?days=&language=`
- `GET /chapters/`
- `GET /chapters/<chapter_number>/`
- `GET /verses/<chapter>.<verse>/`
- `GET /verses/search/?q=&limit=`
- `POST /mantra/` (auth)
- `GET /quote-art/styles/`
- `POST /quote-art/generate/`
- `GET /quote-art/featured/`

### Threads / history

- `GET /history/me/` (latest conversation-style history)
- `GET /history/<user_id>/` (owner check)
- `GET /conversations/?limit=&offset=`
- `POST /conversations/`
- `GET /conversations/<conversation_id>/messages/?limit=&offset=`
- `DELETE /conversations/<conversation_id>/`

### Retention / feedback / support

- `GET /feedback/`
- `POST /feedback/`
- `GET /saved-reflections/`
- `POST /saved-reflections/`
- `DELETE /saved-reflections/<reflection_id>/`
- `POST /support/`
- `GET /support/tickets/`

### Notifications / engagement

- `GET /engagement/me/`
- `PATCH /engagement/me/`
- `GET /notifications/preferences/`
- `PATCH /notifications/preferences/`
- `POST /devices/register/`
- `DELETE /devices/<device_id>/`

### Sharing / growth / community

- `POST /answers/share/`
- `POST /analytics/events/`
- `GET /analytics/summary/?days=` (staff only)
- `GET /community/posts/`
- `POST /community/posts/`
- `PATCH /community/posts/<post_id>/`
- `DELETE /community/posts/<post_id>/`

### Subscription / payments

- `GET /subscription/status/`
- `GET /payments/history/`
- `POST /payments/create-order/`
- `POST /payments/verify/`
- `POST /payments/status/` (mark order cancelled/failed for ledger)
- `GET /payments/checkout/bridge/` (HTML Razorpay bridge; pass `redirect_uri` = app deep link)
- `POST /payments/webhook/` (server-to-server only)

### Sadhana

- `GET /sadhana/programs/`
- `GET /sadhana/programs/<slug>/`
- `GET /sadhana/programs/<slug>/days/<day_number>/`
- `POST /sadhana/programs/<slug>/days/<day_number>/complete/`
- `GET /sadhana/me/`

---

## 4) Exact Integration Checklist (Call Order)

## A. App boot

1. Call `GET /health/`.
2. Read stored token (if present).
3. If token exists, call `GET /auth/me/`.
4. If `401/403`, clear token and switch to guest mode.
5. In parallel for home screen:
   - `GET /starter-prompts/`
   - `GET /plans/catalog/`
   - `GET /daily-verse/?language=en|hi`

## B. Guest mode flow

1. Restore guest state:
   - `GET /guest/history/`
   - `GET /guest/recent-questions/` (optional; already in history payload)
2. Guest ask submit:
   - `POST /guest/ask/` with `message`, `mode`, `language`, optional `guest_id`
3. Render response sections from payload.
4. On "new guest chat":
   - `POST /guest/history/reset/`

## C. Guest -> login/register migration

1. User authenticates via:
   - `POST /auth/register/` or `POST /auth/login/` or `POST /auth/google/`
2. Save token from response.
3. Call `GET /auth/me/` immediately.
4. Clear local guest transcript UI (or keep local read-only preview if desired).
5. Use authenticated thread APIs from now on:
   - `GET /conversations/`

Note: web flow clears guest transcript on login/register; mobile should mimic.

## D. Authenticated guidance flow

1. Load current threads: `GET /conversations/?limit=...&offset=...`
2. If user opens a thread:
   - `GET /conversations/<id>/messages/`
3. Ask submit:
   - `POST /ask/` with `message`, `mode`, `language`, optional `conversation_id`
4. Render returned `conversation_id` and update local active thread.
5. Optional follow-up chips:
   - use `follow_ups` from ask response
   - or request fresh via `POST /follow-ups/`

## E. Reader flow

1. Chapters list: `GET /chapters/`
2. Chapter detail: `GET /chapters/<n>/`
3. Verse detail: `GET /verses/<c>.<v>/`
4. Search: `GET /verses/search/?q=...`
5. Daily verse archive: `GET /daily-verse/history/?days=...&language=...`

## F. Save + feedback + support

1. Save reflection: `POST /saved-reflections/`
2. List saved: `GET /saved-reflections/`
3. Delete saved: `DELETE /saved-reflections/<id>/`
4. Feedback: `POST /feedback/`
5. Support submit: `POST /support/`
6. User support ticket history: `GET /support/tickets/`

## G. Notification setup

1. Register device token after login:
   - `POST /devices/register/` with `token`, `platform`
2. Load prefs:
   - `GET /notifications/preferences/`
3. Update prefs:
   - `PATCH /notifications/preferences/`
4. On logout/device unlink:
   - `DELETE /devices/<device_id>/`

## H. Subscription checkout (Plus/Pro)

1. Show pricing:
   - `GET /plans/catalog/`
   - `GET /subscription/status/`
2. Create order:
   - `POST /payments/create-order/` with `plan` and optional billing fields
3. Launch Razorpay native checkout using returned order payload.
4. After Razorpay success callback:
   - `POST /payments/verify/` with order/payment/signature
5. Refresh subscription state:
   - `GET /subscription/status/`
   - optional `GET /payments/history/`
6. Refresh auth snapshot if needed:
   - `GET /auth/me/`

## I. Sadhana purchase/access

1. List programs: `GET /sadhana/programs/`
2. View detail: `GET /sadhana/programs/<slug>/`
3. Create order for cycle:
   - `POST /payments/create-order/` with
     `{ "product": "sadhana_cycle", "program_slug": "<slug>" }`
4. Verify payment:
   - `POST /payments/verify/`
5. Access program days via sadhana endpoints.

## J. Practice workflow purchase (paid courses)

1. Load catalog: `GET /practice/workflows/` and detail `GET /practice/workflows/<slug>/`.
2. Use **`purchase_currency_options`** from the detail payload when both INR and USD
   exist; otherwise send the single supported `currency` from the API.
3. Create order: `POST /payments/create-order/` with
   `{ "product": "practice_workflow", "workflow_slug": "<slug>", "currency": "INR"|"USD" }`.
4. Open checkout: native apps typically use **`GET /payments/checkout/bridge/`** with
   order fields and `redirect_uri` pointing at the app (e.g. **`/payments/callback`**).
5. On return URL with Razorpay params: `POST /payments/verify/` then refresh
   `GET /practice/workflows/<slug>/` and `GET /practice/workflows/me/`.

---

## 5) Edge-case Handling Playbook

## Auth expiry (`401`/`403` on protected routes)

- Clear token.
- Route to guest-mode state.
- Keep unsent draft text locally.
- Re-run boot sequence (`/health`, `/starter-prompts`, `/plans/catalog`).

## Quota exceeded (`429`)

- Parse error body:
  - standard shape: `error.code`, `error.message`, `detail`
  - many ask responses also include snapshot fields.
- If authenticated:
  - show upgrade CTA + remaining-window context.
- If guest:
  - show sign-in CTA.
  - offer reset UI only for transcript (`guest/history/reset`), not quota bypass.

## Payment verification failure

- `create-order` success is not subscription activation.
- Only treat plan active after `POST /payments/verify/` succeeds.
- On verify failure:
  - show retry support path
  - keep polling `GET /subscription/status/` for short interval
  - offer `GET /payments/history/` view for audit

## Guest -> login transition

- After successful auth:
  - switch API auth mode to token
  - clear guest transcript UI in app
  - fetch real threads from `/conversations/`
- Do not merge guest session transcript into server conversations unless a new
  dedicated migration endpoint is introduced.

## Reader permissions with token

- Chapter/verse/quote-art token calls from free plan can return `403`.
- If token + free, either:
  - prompt upgrade, or
  - retry as same-origin browser-style route in web context (not applicable in
    native app). In native mobile, treat as gated content.

## Mixed error envelopes

- Most APIs use standardized error envelope.
- Some payment endpoints can return `{ "error": "..." }` string.
- Mobile error parser should support both formats.

---

## 6) Minimal Client State Model

- `authToken`: string | null
- `authUser`: result of `/auth/me/` | null
- `activeConversationId`: number | null
- `guestId`: string | null
- `guestHistory`: message[]
- `quotaSnapshot`: from ask/me responses
- `subscriptionStatus`: from `/subscription/status/`
- `notificationDeviceId`: from `/devices/register/`

---

## 7) Implementation Order (recommended)

1. Boot + auth + token lifecycle
2. Guest ask + guest history APIs
3. Auth ask + conversation APIs
4. Reader APIs + search + daily history
5. Saved reflections + feedback + support
6. Plans catalog + subscription status + checkout + verify
7. Notifications/devices + engagement prefs
8. Sadhana flow

---

## 8) QA Smoke List (must pass)

- guest ask works, history persists, reset clears transcript
- login switches to authenticated threads
- ask with `conversation_id` appends to same thread
- free token reader endpoint returns expected gate behavior
- payment verify actually changes subscription status
- device register/delete roundtrip works
- saved reflections CRUD roundtrip works

---

## 9) Notes for AI builders

- Prefer API contracts over parsing HTML from `chat-ui`.
- Do not copy web-template-only logic (animations, modal behavior, DOM fragments).
- Treat backend as authoritative for safety, quota, plan, and payment state.
- If adding fields, use additive response evolution to preserve mobile compatibility.
