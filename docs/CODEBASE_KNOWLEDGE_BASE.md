# BhagwatGitaGuide Backend Knowledge Base

Last reviewed: 2026-04-28

This document is a durable map of the backend so future coding sessions can start
with product and technical context already loaded. It complements
`docs/AI_AGENT_HANDOFF.md`, `PROGRESS.md`, `docs/DEVELOPER_GUIDE.md`, and
`PAYMENT_INTEGRATION_ANALYSIS.md`.

## Product Identity

- Core product: Bhagavad Gita guidance app where a seeker asks modern life
  questions and receives compassionate, verse-grounded guidance.
- Desired tone: Krishna-to-Arjuna clarity, parent-like compassion, practical
  current-life application, not generic chatbot advice.
- Current product pillars:
  - Ask: answer the user's current situation or scripture-study question.
  - Read: browse chapters, verses, commentaries, notes, and daily verse.
  - Practice/Meditate: sadhana, japa, meditation logs, practice workflows.
  - Journal/Insights: saved reflections, conversation history, journey summary.
  - Plans/Payments: Plus/Pro subscription, sadhana and workflow purchases.
  - Community/Growth: community posts, sharing, SEO landing pages, analytics.
- Optional side app: ITR computation summary workflow. It shares the Django
  process and user model but should stay separate from Bhagavad Gita feature
  work unless explicitly requested.

## Repository Shape

- `config/`: Django project settings, URLs, WSGI/ASGI, optional ITR settings.
- `guide_api/`: primary Bhagavad Gita API, web UI, retrieval, LLM, payments,
  sadhana, japa, practice workflows, push reminders, tests, admin.
- `apps/`: optional ITR app modules: accounts, billing, documents, exports,
  extractors, reviews, comments, analytics, marketing.
- `templates/`: ITR-facing templates.
- `guide_api/templates/guide_api/`: Gita web templates: chat UI, SEO landing,
  community wall, practice hub, shared answers, legal pages.
- `guide_api/static/guide_api/`: Gita frontend CSS, SVG icons, audio.
- `data/`: canonical and enrichment corpus: `gita_700.json`,
  `Bhagwad_Gita.csv`, `gita_additional_angles.json`, chapter JSON, slok JSON,
  retrieval eval sets.
- `docs/`: operational, developer, payment, mobile parity, meditation, design,
  ITR audit docs.
- `scripts/`: local import and benchmark helpers.
- `media/` and `staticfiles/`: runtime/generated; do not treat as source.

## Runtime And Deployment

- Stack: Django + DRF, Python 3.14, SQLite locally, Neon PostgreSQL in
  production, Fly.io app `askbhagavadgita`.
- Public domains/URLs: `https://askbhagavadgita.co.in/` and Fly URL.
- API prefixes: `/api/...` and `/api/v1/...` mirror the same route table.
- Secrets live in environment/Fly secrets. Do not commit `SECRET_KEY`,
  OpenAI keys, Razorpay keys, database URLs, Google OAuth secrets, or Expo
  push tokens.
- Free-cost Fly mode is supported through auto-stop and zero/minimal machines,
  but cold starts are expected.
- Production HTTPS depends on `SECURE_PROXY_SSL_HEADER` behind Fly proxy.

## Core Backend Files

- `guide_api/models.py`: all Gita product data models.
- `guide_api/views.py`: large orchestration file for auth, ask, guest ask,
  chat UI, analytics, reader, payments, support, community, notes, logs.
- `guide_api/services.py`: language detection, safety, intent routing,
  retrieval, verse/context enrichment, OpenAI guidance, fallback guidance,
  chapter/verse detail helpers.
- `guide_api/serializers.py`: DRF validation/response contracts.
- `guide_api/urls.py`: mirrored API route table for `/api/` and `/api/v1/`.
- `guide_api/permissions.py`: custom browse permission, notably
  `GitaBrowseAPIPermission`.
- `guide_api/admin.py`: admin surfaces and CSV export for billing.
- `guide_api/sadhana_views.py`: multi-day sadhana catalog/access/completion.
- `guide_api/practice_workflow_views.py`: single-session guided workflows,
  purchase access, tags, enrollment.
- `guide_api/japa_views.py`: personal japa commitments and sessions.
- `guide_api/user_insights_summary.py`: aggregates user journey snapshot for
  `/api/v1/insights/me/`.
- `guide_api/push_reminders.py`: Expo push reminder delivery logic.
- `guide_api/google_auth.py`: Google ID token verification and user creation.
- `guide_api/dataset_utils.py`: multi-script corpus normalization.
- `guide_api/tests.py`: main regression suite for APIs, payments, sadhana,
  practice workflows, community, insights, push helpers.

## Primary Data Models

- `Verse`: canonical verse reference, translation, commentary, themes,
  embedding JSON.
- `VerseSynthesis`: cached per-verse overview, commentary consensus, life
  application, key points, optional embedding.
- `Conversation` + `Message`: authenticated chat thread and messages.
- `GuestChatIdentity`: browser-linked guest limits and guest analytics.
- `ResponseFeedback`: helpful/not helpful response feedback.
- `UserSubscription`: Free/Plus/Pro plan and Razorpay/subscription state.
- `BillingRecord`: invoice-ready ledger row per Razorpay order/payment.
- `DailyAskUsage`: authenticated daily ask counters.
- `RequestQuotaSettings`: admin singleton for guest/free/plus/pro quota knobs.
- `AskEvent`, `WebAudienceProfile`, `GrowthEvent`, `FollowUpEvent`,
  `EngagementEvent`: product and growth telemetry.
- `SavedReflection`: user-bookmarked guidance bundle.
- `UserEngagementProfile`: streak and reminder preferences.
- `SupportTicket`: guest/auth support requests.
- `NotificationDevice`: Expo push devices.
- `QuoteArt`: generated/shareable verse art metadata.
- `CommunityPost`: community top-level posts and replies.
- `SharedAnswer`: public shared guidance page.
- `SadhanaProgram`, `SadhanaDay`, `SadhanaStep`, `SadhanaEnrollment`,
  `SadhanaDayCompletion`: multi-day paid/free practice programs.
- `PracticeTag`, `PracticeWorkflow`, `PracticeWorkflowStep`,
  `PracticeWorkflowEnrollment`: single-session practice/meditation workflows.
- `VerseUserNote`: private per-verse notes.
- `UserReadingState`: last verse opened, unique verses seen, read streak.
- `PracticeLogEntry`: manual japa/meditation/reading logs.
- `MeditationSessionLog`: pre/post mood and duration around meditation.
- `JapaCommitment`, `JapaSession`, `JapaDailyCompletion`: personal japa tracks.

## Ask / Guidance Pipeline

Main authenticated endpoint: `POST /api/v1/ask/`. Guest endpoint:
`POST /api/v1/guest/ask/`.

Flow:

1. Validate payload with serializers.
2. Resolve requested language through `resolve_guidance_language`; supports
   English, Hindi, and Hinglish detection.
3. Run safety guardrails with `is_risky_prompt`.
4. Enforce quota through `UserSubscription`, `DailyAskUsage`,
   `RequestQuotaSettings`, and global `DISABLE_ALL_QUOTAS`.
5. Create or select a `Conversation`; latest user message is always primary.
6. Run intent routing with `classify_user_intent`.
7. Interpret query with `interpret_query` to enrich retrieval.
8. Retrieve candidate verses using `retrieve_verses_with_trace`.
9. Build response using `build_guidance`.
10. Validate grounding / references and fall back safely when malformed.
11. Persist assistant message, ask telemetry, streak updates, quota counters.
12. Return structured JSON: guidance, meaning, actions, reflection, verses,
    related verses, follow-ups, intent flags, quota, engagement, debug trace
    in `DEBUG`.

Important behavior:

- General greetings should not force a verse.
- Scripture-study questions should answer what was asked, not force actions.
- Life-guidance questions may include actions/reflection/verses when useful.
- Exact verse questions should explain verse context, why Krishna said it to
  Arjuna, commentary synthesis, and modern application.
- The model may omit actions/reflection/related verses when not relevant.
- Related verses should be highly relevant or filtered out.

## Retrieval And Corpus

- Canonical verse table is seeded/imported from `data/gita_700.json`.
- Multi-script enrichment comes from `data/Bhagwad_Gita.csv` and
  `data/gita_additional_angles.json`.
- Chapter summaries live in `data/chapter/`.
- Per-verse multi-author commentaries live in `data/slok/`.
- `verse_embedding_document` is the single source for embedding text.
- `embed_gita_verses`, `tag_gita_themes`, `ingest_gita_multiscript`,
  `eval_retrieval`, `setup_pgvector_index`, `sync_pgvector_embeddings` are
  management commands for corpus and quality work.
- Semantic retrieval uses OpenAI embeddings when enabled; hybrid and curated
  fallbacks keep local/dev usable without OpenAI.
- pgvector is scaffolded for PostgreSQL but guarded by env flags.
- Eval data:
  - `data/retrieval_eval_cases.json`
  - `data/retrieval_eval_cases_user_mix.json`

## Reader / Scripture Study

- `GET /api/v1/chapters/`: list 18 chapters.
- `GET /api/v1/chapters/<chapter>/`: chapter detail and verse list.
- `GET /api/v1/verses/<chapter>.<verse>/`: full verse detail, commentary,
  optional synthesis.
- `GET /api/v1/verses/search/`: lightweight search.
- `GET /api/v1/daily-verse/`: deterministic date-seeded daily verse.
- `GET /api/v1/daily-verse/history/`: rolling daily-verse archive.
- `GET/PUT/PATCH /api/v1/verses/<chapter>.<verse>/note/`: private verse note.
- `POST /api/v1/reading/verse-open/`: update reading state and streak.

Permission rule:

- Browser/no-token chapter/verse/quote-art access remains allowed for web UI.
- Token-authenticated Free users are gated by `GitaBrowseAPIPermission`;
  Plus/Pro token users are allowed.

## Practice, Meditation, Sadhana, Japa

Sadhana:

- Multi-day guided programs with days and ordered steps.
- Free sample day can be unlocked without paid enrollment.
- Paid access via `product=sadhana_cycle` payment flow.
- Endpoints: `sadhana/programs/`, detail, day detail, day complete,
  `sadhana/me/`.

Practice workflows:

- Single-session or short guided flows, intended for guided meditation and
  special workflows.
- Access modes: `free_public`, `pro_included`, `purchase_required`.
- Steps mirror sadhana media/caption/timed-cue shape.
- Purchase flow uses `product=practice_workflow`, `workflow_slug`, and
  `purchase_currency_options`.
- Endpoints: `practice/tags/`, `practice/workflows/`,
  `practice/workflows/<slug>/`, `practice/workflows/me/`.

Meditation logs:

- `POST /api/v1/practice/meditation-sessions/` stores mood/stress/duration.
- `POST /api/v1/practice/log/` stores meditation minutes, read minutes,
  japa rounds.

Japa:

- Personal japa commitments are distinct from curated sadhana programs.
- Endpoints create/list commitments, start/pause/resume/abandon sessions,
  finish day, fulfill commitment.
- `japa_insights_for_user` feeds the insights summary.

## Insights

Endpoint: `GET /api/v1/insights/me/`.

Implementation:

- View: `UserInsightsSummaryView`.
- Aggregator: `guide_api/user_insights_summary.py`.
- Data sources: engagement profile, conversations, saved reflections,
  verse companions, recent user questions, community posts, sadhana activity,
  reading state, practice logs, japa insights.

Purpose:

- Mobile Insights tab should show the user's spiritual journey pattern:
  recurring questions, most-used verses, streaks, saved reflections, reading,
  practice, japa, community, active sadhana.

## Payments And Plans

Core files:

- `guide_api/views.py`: `CreateOrderView`, `VerifyPaymentView`,
  `PaymentCheckoutBridgeView`, `PaymentStatusUpdateView`,
  `RazorpayWebhookView`, `SubscriptionStatusView`, `PaymentHistoryView`.
- `PAYMENT_INTEGRATION_ANALYSIS.md`
- `docs/PAYMENT_AND_CHECKOUT_E2E_WORKFLOWS.md`

Products:

- `subscription`: Plus/Pro.
- `sadhana_cycle`: access to a sadhana program.
- `practice_workflow`: access to a paid workflow.

Rules:

- `BillingRecord` is the payment ledger source of truth.
- Verify requires HMAC signature and user/order ownership.
- Verify and webhook must check amount/currency against catalog and ledger.
- Webhook captured events activate sadhana/workflow only when ledger and
  catalog amounts match.
- Mobile can use `payments/checkout/bridge/` with deep-link return, then post
  to `payments/verify/`.
- No automatic recurring subscription renewal exists yet.

## Auth, Account, Guest Mode

- Auth supports session/basic/token.
- Endpoints: register, login, Google auth, logout, `auth/me`, profile update,
  change password, forgot/reset password, debug plan update.
- Guest APIs preserve temporary transcript and quota snapshot without account
  persistence.
- Guest-to-login should clear/migrate UI state on the client; there is no
  server-side guest transcript migration endpoint.

## Support, Community, Sharing, Growth

- Support: `POST /api/v1/support/`, `GET /api/v1/support/tickets/`.
- Feedback: `GET/POST /api/v1/feedback/`.
- Saved reflections: CRUD through `/saved-reflections/`.
- Community: public-ish authenticated community posts with reply support and
  soft delete/moderation helpers.
- Shared answers: `POST /api/v1/answers/share/`, public shared answer page.
- Growth analytics: visitor profile, growth events, admin dashboard,
  `growth_report` command, `/api/v1/analytics/events/`, staff-only summary.

## Web / SEO Surfaces

- Root and topic SEO pages live in `guide_api/web_urls.py` and
  `guide_api/templates/guide_api/seo_landing.html`.
- Public pages include daily verse hub, FAQ archive, topic pages, sitemap,
  robots, canonical and hreflang handling.
- Chat UI lives at `/api/chat-ui/` and remains important for manual testing.
- Design direction is documented in `docs/design-playbook.md`.

## Optional ITR App

Kill switch: `ITR_ENABLED=false`.

Core pieces:

- `config/settings_itr.py`: optional settings injection.
- `config/urls_itr.py`: ITR URL include under `ITR_URL_PREFIX`.
- `apps/documents`: upload/review lifecycle for filed ITR JSON.
- `apps/extractors`: ITR-1/ITR-3/ITR-4 JSON parsing and validation.
- `apps/exports`: WeasyPrint/ReportLab PDF generation, retention cleanup.
- `apps/accounts`: separate ITR profile/quota, Google OAuth context.
- `apps/billing`: ITR-specific Razorpay order audit.
- `apps/marketing`, `apps/reviews`, `apps/comments`, `apps/analytics`: ITR
  marketing, review, comments, and funnel support.

Do not mix ITR subscription/quota assumptions with Gita `UserSubscription`.

## Mobile Integration Contract

- Mobile repo: `/Users/deecoderr/Work/Personal/Projects/bhagavadgitaguide_mobile-main`.
- Mobile should use `/api/v1/` where possible.
- Backend owns safety, quotas, plan gates, payments, retrieval, ownership.
- Mobile owns native UX, loading/error states, local drafts, animation, and
  navigation.
- For native checkout, use `payments/checkout/bridge/` or Razorpay SDK; only
  treat access as active after `payments/verify/` and refresh status.

## Testing And Verification

- Backend gate: `make test` or `python manage.py test`.
- Important focused suites/classes:
  - `GuideApiTests`
  - `PaymentIntegrationTests`
  - `CommunityApiTests`
  - `SadhanaApiTests`
  - `PracticeWorkflowApiTests`
  - `UserInsightsVerseNormalizeTests`
  - push reminder tests
  - ITR tests under `apps/*/tests`
- Retrieval quality: `make eval-retrieval` and `python manage.py eval_retrieval`.
- Production smoke: `docs/PRODUCTION_RUNBOOK.md`.

## Current Caution Points

- The repo can have unrelated/uncommitted work. Always check `git status`.
- `guide_api/views.py` is large and high-risk; prefer small, well-tested edits.
- Payment changes must update tests and payment docs.
- Public API changes should be additive; mobile depends on current field names.
- If guidance behavior changes, update user/developer docs and tests.
- If embedding text changes, re-run embeddings and pgvector sync if enabled.
- If sadhana/practice purchase behavior changes, update mobile parity docs.
- Keep ITR disabled or ignored unless the task explicitly asks for ITR.

## Future Feature Build Checklist

1. Read this file plus `AGENTS.md`, `PROGRESS.md`, and relevant feature docs.
2. Locate backend source of truth before changing mobile behavior.
3. Preserve existing endpoint contracts or add fields instead of renaming.
4. Add/update serializers and tests for backend behavior changes.
5. Update mobile types in `expo/lib/api.ts` when API payload changes.
6. Update docs when behavior, payments, meditation, or insights change.
7. Run backend tests for backend changes; run mobile lint/typecheck for mobile.
