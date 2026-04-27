# Bhagwat Gita Guide - Progress Tracker

Last updated: 2026-04-25

## Completed

- Added dedicated guided meditation planning blueprint:
  - `docs/MEDITATION_UX_BLUEPRINT.md`
  - defines 30-min canonical sequence (settling + pranayam + yoga + mantra +
    affirmation + living-the-mantra + bhakti + close)
  - defines web/mobile IA, screen-by-screen flow, MVP implementation order,
    and integration points with ask/chat flow

- Mobile API parity expansion completed (no need to replicate web-only logic in
  Android/iOS clients):
  - added account/profile endpoints:
    - `PATCH /api/auth/profile/`
    - `POST /api/auth/change-password/`
    - `POST /api/auth/forgot-password/`
    - `POST /api/auth/reset-password/confirm/`
  - added conversation/thread APIs:
    - `GET|POST /api/conversations/`
    - `GET /api/conversations/<id>/messages/`
    - `DELETE /api/conversations/<id>/`
  - added guest-mode session APIs:
    - `POST /api/guest/ask/`
    - `GET /api/guest/history/`
    - `POST /api/guest/history/reset/`
    - `GET /api/guest/recent-questions/`
  - added onboarding/paywall metadata APIs:
    - `GET /api/starter-prompts/`
    - `GET /api/plans/catalog/`
  - added notification + device APIs:
    - `GET|PATCH /api/notifications/preferences/`
    - `GET /api/devices/` (active devices)
    - `POST /api/devices/register/`
    - `DELETE /api/devices/<id>/`
  - **Push delivery:** `guide_api/push_reminders.py` + `manage.py send_push_reminders`
    (Expo Push API); `UserEngagementProfile.last_reminder_push_date` dedupes one send
    per local calendar day; mobile registers Expo tokens via `expo-notifications`.
  - added reader/mobile helpers:
    - `GET /api/daily-verse/history/`
    - `GET /api/verses/search/`
    - `GET /api/support/tickets/`
  - added `NotificationDevice` model + migration:
    `guide_api/migrations/0025_notificationdevice.py`
  - tests expanded and passing after parity pass (`make test`: 271 tests)

- **ITR Summary Generator merge (same repo / `manage.py`):**
  - Optional ITR stack controlled by **`ITR_ENABLED`** (default on); isolation in
    **`config/settings_itr.py`** (`register_itr_settings`), URLs in **`config/urls.py`**
    + **`config/urls_itr.py`** under **`ITR_URL_PREFIX`** (default **`/itr-computation/`**).
    Shared **`User`** with Gita; separate ITR models (`apps.documents`, `apps.exports`,
    `apps.billing`, …).
  - **`guide_api` compatibility:** **`_session_auth_login()`** for chat-ui when
    multiple auth backends (allauth); **`CanonicalHostRedirectMiddleware`** also treats
    **`*.onrender.com`** like **`*.fly.dev`** for canonical redirects.
  - **Retention:** **`ExportedSummary.expires_at`** / **`pdf_purged_at`**;
    **`purge_expired_exports()`** + **`purge_itr_retention`** management command;
    **`ITR_OUTPUT_RETENTION_HOURS`**, **`ITR_DELETE_INPUT_AFTER_EXPORT`**;
    **`Document.uploaded_file`** nullable after input purge; workspace/detail/list UX
    for expired PDFs; marketing/upload/export copy via **`{% itr_output_retention_hours %}`**.
  - **Deps:** `django-allauth`, `django-rq`, redis, reportlab, weasyprint, PyJWT in
    **`requirements.txt`** when ITR is used.
  - **ITR OAuth (django-allauth):** **`config/settings_itr.py`** adds
    **`apps.accounts.context_processors.google_oauth`** and
    **`account_profile`** to **`TEMPLATES`** so **`google_oauth_configured`** works
    on ITR pages; **`GOOGLE_OAUTH_CONFIGURED`** derives from **`GOOGLE_CLIENT_ID`**
    or **`GOOGLE_OAUTH_CLIENT_ID`** plus **`GOOGLE_CLIENT_SECRET`**. Account and
    marketing templates (**`login`**, **`signup`**, **`home`**, **`pricing`**) expose
    **Continue with Google** with a safe **`next`** back to the ITR workspace or
    checkout when OAuth is configured.
  - **WeasyPrint on Fly/Docker:** the production **`Dockerfile`** installs OS
    packages for **Pango, cairo, GLib/GObject, GDK-Pixbuf, shared-mime-info**,
    and baseline fonts—**`pip install weasyprint` is not sufficient** in slim
    images. Redeploy after Dockerfile changes; see **`docs/PRODUCTION_RUNBOOK.md`**
    if production shows **`libgobject`** / missing shared library errors.
  - **PDF export UI:** **`apps.exports.views.export_pdf`** only generates via
    **WeasyPrint**; the ReportLab button/path was removed from
    **`templates/exports/export_confirm.html`**. **`apps.exports.pdf_render`** remains
    for **`apps/exports/tests/test_pdf_export.py`** and reuse.
  - **Filed JSON importer:** `apps/extractors/json_pipeline.py` supports filed
    **ITR-1**, **ITR-3**, and **ITR-4** JSON: tax/refund, banks, TDS; ITR-1 maps
    salary / u/s 16 / OS splits / filing meta / CYLA defaults; **ITR-4** maps
    `IncomeDeductions`, **Schedule BP** (44AD turnover + presumptive + trade
    name), IFD/SAV OS buckets, salary stubs (incl. `EntertainmntalwncUs16ii`
    typo), and root-level `TaxComputation` / `TDSonSalaries`; **Weasy**
    computation PDF adds salary/House property/Chap VI-A/tax detail and **44AD**
    lines when Schedule BP data exists.

- **Comments & replies** (`CommunityPost`): **`/community/`** full page + **`/api/community/posts/`**
  API (**`/api/v1/`** mirrored). Chat UI **`/api/chat-ui/`**: redesigned header (home pill,
  clustered language + CTAs), nav **Comments / टिप्पणियाँ** → anchor to embedded
  **`#community-preview-discussion`** (recent threads via fetch, reply + **Load more**).

- Chat UI **logout** now routes through `_render_chat_ui()` so **`google_oauth_client_id`**
  and related context are preserved; the Google button and GSI script render again
  after logout (`guide_api/views.py::_handle_logout`, regression test).

- **Google Sign-In popup blank screen (production):** set
  `SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"` so GIS popups
  can `postMessage` the opener (Django’s default `same-origin` COOP breaks that).

- Chat UI **naam japa / Hari śaraṇam** sanctuary block: expandable calm-glow panel
  under the hero with Hindi + English copy, pronunciation play control (`hari-saranam-chant.mp3`
  in static audio), reduced-motion respect,
  and GSAP entrance (`guide_api/templates/guide_api/chat_ui.html`).

- Tightened open API surface:
  - `POST /api/eval/retrieval/` now requires **authentication** (retrieval work
    no longer anonymously callable)
  - `POST /api/mantra/` now requires **authentication**
  - **Quote art** JSON routes (`quote-art/styles`, `generate`, `featured`) use
    the same **`GitaBrowseAPIPermission`** rule as chapter browse (browser OK
    without token; Free **token** → `403`)

- Gita browse API access control + docs sync:
  - `GET /api/chapters/`, `GET /api/chapters/<n>/`, `GET /api/verses/...` (and
    `/api/v1/` aliases) use `GitaBrowseAPIPermission` (`guide_api/permissions.py`):
    browser requests **without** `Authorization: Token` remain allowed (chat UI
    reader for guests and signed-in users); **token-authenticated** calls require
    **Plus or Pro**, **Free** plan tokens receive `403` to limit external API
    abuse on hosted infrastructure
  - regression tests: anonymous GET still `200`, token+Free `403`, token+Pro `200`
  - `README.md`, `AGENTS.md`, `docs/AI_AGENT_HANDOFF.md`, `docs/USER_GUIDE.md`,
    `docs/DEVELOPER_GUIDE.md` updated to describe the policy

- Chat UI guest parity (landing):
  - guests see **Today's Signal** on the guest home hero (same card behavior as
    signed-in; driven by `/api/daily-verse/`)
  - **Read Gita** is available from top nav and landing cards for guests, not
    only signed-in users (shared descriptive copy for all users)

- Ask/chat guidance quality pass:
  - Cost controls (default-on / opt-in): Django `cache` for duplicate query embeddings
    (`OPENAI_QUERY_EMBEDDING_CACHE_*`), optional `OPENAI_VERSE_RELEVANCE_MODEL` /
    `OPENAI_VERSE_SUGGEST_MODEL` for short JSON passes, `MAX_CONVERSATION_CONTEXT_*`
    to cap guidance prompt history size.
  - Retrieval alignment: `verse_embedding_document()` in `services.py` is the single
    source for verse embedding text (`embed_gita_verses`); query embeddings use
    `interpret_query()`-enriched text (`OPENAI_QUERY_EMBEDDING_ENRICHED`, default on).
    New `integrity` theme + priors for ethics/professional language. Re-run
    `embed_gita_verses --overwrite` (and pgvector sync) after changing embedding text.
  - Post-retrieval `refine_verses_for_guidance()`: commentary-aware relevance LLM
    (`_validate_and_correct_verses`) can swap refs, return no verse
    (`no_appropriate_verse`), or run optional `_suggest_verse_refs_llm` when empty;
    wired in `_run_guidance_flow` and guest chat. Flags: `DISABLE_VERSE_RELEVANCE_LLM`,
    `DISABLE_LLM_VERSE_SUGGEST_WHEN_EMPTY`. Verse-optional answers: empty context
    allows `verse_references=[]` with grounding that forbids sneaked `chapter.verse`
    in prose; professional/legal heuristic adds non-legal framing. Principle-only
    fallback when the main LLM fails with no verses.
  - `build_guidance` prompts: parent-like compassionate tone, strict on-topic rules,
    separate instructions for `knowledge_question` vs life-guidance, optional
    `related_verse_references` in JSON for LLM-filtered related verses
  - `GuidanceResult.related_verses_refs` + `_related_verses_payload_for_response` in
    views (API + chat UI) to honor LLM picks or fall back to `get_related_verses`
  - `build_verse_explanation` prompts: clearer Krishna–Arjuna "why," commentary synthesis
  - Ambiguous intent routing: **heuristic-first** (incl. two-word “help me” →
    `life_guidance`); optional intent JSON LLM when `DISABLE_INTENT_LLM_REFINEMENT=false`
    (default **skips** it for cost/latency; turn off disable for edge-case quality)

- SEO intent expansion against "Gita GPT / Ask Gita / Bhagavad Gita AI" search demand completed:
  - inspected `gitagpt.org` and found its strongest advantage was not technical SEO depth,
    but exact-match query coverage in homepage title/description for terms users search:
    `gitagpt`, `gita gpt`, `ask gita`, and `bhagavad gita ai`
  - updated our public SEO index page title and meta description to cover the same search
    intent cluster more naturally, without low-quality keyword stuffing
  - added optional `meta keywords` support to SEO landing pages and wired it into both
    the public index page and topic pages
  - expanded homepage structured data with `alternateName` entries:
    `Ask Bhagavad Gita`, `Ask Gita`, `Bhagavad Gita AI`, `Gita GPT`
  - added a visible intent-alignment content strip on the SEO index page so the phrases
    people search also appear in indexable body copy
  - added FAQ content + FAQPage schema on the SEO index page so Google gets explicit
    answers around "Is this a Bhagavad Gita AI / Gita GPT style app?"
  - this should help us compete for adjacent branded/generic searches while keeping the
    page readable and aligned with the actual product

- SEO long-tail expansion completed:
  - added five more public Bhagavad Gita topic landing pages, each with both
    English and Hindi copy:
    - fear of failure
    - purpose
    - discipline
    - stress
    - anger
  - each page now has:
    - dedicated title/description
    - localized hero copy
    - localized problem points
    - starter question
    - relevant verse set
    - FAQ content
  - updated public routing and sitemap generation so new SEO pages are
    automatically exposed to Google
  - added a new "Most Searched Bhagavad Gita Verses" section on the SEO index
    page for famous, high-interest verses like:
    - 2.47
    - 2.48
    - 4.7
    - 6.5
    - 18.66
  - each verse spotlight now includes:
    - why people search it
    - visible indexable copy
    - direct CTA into the full app with prefilled verse-oriented prompts
  - expanded structured data with an `ItemList` for popular verse spotlights to
    strengthen search understanding around famous verse intent

- Search-intent question archive inspired by high-traffic Q&A sites completed:
  - analyzed `gotquestions.org` and identified the most transferable growth
    pattern: a large, crawlable archive of plain-language question intent with
    strong internal linking
  - implemented a Bhagavad Gita equivalent public archive page:
    `/frequently-asked-bhagavad-gita-questions/`
  - added English and Hindi question clusters across:
    - anxiety and overthinking
    - career and purpose
    - relationships and anger
    - discipline and self growth
  - each listed question links directly into the full app with a prefilled ask,
    turning search intent into usable product entry points
  - archive page includes:
    - localized metadata
    - visible question-rich content
    - FAQ schema
    - ItemList schema
    - backlinks to all major topic landing pages
  - sitemap now includes the archive route for better crawl discovery

- Daily verse hub completed:
  - promoted the existing daily-verse API logic into reusable helpers so both
    API consumers and public landing pages use the same deterministic
    day-seeded verse selection
  - added a new public route:
    `/daily-bhagavad-gita-verse/`
  - added English and Hindi daily-verse hub rendering with:
    - today's verse
    - compact meaning
    - reflection
    - recent 7-day history
    - deep-link CTA into the full app with verse-prefilled prompts
  - added structured data (`CollectionPage` + `ItemList`) so search engines can
    understand the page as a daily verse archive / recency hub
  - linked the daily verse hub from the main SEO index and added it to the
    sitemap for crawl discovery

- Custom domain HTTPS hardening completed:
  - identified that `https://askbhagavadgita.co.in/` had a valid TLS
    certificate, but the live response was still missing strict HTTPS headers
    that help browsers consistently treat the site as secure
  - enabled `MixedContentProtectionMiddleware` in Django middleware so
    production responses now emit a CSP with:
    `upgrade-insecure-requests; block-all-mixed-content`
  - enabled HSTS in production with preload-friendly settings:
    - `SECURE_HSTS_SECONDS=31536000`
    - `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`
    - `SECURE_HSTS_PRELOAD=True`
  - tightened referrer policy to `strict-origin-when-cross-origin`
  - this ensures browsers learn to use HTTPS for the domain, prevents accidental
    mixed-content subresource loads, and reduces "Not Secure" behavior on the
    new custom domain

- Production guest chat resilience improved:
  - identified that guest-mode prod asks could blank back to the landing state
    because the server was hitting `500` during quota settings reads on Fly
  - hardened `_request_quota_settings()` with a short-lived in-process cache
    and safe fallback to env defaults when the admin quota singleton lookup is
    temporarily unavailable
  - this prevents a transient Neon/Fly latency spike from crashing guest chat
    and dropping the visible transcript

- Quotas re-enabled by default:
  - switched `DISABLE_ALL_QUOTAS` default posture back to `false`
  - restored normal guest and signed-in quota behavior as the standard runtime
    mode
  - kept the global quota-off switch available for temporary operational use
    when needed

- Global quota switch-off added:
  - introduced `DISABLE_ALL_QUOTAS` setting so guest and signed-in ask caps can
    be disabled cleanly without rewriting individual limit values
  - when enabled, guest ask caps are off and plan daily/monthly/deep monthly
    quota enforcement returns unlimited
  - this leaves the rest of the product intact while temporarily removing quota
    friction

- Response quality defaults rebalanced upward:
  - increased per-plan LLM output caps to improve answer completeness:
    - Free: 500
    - Plus: 800
    - Pro: 1200
  - increased per-plan retrieval context verse caps so the model sees more
    relevant material before generating:
    - Free: 3
    - Plus: 5
    - Pro: 6
  - quota and monetization rules remain unchanged; only quality-oriented
    generation defaults were relaxed

- Guest quota now resets daily per browser:
  - root cause was guest mode using `GuestChatIdentity.total_asks` as a
    lifetime cap, so a guest browser stayed blocked forever after hitting 3 asks
  - added per-browser daily fields on `GuestChatIdentity`:
    `daily_asks_used` and `daily_asks_date`
  - guest quota snapshot and enforcement now reset automatically on a new local
    day while still preserving `total_asks` for lifetime analytics
  - same browser can now ask again the next day in guest mode
  - migration added: `0021_guestchatidentity_daily_asks_date_and_more`
  - validated with `manage.py migrate`, focused guest reset tests, and full
    suite: 136 tests passing

- Chat UI membership plan desync after successful payment fixed:
  - root cause was split auth state between Django's authenticated
    `request.user` and the custom `chat_ui_auth_username` session key
  - this could show a verified PLUS/PRO billing record while the sidebar plan
    card still rendered `Free`
  - chat-ui now resolves one effective user for quota, plan, and billing
    context: explicit `chat_ui_auth_username` wins, and Django `request.user`
    is used only as a fallback
  - chat-ui register/login now also call Django `login()` so browser auth state
    and chat-ui session state stay aligned
  - chat-ui logout now calls Django `logout()` in addition to clearing the
    custom session keys
  - added regression test covering an authenticated browser session without the
    custom chat-ui session username to ensure paid plan context still renders
  - added regression coverage for the exact stale-browser-user case where
    payment APIs must prefer `chat_ui_auth_username` over an older Django
    authenticated user
  - validated with `manage.py check` and full suite: 135 tests passing

- Billing ledger for Tally/invoice export completed:
  - added `BillingRecord` model as a single invoice-ready row per Razorpay
    order/payment
  - stores billing identity, GST/export classification, country details,
    currency, amount, plan, payment IDs, and status transitions
  - checkout now captures billing details from the membership panel before
    opening Razorpay
  - `POST /api/payments/create-order/` now creates/updates the billing row at
    order creation time
  - `POST /api/payments/verify/` now marks the same billing row as verified and
    attaches the Razorpay payment id
  - `payment.captured` and `payment.failed` webhooks now update the same row so
    the export table remains the single source of truth
  - Django admin now exposes `BillingRecord` with filters/search plus CSV export
    for Tally-friendly download
  - added authenticated `GET /api/payments/history/` so users/support flows can
    inspect recent billing rows without going through Django admin
  - `GET /api/subscription/status/` now includes `latest_billing_record` for
    the signed-in user
  - membership panel now shows the latest payment/billing snapshot after a
    checkout attempt
  - validated with `manage.py check` and full suite: 130 tests passing

- Production Razorpay build fix completed:
  - added missing `razorpay` package to `requirements.txt` so Fly production
    installs the SDK during deploy
  - `CreateOrderView` now returns a clean `503` JSON error if the payment SDK is
    missing instead of crashing with an HTML 500
  - validated with `manage.py check` and full suite: 133 tests passing

- Unified quota control in admin (single place) completed:
  - extended `RequestQuotaSettings` singleton to manage all quota knobs:
    - guest: enabled + ask limit
    - free: daily + monthly + deep-mode toggle
    - plus: daily enabled/limit + monthly + deep monthly
    - pro: daily enabled/limit + monthly + deep monthly
  - runtime quota resolvers now read admin singleton first and fall back to
    settings only if singleton is missing
  - chat UI `plan_limits` now reflects admin-controlled values
  - sidebar display now correctly shows unlimited Pro deep when configured
  - migration applied: `guide_api.0019_requestquotasettings_free_deep_mode_enabled_and_more`
  - singleton data aligned to current defaults and validated
  - validated with full suite: all 136 tests passing

- Geo-aware pricing display + checkout currency enforcement completed:
  - India users now see/pay in INR only; non-India users now see/pay in USD only
    when country headers are available
  - server now enforces billing currency in `POST /api/payments/create-order/`
    based on detected country (prevents client-side currency spoofing)
  - unknown-country fallback remains backward-compatible (defaults to INR unless
    explicit valid currency is provided)
  - membership pricing UI now renders a single currency per user region
  - India launch pricing lowered while keeping USD unchanged:
    - Plus: ₹199 (USD unchanged at $3.49)
    - Pro: ₹499 (USD unchanged at $8.49)
  - validated with full suite: all 132 tests passing

- Cost-safety pricing + deep-mode enhancement pass completed:
  - updated paid plan pricing defaults to launch-safe levels:
    - Plus: ₹299 / $3.49 (`SUBSCRIPTION_PRICE_PLUS_INR=29900`, `SUBSCRIPTION_PRICE_PLUS_USD=349`)
    - Pro: ₹699 / $8.49 (`SUBSCRIPTION_PRICE_PRO_INR=69900`, `SUBSCRIPTION_PRICE_PRO_USD=849`)
  - deep monthly caps aligned to new matrix:
    - Plus deep monthly: 40
    - Pro deep monthly: 180
  - added cost guardrails in settings and environment defaults:
    - output token caps by plan (`MAX_OUTPUT_TOKENS_FREE/PLUS/PRO`)
    - context-verse caps by plan (`MAX_CONTEXT_VERSES_FREE/PLUS/PRO`)
    - input hard cap (`MAX_ASK_INPUT_CHARS`) and other ask safety caps
  - wired plan-aware limits into runtime ask flow:
    - authenticated users now use plan-specific retrieval context limits
    - authenticated users now use plan-specific `max_output_tokens`
    - guest flow now uses Free-plan context and output caps
  - deep insights payload extended:
    - Plus/Pro deep now include `historical_context_from_mahabharata`
    - Pro deep now additionally includes `deep_verse_commentary`
  - deep insights UI now renders these new fields in chat response cards
  - `.env.example` updated to match all new defaults and pricing values
  - validated with full test suite: all 132 tests passing

- Mode + plan differentiation pass completed (Free/Plus/Pro clarity):
  - deep mode is now locked for free users by default
    (`ENABLE_FREE_DEEP_MODE=false`)
  - deep limits updated to product decision defaults:
    - plus deep monthly = 50
    - pro deep monthly = unlimited when `ASK_LIMIT_PRO_DEEP_MONTHLY=0`
  - API and chat-ui now enforce guest/free deep lock with clear upgrade messaging
  - deep responses now include tier-aware `deep_insights` payload:
    - Plus deep: spiritual principle, modern application, meditation practice,
      contemplative prompts
    - Pro deep: all Plus deep insights plus commentary links,
      cross-verse links, meditation program suggestion, custom journal prompts,
      and priority-response marker
  - chat-ui settings and membership copy updated to show the exact
    Free/Plus/Pro matrix and deep-mode availability
  - regression coverage added for deep lock and plus/pro deep behavior;
    full suite passing (132 tests)

- Pricing matrix accuracy audit + copy corrections completed:
  - executed comprehensive audit comparing pricing matrix claims against
    backend implementation
  - identified and corrected 4 copy/code misalignments:
    1. Removed "Simple" qualifier from quota descriptions ("200 questions/month"
       instead of "200 Simple questions/month", etc.) because monthly quotas
       track total asks across both simple and deep modes, not mode-split
    2. Changed "Learn from 50+ Starter Journeys" to "Explore example questions"
       (only 4 starter prompts exist in code)
    3. Changed "Save this session only" (Free) to "Guest sessions are temporary"
       (clarifies guest behavior without overpromising)
    4. Removed "priority response" tag from Pro tooltip (only a metadata flag,
       no actual queue prioritization system yet)
  - corrected copy in both landing pricing grid and membership panel matrices
  - validated changes with full test suite: all 132 tests passing
  - ensures zero false promises about plan features delivered to users

- Chat UI reorganization for clarity completed:
  - removed "Try Another Approach" modal from active chat area to keep
    conversation stream clean and focused on responses only
  - mode switching (Quick Guidance ⚡ | Deep Reflection 🔍) moved entirely to
    sidebar "Approach" selector for persistent, uncluttered access
  - "How it works" 3-step guide remains on landing page only (displayed when
    no active conversation exists)
  - pricing matrix kept on landing page with path-choice cards (Quick/Deep/Learn)
  - result: cleaner chat UX with mode toggles always accessible in sidebar
    without interrupting response flow
  - validated with full test suite: all 132 tests passing

- Free plan monthly quota cap added:
  - Free users previously showed "Unlimited monthly" which was confusing with
    a 3/day daily cap
  - added ASK_LIMIT_FREE_MONTHLY setting (default: 100/month) to provide
    explicit monthly ceiling for Free users
  - updated `_plan_monthly_limit()` to return Free monthly cap instead of None
  - quota UI now correctly displays "98/100" for Free monthly instead of
    "Unlimited"
  - Free plan now has clear dual constraints: 3/day AND 100/month
  - updated Free pricing matrix to display both limits for transparency
  - all daily/monthly quota checks now consistent across Free/Plus/Pro
  - comprehensive verification completed:
    - FREE: 3/day limit, 100/month limit, deep mode locked
    - PLUS: unlimited daily, 200/month limit, 50 deep/month, tier-aware insights
    - PRO: unlimited daily, 500/month limit, unlimited deep, pro_advanced features
  - validated with full test suite: all 132 tests passing

- Landing page reorganization completed:
  - removed "How it works", guidance path cards, and pricing matrix from
    landing page to reduce visual clutter and improve quick-action focus
  - moved all educational content to sidebar as collapsible "Help" accordion
  - landing page now shows: hero title, subtitle, quick action buttons
    (Ask Question, Read Gita, Share), and growth sharing section only
  - users can explore guidance paths and pricing details by expanding the
    sidebar Help section instead of scrolling through landing content
  - result: faster path to asking questions, educational content still
    discoverable but out of the primary flow
  - validated with full test suite: all 132 tests passing

- Tier-specific payment checkout flow synced (Plus + Pro):
  - `/api/payments/create-order/` now accepts selected paid tier and maps
    amount/currency by plan
  - `/api/payments/verify/` now activates selected tier (plus/pro) instead of
    forcing pro
  - `payment.captured` webhook now infers tier from captured amount/currency
  - chat-ui upgrade panel now exposes separate Plus and Pro checkout buttons
  - subscription status pricing payload now includes per-plan pricing matrix
    while retaining legacy top-level pricing keys
  - added regression coverage; full suite passing (128 tests)

- Monetization quota refactor (cost-aware) completed in runtime gates:
  - added `plus` plan support in model choices and plan-update serializer
  - introduced daily + monthly + deep-mode quota settings in config
  - centralized quota snapshot + violation evaluation for API and chat-ui
  - aligned `/api/ask/`, `/api/auth/me/`, `/api/plan/`, and `/api/chat-ui/`
    to return consistent enriched quota snapshots
  - preserved backward-compatible default deep-mode behavior for free users
    (`ENABLE_FREE_DEEP_MODE=true` unless overridden)
  - validated with full suite: all 124 tests passing

- Production deployment + runtime hardening completed:
  - deployed app successfully on Fly.io
  - production database connected to Neon PostgreSQL via `DATABASE_URL`
  - migrations run successfully in production
  - fixed HTTPS redirect loop in production by trusting proxy HTTPS header
    (`SECURE_PROXY_SSL_HEADER`)
  - fixed static serving path in Fly config (`/code/staticfiles`)
  - removed baked secret from Docker image; runtime secrets now come from Fly
    secrets only
  - imported full canonical verse corpus into Neon-backed environment
  - provisioned SEO-friendly Fly app slug `askbhagavadgita`
  - documented free-cost runtime mode: auto-stop machines, zero always-on
    machines, optional OpenAI-disabled operation

- User support contact flow completed:
  - added `SupportTicket` model for guest and authenticated users
  - added `POST /api/support/` for programmatic support submissions
  - added chat-ui support panel with direct email and structured support form
  - exposed support queue in Django admin with issue/status filters
  - added tests for API and chat-ui support submission flows
- **Support address for account email:** `DEFAULT_FROM_EMAIL` and `SERVER_EMAIL` default
  to `SUPPORT_EMAIL` (e.g. `askbhagwatgitasupport@gmail.com`); ITR templates get
  `support_email` via `apps.accounts.context_processors.support_contact`; allauth
  **forgot password** flow has matching templates and a **Forgot password?** link on
  login; `.env.example` documents `DEFAULT_FROM_EMAIL` and optional Gmail SMTP vars
  for production.

- Cached multilingual verse synthesis added:
  - new `VerseSynthesis` model stores per-verse integrated overview, commentary bridge,
    life application, key points, and synthesis embedding
  - verse detail API now generates this once on demand, saves it, and reuses it on later opens
  - clicked verse references from chat now open directly into the Gita reader with this richer view
  - future verse embedding refreshes now include any cached synthesis text automatically
  - runtime now degrades safely if the `VerseSynthesis` migration has not been applied yet,
    so chat and daily verse endpoints keep working until the DB is migrated
  - fallback verse synthesis quality improved with cleaned, language-aware commentary snippets
  - synthesis schema versioning now forces regeneration of older noisy cached summaries
  - verse synthesis now records `generation_source` (`llm` or `fallback`) for easier debugging and quality verification
- Guest homepage UX cleaned up:
  - guest logged-out landing now uses a true single-column layout instead of reserving sidebar space
  - hero simplifies for guests by removing the competing remembrance card
  - guest register/login access is now surfaced in the main flow instead of the hidden sidebar
- Guest Ask-From-SEO crash fixed in production:
  - identified the issue path as SEO landing CTA posting directly to
    `/api/chat-ui/` for immediate guest ask execution
  - updated SEO CTA flow to open `/api/chat-ui/` via GET with `prefill`
    instead of executing ask on the landing page
  - chat-ui GET now accepts `prefill` and injects it into the composer text
    so users can review/edit before submitting
  - reverted retrieval scoring optimizations to preserve prior relevance
    behavior and answer quality
  - added regression tests for SEO CTA GET prefill flow and chat-ui prefill
    rendering
  - added exception logging guard in chat-ui ask pipeline with structured
    request context (`mode`, `language`, `guest_id`, `referer`, message
    length, conversation id) so future failures are visible in Fly logs
  - added explicit `seo_cta_to_chatui` marker log when `/api/chat-ui/` opens
    with `prefill` from SEO landing CTA, including referer + guest context
  - added regression test to ensure internal ask exceptions render a user-safe
    error state instead of returning HTTP 500
- Admin-configurable request quota controls added:
  - new singleton `RequestQuotaSettings` model in admin for guest/free/pro
    quota controls
  - admin can enable/disable quota enforcement separately for guest, free,
    and pro users
  - admin can set guest request cap and free/pro daily request caps without
    changing code or redeploying
  - API (`/api/ask/`) and chat-ui now read runtime limits from admin settings
    with safe fallback to environment defaults when no settings row exists
  - when free/pro limits are disabled, responses return `daily_limit=null` and
    `remaining_today=null` to indicate unlimited asks
  - validated with new regression tests for disabled guest cap and disabled
    free cap
  - validated with full suite: all 113 tests passing
- Viral-growth landing conversion pass completed:
  - chat-ui landing now includes one-tap "starter journey" prompts that
    switch directly into composer mode with prefilled dilemmas
  - added built-in share actions (Web Share API + copy-link fallback) to
    encourage word-of-mouth distribution
  - added trust/value blocks on landing to clarify verse-grounded guidance,
    practical outcomes, and shareability at first glance
  - validated with full suite: all 113 tests passing
- Audience and search-query analytics tracking completed:
  - added persistent `WebAudienceProfile` model to track unique visitors,
    visit heartbeat, and latest source/path
  - wired visitor tracking into SEO index/topic pages and chat-ui landing
    loads with durable guest audience cookie attribution
  - improved guest ask telemetry IDs to be per-browser (`guest:<id>`) so
    unique users-who-used metrics are accurate instead of collapsing to one
    shared "guest" value
  - expanded AskEvent admin dashboard cards with all-time metrics:
    unique visitors, unique users who used the app, queries fired, and
    queries served
  - validated with new regression tests + full suite: all 115 tests passing
- Full growth analytics stack completed:
  - added `GrowthEvent` model to track landing views, starter clicks,
    share/copy clicks, and ask submissions for funnel analysis
  - added UTM attribution fields on `WebAudienceProfile` to store first/last
    source, medium, and campaign for channel performance tracking
  - added `POST /api/analytics/events/` to ingest frontend growth events
    without blocking user experience
  - added staff-only `GET /api/analytics/summary/?days=7` endpoint with:
    all-time totals, conversion snapshot, daily trend rows, and top UTM sources
  - wired chat-ui frontend to emit growth events for starter clicks,
    share/copy actions, and ask-submit events
  - added management command `python manage.py growth_report` for weekly and
    monthly growth snapshots in terminal
  - validated with migrations + new tests + full suite: all 118 tests passing
  - deployed to production (version 22, Fly.io `askbhagavadgita`)
- Project scaffold created with Django + DRF.
- Core API app added: `guide_api`.
- Models implemented:
  - `Verse`
  - `Conversation`
  - `Message`
- API endpoints implemented:
  - `GET /api/health/`
  - `POST /api/ask/`
  - `GET /api/daily-verse/`
  - `GET /api/history/<user_id>/`
- Basic retrieval system implemented:
  - default verse seed data
  - theme keyword matching
  - deterministic verse ranking
- Basic safety guardrails implemented:
  - blocks risky prompts (self-harm/violence/medical/legal patterns)
- Admin configured for verses and conversations.
- Automated tests added and passing.
- Environment upgraded:
  - Python `3.14.3` in project `.venv`
  - latest Django/DRF and supporting packages installed
- Dependency management set up:
  - `requirements.txt` (top-level deps)
  - `requirements.lock.txt` (pinned exact deps)
- Developer workflow set up:
  - `Makefile` commands for setup/run/test/lock
- Smoke testing completed for all current endpoints.
- `.env` support added in Django settings.
- `.env.example` added with OpenAI and runtime config.
- OpenAI guidance generation added with safe fallback mode.
- Citation grounding validation added for generated responses.
- `.gitignore` added for local environment and secrets.
- Debug response marker added: `response_mode` (`llm` or `fallback`) in API.
- Manual browser testing page added: `GET/POST /api/chat-ui/`.
- Feedback capture added:
  - UI buttons on `/api/chat-ui/` (`Helpful` / `Not Helpful`)
  - API endpoint `GET/POST /api/feedback/`
  - DB persistence via `ResponseFeedback` model
- Relevance tuning v1 completed:
  - Expanded default verse set for common life issues
  - Hybrid retrieval scoring (theme overlap + token overlap)
  - Prompt updated to directly address user problem in first line
- Full dataset ingestion support added:
  - `import_gita` management command with upsert behavior
  - `--dry-run` and `--strict` modes
  - sample input file at `data/gita_import_sample.json`
- Kaggle integration prep added:
  - CSV conversion script: `scripts/convert_kaggle_gita_csv.py`
  - Makefile shortcut: `make convert-gita-csv INPUT=data/Bhagwad_Gita.csv`
- Kaggle multi-script ingestion upgrade completed:
  - new command: `python manage.py ingest_gita_multiscript --input ...`
  - supports both CSV and XLSX source files (XLSX via `openpyxl`)
  - normalizes and deduplicates by `chapter.verse`
  - merges additive source rows into `data/gita_additional_angles.json`
  - keeps canonical `data/Bhagwad_Gita.csv` and `data/gita_700.json` intact
    by default
  - optional canonical refresh still available via `--update-canonical`
- Retrieval embeddings refreshed after additive-angle ingestion:
  - `python manage.py embed_gita_verses --overwrite --batch-size 50`
  - completed for all 701 verses using `text-embedding-3-small`
- Retrieval tuning pass after additive-angle ingestion:
  - added deterministic semantic-vs-hybrid local strength selection
  - tightened confidence gate to avoid weak semantic matches
  - expanded curated priors for anger/comparison/discipline verses
  - eval improved from `0.74` to `0.80` hit rate on 50-case pipeline set
- Multilingual retrieval-eval expansion completed:
  - added `data/retrieval_eval_cases_user_mix.json` (30 mixed Hindi,
    Hinglish, and English prompts)
  - expanded theme keywords for multilingual phrasing in retrieval detector
  - new mixed set benchmark: `0.8333` hit rate (`25/30`)
  - baseline 50-case pipeline set remained stable at `0.80`
- Dual-corpus retrieval experiment completed (safe fallback):
  - implemented additive-angle candidate retrieval + deterministic rerank helper
  - benchmarked impact on both eval sets
  - left dual-rerank disabled in runtime path after observing mixed
    trade-offs, preserving current best profile (`0.80` baseline, `0.8333`
    mixed set)
- pgvector migration phase-1 scaffolding completed (non-breaking):
  - added PostgreSQL `DATABASE_URL` parsing in settings (SQLite remains default)
  - added guarded runtime semantic path for pgvector when enabled
    (`ENABLE_PGVECTOR_RETRIEVAL=true`)
  - added management commands:
    - `setup_pgvector_index` (extension/table/ivfflat index)
    - `sync_pgvector_embeddings` (Verse JSON embeddings -> pgvector table)
  - embedding job can optionally chain sync via `embed_gita_verses --sync-pgvector`
- Retrieval reranker pass completed:
  - widened semantic/hybrid candidate pool before final selection
  - added deterministic user-context reranker for action/decision and
    emotional/reactivity queries
  - baseline pipeline set remained at `0.82` (`41/50`)
  - mixed real-user set improved to `0.8667` (`26/30`)
- Sparse lexical fusion pass completed:
  - added lightweight exact-token sparse retriever and fused it into the
    final candidate merge stage
  - preserved baseline pipeline performance at `0.80` on the 50-case set
  - preserved mixed real-user performance at `0.8667` (`26/30`)
- Guidance-generation prompt refinement completed:
  - strengthened LLM prompt to explicitly explain:
    - what Krishna was addressing in Arjuna
    - the timeless principle of the verse
    - how that principle applies to the user's modern situation
  - improved fallback wording to mirror the same Krishna-to-Arjuna-to-user
    bridge structure
- Merged verse-context runtime layer completed:
  - merged `gita_700.json`-backed canonical verse data and
    `gita_additional_angles.json` additive data by `chapter.verse`
  - runtime retrieval/prompt/quote/embedding context now reads from the
    merged per-reference view instead of treating them as separate sources
  - re-embedded all 701 verses after the merge-layer update
- Derived chapter-summary retrieval boost completed:
  - no separate chapter-summary JSON file required
  - chapter summaries are derived in-memory from existing chapter-perspective
    text plus per-chapter verse theme distribution
  - retrieval reranker now uses that chapter-level context to better route
    broad or abstract user questions toward the right chapter before final
    verse selection
- Vedic multi-author commentary integration completed:
  - local `data/slok/` verse JSON files now load as per-verse commentary
    enrichment keyed by `chapter.verse`
  - local `data/chapter/` JSON files now feed chapter summaries when present
  - retrieval scoring, sparse matching, prompt serialization, and embedding
    text now include compact multi-author commentary perspectives
  - canonical verse selection remains verse-first; author commentary is used
    as supporting context, not as a replacement source of truth
- Query-aware author perspective selection completed:
  - per-verse author commentary is now ranked against the user's actual query
  - prompt context now prefers the most relevant commentator angles instead of
    taking the first few available entries
  - this improves the Krishna-to-Arjuna explanation layer while preserving the
    same verse-grounded retrieval contract
- Repo-level frontend redesign automation guidance added:
  - root `AGENTS.md` now defines a frontend redesign workflow for AI agents
  - new `docs/design-playbook.md` maps app purpose to visual direction,
    typography, color, motion, and UX constraints
  - `docs/AI_AGENT_HANDOFF.md` now points future agents to the design playbook
    before substantial UI work
- Spiritually aligned chat-ui visual redesign pass completed:
  - upgraded `chat_ui.html` with a stronger sacred design system and reusable
    visual tokens
  - improved hero framing, panel depth, navigation polish, conversation cards,
    chat bubble styling, landing state, and composer prominence
  - aligned the seeker-facing UI more closely with the Bhagavad Gita guidance
    purpose while preserving existing chat functionality
- Chat-ui appeal polish pass completed:
  - improved hierarchy and cohesion for quote-art, plan/upgrade, and chat
    composer sections
  - added better micro-hierarchy with panel kickers, refined chips, polished
    style cards, and more premium scroll/composer treatment
  - preserved existing functionality while making the interface feel more
    finished and visually unified
- Immersive frontend motion pass completed:
  - added ambient aurora layers, sacred grid, cursor aura, scroll progress, and
    gentle parallax for a richer devotional atmosphere
  - upgraded motion system with stronger GSAP entrances, floating orb motion,
    sheen effects, and deeper visual layering across hero, panels, and chat
  - preserved existing frontend functionality while making the UI feel more
    alive, premium, and emotionally immersive
- Internet-sourced SVG asset integration completed:
  - added locally stored open-source Lucide SVG assets for section iconography
    and UI accents under `guide_api/static/guide_api/assets/`
  - integrated those assets into hero, landing cards, quote-art, conversation,
    feedback, and saved-reflection surfaces
  - attempted external sacred motif downloads, but kept only clean verified SVG
    assets to avoid broken or checkpoint-blocked files in the app
- Concept-aligned layout rearrangement completed:
  - reordered sidebar content so spiritual guidance, thread memory, and core
    seeker flows appear before account and support controls
  - aligned component placement more closely with the app's primary concept:
    sacred dialogue first, utilities second
  - improved section framing with more intentional iconography and hierarchy
- Inline SVG reliability fix completed:
  - replaced small static icon image references in `chat_ui.html` with inline
    SVG markup so icons render reliably without depending on static asset
    loading
  - resolved the broken icon placeholders appearing across the frontend
- Premium hierarchy/layout pass completed:
  - rebalanced the main two-column layout so the conversation area carries more
    visual authority and the sidebar feels calmer
  - grouped lower-priority tools such as quote art, settings, quota, saved
    reflections, and account actions into expandable utility sections
  - increased conversation readability with a stronger heading block, taller
    chat shell, larger reply text, and a more prominent composer area
- Sidebar visibility fix completed:
  - removed the extra sticky/overflow scroll trap on the left column after it
    started hiding lower sidebar sections beneath the conversations panel
  - restored normal page flow so all left-side components remain reachable
- Homepage left-rail simplification completed:
  - when the user is signed out and no active conversation is open, the left
    rail now stays focused on the Guidance Tone panel only
  - preserved signed-in behavior so users still see their conversation list as
    soon as they log in, even before sending a new message
- Composer-focus transition refinement completed:
  - once the user clicks `Start Conversation` from the landing state, the left
    Guidance Tone rail is hidden client-side so the page shifts into a more
    focused asking/composer experience
- Top-nav clipping fix completed:
  - removed sticky overlap behavior from the top navigation after it started
    cutting into the hero/landing visuals during scroll
- Compact top-nav pass completed:
  - reduced top bar padding, pill size, and nav button sizing so the header
    occupies less space and feels lighter above the hero section
- Compact landing-state pass completed:
  - reduced the namaste mark, landing title block, and the `Start Conversation`
    / `Read Gita` action card sizes so the homepage landing section fits more
    comfortably without feeling oversized
- Daily signal automation completed:
  - upgraded `/api/daily-verse/` from a fixed first-verse response to a
    deterministic date-seeded verse selection across the full corpus
  - the `Today's Signal` card now hydrates from that endpoint and displays the
    day’s verse reference plus a language-aware meaning instead of static copy
- Theme tagging command added:
  - `python manage.py tag_gita_themes`
  - supports `--dry-run` and `--overwrite`
- Semantic retrieval foundation added:
  - verse embedding storage on `Verse.embedding`
  - `embed_gita_verses` command for batch embedding generation
  - retrieval now tries semantic similarity first, then hybrid fallback
- Retrieval debug trace added in `DEBUG=true` mode:
  - `retrieval_mode`
  - `retrieved_references`
  - `retrieval_scores`
  - `query_themes`
- Retrieval eval endpoint added:
  - `POST /api/eval/retrieval/`
  - returns retrieval trace only (no LLM generation)
  - supports `mode=benchmark` for side-by-side semantic vs hybrid compare
- Authentication and ownership v1 completed:
  - token auth enabled via `rest_framework.authtoken`
  - auth endpoints:
    - `POST /api/auth/register/`
    - `POST /api/auth/login/`
    - `POST /api/auth/logout/`
    - `GET /api/auth/me/`
  - protected endpoints now require auth:
    - `POST /api/ask/`
    - `GET /api/history/me/`
    - `GET /api/history/<user_id>/` (owner-only)
    - `GET/POST /api/feedback/`
- Makefile QA flows added:
  - `make auth-flow USERNAME=... PASSWORD=...`
  - `make auth-flow-benchmark USERNAME=... PASSWORD=...`
  - `make auth-flow-benchmark-summary USERNAME=... PASSWORD=...`
- Retrieval benchmark summary tooling added:
  - `scripts/print_retrieval_benchmark_summary.py`
  - concise semantic vs hybrid comparison output
- Retrieval quality harness added:
  - eval dataset: `data/retrieval_eval_cases.json`
  - management command: `python manage.py eval_retrieval`
  - supports modes: `pipeline`, `hybrid`, `semantic`
  - supports strict failure gate: `--strict`
  - Makefile shortcut: `make eval-retrieval`
  - dataset expanded to 50 prompts across key life themes
- Hybrid retrieval scoring tuned (v2):
  - reduced noisy commentary influence in token scoring
  - added theme-aware prior references and expanded stopwords
  - benchmark on 50-case eval set improved from `0.20` to `0.54` hit rate
- Hybrid retrieval scoring tuned (v3):
  - expanded theme keyword coverage for purpose/comparison/discipline phrases
  - added `comparison` theme with dedicated reference priors
  - benchmark on 50-case eval set improved from `0.54` to `0.66` hit rate
- Retrieval eval tooling improved (v4):
  - added miss-cluster diagnostics in `eval_retrieval` via `--report-misses`
  - reports inferred miss themes and most-missed verse references
- Hybrid retrieval scoring tuned (v5):
  - added chapter-level priors by inferred theme
  - increased prior impact and expanded uncertain/confusion keyword coverage
  - benchmark on 50-case eval set improved from `0.66` to `0.78` hit rate
- Auth flow reliability improvements added:
  - migration precheck before auth flow targets
  - safe token parsing script: `scripts/extract_token.py`
  - curl timeout guardrails (`--connect-timeout`, `--max-time`)
- Subscription limits and quota checks added on `/api/ask/`:
  - `UserSubscription` model (`free`/`pro`)
  - `DailyAskUsage` model for per-day counters
  - free/pro daily limits configurable via env vars
  - `/api/auth/me/` now returns quota snapshot fields
  - `/api/auth/plan/` added for local plan switch testing
  - `/api/chat-ui/` now supports plan switch + quota snapshot display
- UX pass v1 completed for `chat-ui`:
  - sidebar `Today` card added for daily spiritual framing
  - starter prompt chips for first-time onboarding
  - primary in-chat composer added above the transcript
  - chat asks now update in place without a full page refresh
  - thinking animation now appears while waiting for the reply
  - latest structured assistant reply now stays inside the conversation
  - structured response rendering (guidance/meaning/actions/reflection/verses)
  - follow-up prompt chips after each answer
  - newest assistant reply now animates in with a typing effect
  - recent question shortcuts (session-backed, max 3)
- Threaded conversation UX pass completed for `chat-ui`:
  - logged-out chat now stays temporary in session and is not persisted to DB
  - logged-in users only see their own saved conversation history
  - sidebar mode selector now acts as a global mode for the next message in
    any thread
  - separate conversation threads now persist in the database
  - chat-ui shows a sidebar list of recent conversations
  - sidebar cards now show message counts and last-updated timestamps
  - active or older threads can be deleted from the sidebar
  - `Start New Conversation` begins a separate thread instead of continuing
    the active one
  - LLM prompt now uses recent thread history as supporting context while
    still answering the latest user message as the primary query
- Frontend motion and visual polish pass completed for `chat-ui`:
  - upgraded typography with display/body font pairing for stronger hierarchy
  - integrated `Animate.css` for lightweight hero entrance effects
  - integrated `AOS` for scroll-triggered panel reveals
  - integrated `GSAP` for subtle page and list choreography
  - integrated `VanillaTilt` on highlight/sidebar cards as progressive enhancement
  - kept chat live-submit behavior and typing/thinking interactions intact
- Multi-language support v1 completed (`en`, `hi`):
  - `POST /api/ask/` accepts `language` and returns it in response payload
  - `POST /api/follow-ups/` accepts `language` for localized prompt labels
  - chat-ui now has a global language selector shared across conversations
  - guidance generation + deterministic fallback support Hindi output
  - tests added for Hindi API ask and chat-ui language persistence
- Multi-language UX stabilization completed:
  - language switch now updates chat-ui in place without full-page reload
  - conversation sidebar state now remains visible on language changes
  - primary chat-ui labels/buttons/headings now localize for Hindi mode
- Hindi UI localization sweep completed:
  - translated remaining chat-ui microtexts (helper copy, form labels,
    placeholders, empty states, and guest/help panels)
  - localized live-chat client fallback error message for Hindi mode
- Conversation sidebar paging UX completed:
  - sidebar now renders first 3 recent conversations initially
  - conversation list has its own scroll container to avoid page overgrowth
  - older conversations now load incrementally on sidebar scroll
- Divine experience pass completed:
  - upgraded guidance tone to be calmer, devotional, and guru-like
  - improved fallback guidance wording for spiritually grounding responses
  - replaced text-only waiting state with a Sudarshan-Chakra style loader
  - added heaven-like visual polish (stardust + golden shimmer accents)
- Relevance gate + cost-safe retrieval hardening completed:
  - added deterministic relevance confidence check before guidance generation
  - when retrieval confidence is low, switched to local curated verse fallback
    (no runtime web search and no extra LLM calls)
  - introduced `retrieval_mode=curated_fallback` for weak-match recoveries
- Multilingual corpus utilization enhancement completed:
  - retrieval relevance scoring now incorporates Sanskrit/Hindi/English and
    word-meaning metadata from local `Bhagwad_Gita.csv`
  - prompt context now includes compact Hindi/word-meaning angle snippets
  - embedding input now includes Sanskrit, transliteration, Hindi meaning,
    English meaning, and word meanings for stronger multilingual recall
- Admin analytics dashboard v1 completed:
  - new `AskEvent` telemetry model for ask attempts/outcomes
  - events logged from `/api/ask/` and `chat-ui` ask path
  - admin counters on `Ask events` changelist:
    - asks today
    - asks (7d)
    - fallback rate (7d)
    - helpful rate (7d)
    - quota blocks (7d)
- Saved reflections/bookmarks retention loop completed:
  - `SavedReflection` model added (message/guidance/actions/reflection/refs/note)
  - owner-only API endpoints added:
    - `GET /api/saved-reflections/`
    - `POST /api/saved-reflections/`
    - `DELETE /api/saved-reflections/<id>/`
  - chat-ui includes `Save Reflection` flow for existing auth usernames
- Mobile contract hardening completed (non-breaking):
  - `/api/v1/` alias added for all current endpoints
  - standardized error envelope added (`error.code`, `error.message`, `detail`)
  - pagination added to list APIs:
    - `GET /api/feedback/?limit=&offset=`
    - `GET /api/saved-reflections/?limit=&offset=`
- Contextual follow-up system completed:
  - `POST /api/follow-ups/` endpoint added
  - `/api/ask/` now returns dynamic follow-up prompt objects
  - follow-up analytics events added (`shown`, `clicked`) via `FollowUpEvent`
  - chat-ui follow-up chips now consume structured follow-up objects
- Engagement profile + streak API completed:
  - `UserEngagementProfile` model added
  - `EngagementEvent` model added (`streak_updated`, `reminder_pref_updated`)
  - `GET/PATCH /api/engagement/me/` added
  - `/api/ask/` now updates daily streak and returns engagement snapshot
- Chat UI auth + layout sanity pass completed:
  - added visible `Home`, `Register`, `Login`, and `Logout` controls
  - chat-ui now defaults to logged-in username when available
  - improved component positioning for account, ask, quota, and response sections
- Docs expanded and kept in sync:
  - `README.md` updated with auth + QA commands
  - `docs/USER_GUIDE.md` updated with auth usage and make targets
  - `docs/DEVELOPER_GUIDE.md` updated with endpoint map and sequence diagrams
- Chapter and verse browsing API completed (mobile-ready):
  - `GET /api/chapters/` - list all 18 chapters with metadata
  - `GET /api/chapters/<chapter_number>/` - chapter detail with verse list
  - `GET /api/verses/<chapter>.<verse>/` - full verse detail with:
    - Sanskrit shloka, transliteration, speaker
    - Hindi/English meanings and word meanings
    - Multi-author Vedic commentaries from `data/slok/` JSON files
  - chapter/verse endpoints work via `/api/v1/` alias
- Mantra generation endpoint completed:
  - `POST /api/mantra/` - returns verse as mantra for mood
  - supports moods: calm, focus, courage, peace, strength, clarity
  - bilingual (en/hi) output with recitation instruction
- Tests added for all new browsing and mantra endpoints
- Quote Art frontend integration completed:
  - new `Quote Art` panel added to `/api/chat-ui/` sidebar
  - 4 visual styles selectable: Divine, Minimal, Nature, Cosmic
  - verse reference input with popular verse quick-select chips
  - AJAX-based art generation via `/api/v1/quote-art/generate/`
  - preview card displays styled verse with Sanskrit text
  - copy-to-clipboard and native share (Web Share API) actions
  - bilingual UI labels (en/hi) matching chat-ui language setting
  - CSS matches divine theme aesthetic with gradient backgrounds
- Gita Reader (Pro Feature) completed:
  - new "Read Bhagavad Gita" panel visible only for Pro plan users
  - full-screen modal reader with divine theme styling
  - chapter grid view displaying all 18 chapters with metadata:
    - chapter number, name (English & Hindi), verse count
    - hover animations and VanillaTilt effects
  - chapter detail view with summary and verse list
  - verse detail view with full content:
    - Sanskrit shloka in golden box
    - transliteration
    - English and Hindi meanings
    - multi-author Vedic commentaries
  - navigation breadcrumbs (Chapters → Chapter X → Verse)
  - GSAP animations for smooth transitions between views
  - verse actions: copy verse, create Quote Art
  - "Create Art" button auto-fills Quote Art panel and generates
  - keyboard support (ESC to close)
  - bilingual labels (en/hi) matching user's language setting
- Mortality/war/death retrieval & guidance theme completed:
  - added `mortality` theme to `THEME_KEYWORDS` with ~50 multilingual
    keywords (war, death, die, destroy, weapon, soul, मृत्यु, युद्ध, etc.)
  - added `THEME_REFERENCE_PRIORS["mortality"]` mapping to 2.20, 2.22, 2.23,
    2.27, 2.47, 2.62, 2.63, 2.14, 6.5, 18.66
  - added `THEME_CHAPTER_PRIORS["mortality"]` → {2, 6, 11, 18}
  - added 2.20, 2.23 to `UNIVERSAL_CURATED_REFERENCES`
  - added `MORTALITY_OR_WAR_TERMS` set and bridge reranker boost (+12 for
    Self-immortality verses, +8 for war-origin verses)
  - added `WAR, DEATH, AND THE IMMORTAL SELF` topic detection in
    `build_guidance()` with detailed LLM prompt guidance
  - added `_build_mortality_fallback()` with dedicated en/hi templates
    covering: why war happens (2.62-63), immortality of Self (2.20, 2.23),
    endurance (2.14), and Krishna's "do not despair" (18.66)
  - tightened confidence gating for no-theme queries (score threshold
    lowered to prevent marginal semantic results)
  - added 5 mortality eval cases — 4 of 5 hit (2 perfect 3/3 matches)
  - removed the redundant "Your Recent Curiosity" sidebar panel because the conversation list already covers recent context
  - Guidance Tone moved out of the left rail and into the main chat flow below the composer
  - landing state shows Guidance Tone expanded under the chat box
  - active-thread state keeps Guidance Tone available as a compact accordion below the composer
  - all 63 tests pass
- LLM verse-relevance validation & correction layer completed:
  - merged verse-relevance evaluation into the main guidance prompt instead
    of using a separate LLM call — reduced total API calls from 3 to 2 per
    question (embedding + guidance generation)
  - system prompt now instructs the LLM to evaluate whether provided verses
    address the user's concern and reference better Gita verses if not
  - grounding check expanded: LLM-suggested verse references are verified
    against the DB before acceptance
  - added `_fetch_verses_by_references()` helper for reference→Verse lookup
  - `_validate_and_correct_verses()` kept as a utility but no longer called
    in the hot path
- Commentary enrichment in guidance prompts completed:
  - increased per-verse author commentary from 2 to 3 commentators
  - increased commentary budget from 260 to 500 chars per verse
  - added english_meaning field (200 chars) to prompt context
  - increased hindi_meaning, word_meaning budgets from 120 to 200 chars
  - increased additional_angles budget from 220 to 400 chars
  - increased angle limit from 2 to 3 per verse
  - the LLM now receives substantially richer multi-author scholarly
    context for crafting deeply informed, tradition-grounded guidance
  - all 71 tests pass

- Global multilingual SEO presence completed:
  - added global language selector (en/hi) visible on every page including guest/logged-out pages
  - added public SEO landing pages at `/`, `/bhagavad-gita-for-anxiety/`,
    `/bhagavad-gita-for-career-confusion/`, `/bhagavad-gita-for-relationships/`
    with dedicated metadata, focused copy, curated verses, and direct CTAs
  - each SEO page fully localized in English and Hindi
  - added `/robots.txt` endpoint with sitemap hint (allow all crawlers)
  - added `/sitemap.xml` endpoint listing 5 key public URLs
  - added canonical URL tags on all SEO pages
  - added hreflang alternates (en/hi/x-default) for multi-language SEO
  - added Open Graph and Twitter Card meta tags for social sharing
  - added JSON-LD structured data (WebSite, CollectionPage, WebPage, BreadcrumbList)
  - added Google Search Console verification meta-tag support (configurable via GOOGLE_SITE_VERIFICATION secret)
  - added 3 new tests for SEO metadata, canonical, hreflang, and Google verification
  - all 86 tests pass

- Razorpay payment integration tested and validated:
  - comprehensive test suite for payment flow (21 new tests):
    - CreateOrderView: INR/USD flows, default currency, unauthenticated failure, gateway misconfiguration
    - VerifyPaymentView: valid signature verification, invalid signature rejection, order ID mismatch, missing parameters, unauthenticated failure
    - RazorpayWebhookView: payment.captured event handling, payment.failed event, invalid signature rejection, webhook misconfiguration, invalid JSON handling
    - SubscriptionStatusView: free plan status, active pro plan, expired pro plan, unauthenticated failure
    - End-to-end payment flow: complete order creation → payment verification → subscription activation cycle
  - all payment endpoints verified working against mocked Razorpay client
  - webhook signature verification validated with HMAC-SHA256
  - subscription activation logic confirmed (plan upgrade, is_active, 30-day expiry)
  - all 107 tests pass (86 existing + 21 new payment tests)

- UX focus (current):
  - improve emotional clarity and response tone quality
  - expand guided journey from first answer to second/third session
  - continue polishing `/api/chat-ui/` for faster manual UX iteration

## Remaining (Core Product Roadmap)

### 1) Retrieval Upgrade
- Move from keyword matching to semantic retrieval (`pgvector`).
- Add embedding pipeline for verse corpus.

### 2) Auth + Data Ownership
- Completed (token + ownership checks live).

### 3) Analytics + Feedback
- Track activation, repeat usage, and retention metrics.

### 4) Monetization Foundation (Later)
- Razorpay integration tested (next: connect payment button in chat-ui for users to upgrade).
- Consider email follow-up for expired subscriptions.

## Next 3 Tasks (Recommended)

1. Wire payment button UI in chat-ui to trigger order creation + checkout flow
2. Add push/email delivery service integration for reminder preferences.
3. Add automated subscription renewal/expiry notification job.

## Deferred (Do Later)

- Additional retrieval tuning iterations beyond current `0.78` hit rate (deferred).
- Fixed guest-home `chat_ui.html` template nesting bug that caused `/api/chat-ui/` to fail with an unclosed `{% if %}` during render.
- Hid guest register/login access for authenticated sessions so signed-in users only see it in true guest state.
- Added persistent guest browser quota tracking with a `3`-conversation cap and signup wall after the limit is used.
- Refined guest quota to count `3` guest questions per browser instead of thread count, matching the single-thread guest UX.
- Added always-visible guest `Register` and `Login` entry points in the top nav that jump to and focus the working auth forms.
- Switched guest nav auth actions from page scrolling to a real on-page login/register modal with tabbed forms.
- Updated authenticated plan defaults to `5` asks/day on free and `10000` asks/day on Pro.
- Added a deterministic structured query interpreter before retrieval/generation so responses now carry explicit emotional state, life domain, likely Gita principles, search terms, and match strictness.
- Added a greeting-aware response path so simple messages like `hi` or `hye` no longer force irrelevant verses, and reordered reply panels to show practical actions before reflection.
- Repositioned the chat landing page for growth with stronger SEO title/description, clearer “ask your problem” hero copy, sharper CTAs, more concrete composer guidance, and stronger starter prompts focused on real user pain points.


## How To Update This File

At the end of each coding session:
- Move completed items from "Remaining" to "Completed".
- Add any new scope under "Remaining".
- Update "Next 3 Tasks" so the next session can start immediately.

## 2026-04-15

- Synced documentation for ITR OAuth and WeasyPrint: **`AGENTS.md`**, **`README.md`**,
  **`docs/AI_AGENT_HANDOFF.md`**, **`docs/DEVELOPER_GUIDE.md`**, **`docs/USER_GUIDE.md`**,
  **`docs/ITR_CHANGE_LOG.md`**; sanitized **`.env.example`** Google OAuth client ID
  placeholder.
- **`make test`:** 242 tests OK after doc updates.

## 2026-04-14

- Restored CSRF protection on the session-backed payment and subscription endpoints so browser sessions cannot create orders or verify payments without normal Django CSRF checks.
- Hardened production startup so the app now refuses to boot with the public fallback `SECRET_KEY` when `DEBUG=false`.
- Sanitized `.env.example` so it no longer suggests real-looking Razorpay credentials.
- Fixed intermittent prod chat resets by preserving `conversation_id` in the live-chat DOM swap URL (previously the client always rewrote the URL without the id, so the next render fell back to the landing state even though the thread was created).
- Fixed intermittent prod slow/partial replies by preventing `ensure_seed_verses()` from re-seeding/updating the verse corpus on every worker boot when verses already exist.
- Fixed intermittent prod worker timeouts by lazily loading verse commentaries (`data/slok/*.json`) per-verse instead of loading the full 36MB dataset on the first request.
- Reduced cold-start failures by keeping `min_machines_running = 1` in `fly.toml`.
- Reduced partial replies by increasing gunicorn timeouts and bounding OpenAI client request timeouts so we can fall back gracefully instead of worker aborts.
- Implemented a plain-language tone path for `mode=simple` (especially for anxious/stressed prompts) and added “Explore Related Verses” under “Verses Used”.
- Added custom domain support for `askbhagavadgita.co.in` (allowed hosts + CSRF trusted origins) to unblock GoDaddy DNS + Google Search Console verification.
- Added canonical host redirect in prod to avoid duplicate SEO indexing across `www`, apex, and `*.fly.dev`.
- Revisited the full user-facing visual system across the three public templates (`chat_ui`, `seo_landing`, `shared_answer`) and shifted the product toward a calmer, chat-first hierarchy.
- Redesigned SEO/public landing pages so users can ask immediately above the fold while topic discovery, daily verse, archive, and FAQ sections now support that primary action instead of delaying it.
- Redesigned the shared-answer page into a cleaner reading and conversion flow so shared links feel like a first-class product surface instead of a utility card.
- Reworked the chat UI hierarchy to put the active dialogue visually first: stronger hero ask box, main-first desktop layout, sticky conversation shell/header, and a more secondary right rail for utilities.
