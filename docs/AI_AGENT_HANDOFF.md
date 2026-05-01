# BhagwatGitaGuide — handoff for AI coding agents

**Purpose:** Upload or paste this file when starting or resuming work in GitHub Copilot Chat, Codex, Cursor, or similar tools. It summarizes architecture, conventions, and current scope so you do not need full repo exploration to be productive.

**Full-stack + mobile map:** see **`docs/KNOWLEDGE_BASE.md`** (API inventory, Django models, Expo screens, cross-links).

**Project:** Django + DRF backend for a Bhagavad Gita–based life guidance app (RAG + OpenAI generation, safety guardrails, auth, quota, mobile-friendly JSON APIs).

**Repo root:** `BhagwatGitaGuide/` (Django project `config/`, app `guide_api/`).
**Payments:** see root **`PAYMENT_INTEGRATION_ANALYSIS.md`** (Razorpay products, verify, webhooks, bridge URL) and **`docs/PAYMENT_AND_CHECKOUT_E2E_WORKFLOWS.md`** (end-to-end sequences).

**Optional:** **ITR Summary Generator** — income-tax computation PDF workflow mounted at
`ITR_URL_PREFIX` (default `/itr-computation/`). Toggle with **`ITR_ENABLED`**. Settings
patch in **`config/settings_itr.py`** (includes **`apps.accounts`** context processors
for **`google_oauth_configured`** / **`GOOGLE_OAUTH_CONFIGURED`**); routes
**`config/urls_itr.py`**; apps under **`apps.*`** (`documents`, `exports`, `billing`,
`marketing`, …). Same **`User`** as Gita; separate ITR billing/subscription models.
**Google web login:** set **`GOOGLE_CLIENT_ID`** + **`GOOGLE_CLIENT_SECRET`** for
django-allauth (redirect **`/accounts/google/login/callback/`**). PDF retention:
**`ITR_OUTPUT_RETENTION_HOURS`**, **`purge_itr_retention`** command,
**`apps/exports/retention.py`**. **WeasyPrint** CA-layout exports require OS libraries
(**Pango/cairo/GObject**) in the container—the repo **`Dockerfile`** installs them;
missing **`libgobject`** at runtime means the image was built without those packages.

---

## Stack

- Python 3.14, Django, Django REST Framework
- SQLite locally (`db.sqlite3`)
- OpenAI: chat (`OPENAI_MODEL`, default `gpt-4.1-mini`), embeddings (`OPENAI_EMBEDDING_MODEL`, default `text-embedding-3-small`)
- **Intent routing** (`guide_api/services.py`): `classify_user_intent` uses **heuristics first** (life/knowledge/casual). An optional **second** small LLM call (`DISABLE_INTENT_LLM_REFINEMENT`, **default true** = disabled) can disambiguate only when heuristics return `casual_chat` and the message passes length checks; set `DISABLE_INTENT_LLM_REFINEMENT=false` in `.env` when edge-case routing quality outweighs cost.
- Auth: session + basic + `Authorization: Token <token>` (DRF authtoken)
- **Performance & Scalability:**
  - **Caching:** Global in-memory `_get_all_verses_cached` in `services.py` for high-speed retrieval. Redis-based response caching for the Insights API (`views.py`).
  - **Optimization:** `GZipMiddleware` enabled for response compression. `CONN_MAX_AGE=600` for DB connection pooling.

---

## Production runtime (current)

- Hosting: Fly.io
- Primary app slug: `askbhagavadgita`
- Production DB: Neon PostgreSQL (via `DATABASE_URL` Fly secret)
- Free-cost mode currently supported via Fly auto-stop + zero min machines
- `fly.toml` includes static mapping to `/code/staticfiles`
- HTTPS proxy note: Django must trust forwarded proto header in production
  (`SECURE_PROXY_SSL_HEADER`) to avoid redirect loops

---

## Setup and commands

```bash
cp .env.example .env   # then set OPENAI_API_KEY if using LLM path
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # or requirements.lock.txt for pins
python manage.py migrate
python manage.py runserver
make test
```

Useful `Makefile` targets: `make run`, `make test`, `make setup`,
`ingest-gita-multiscript INPUT=/path/bhagavad-gita.xlsx`, `import-gita`,
`tag-gita-themes`, `embed-gita-verses`, `setup-pgvector-index`,
`sync-pgvector-embeddings`, `eval-retrieval`,
`auth-flow USERNAME=... PASSWORD=...`.

---

## Where logic lives (map)

| Area | Primary files |
|------|-----------------|
| HTTP / API surface | `guide_api/views.py`, `guide_api/urls.py`, `guide_api/permissions.py` |
| Retrieval + LLM + safety | `guide_api/services.py` |
| Serializers / validation | `guide_api/serializers.py` |
| Models | `guide_api/models.py` |
| Admin + analytics summaries | `guide_api/admin.py`, `guide_api/templates/admin/guide_api/askevent/change_list.html` |
| Growth event tracking | `guide_api/models.py` (`GrowthEvent`, `WebAudienceProfile`), `guide_api/views.py` (`_track_web_visit`, `_log_growth_event`, `AnalyticsEventIngestView`, `AnalyticsSummaryView`) |
| Manual web UI | `guide_api/templates/guide_api/chat_ui.html` |
| Project URLs (includes `/api/v1/` alias) | `config/urls.py` |
| Settings / env | `config/settings.py`, `.env.example` |
| Verse data / eval | `data/gita_700.json`, `data/Bhagwad_Gita.csv`, `data/gita_additional_angles.json`, `data/retrieval_eval_cases.json` |
| Management commands | `guide_api/management/commands/` (`ingest_gita_multiscript`, `import_gita`, `tag_gita_themes`, `embed_gita_verses`, `setup_pgvector_index`, `sync_pgvector_embeddings`, `eval_retrieval`, `growth_report`) |
| Tests | `guide_api/tests.py` |
| ITR (optional) | `apps/` (`documents`, `exports`, `billing`, …), `config/settings_itr.py`, `config/urls_itr.py`, `templates/` (ITR HTML), `static_itr/` |
| Meditation UX planning | `docs/MEDITATION_UX_BLUEPRINT.md` |

Long procedures are documented in `docs/DEVELOPER_GUIDE.md`; user-facing behavior in `docs/USER_GUIDE.md`. Build status and roadmap: `PROGRESS.md`, `README.md`.
Production command checklist lives in `docs/PRODUCTION_RUNBOOK.md`.

---

## API contract (high level)

- **Prefixes:** `/api/...` and **`/api/v1/...`** are equivalent (mobile versioning alias).
- **Errors:** Standardized envelope with `error.code`, `error.message`, and `detail` where applicable.
- **List endpoints:** Support `?limit=&offset=` where documented (e.g. feedback, saved-reflections).
- **Quota:** `POST /api/ask/` enforces plan limits (`free|plus|pro`) and may
  return `429`. Plan mock: `POST /api/auth/plan/`.
- **Language:** `POST /api/ask/` and `POST /api/follow-ups/` accept
  `language=en|hi` (defaults to `en`).

**Important routes** (under both `/api/` and `/api/v1/`):

- `GET health/`
- `POST auth/register/`, `auth/login/`, `auth/logout/`, `GET auth/me/`, `POST auth/plan/`
- `PATCH auth/profile/`, `POST auth/change-password/`,
  `POST auth/forgot-password/`, `POST auth/reset-password/confirm/`
- `GET|PATCH engagement/me/` — streak, reminder prefs (delivery not implemented yet)
- `GET starter-prompts/`, `GET plans/catalog/` — mobile onboarding/paywall metadata
- `POST ask/` — main Q&A (structured JSON: guidance, meaning, actions, reflection, verse_references, follow_ups, engagement snapshot, quota fields)
- `POST guest/ask/`, `GET guest/history/`, `POST guest/history/reset/`,
  `GET guest/recent-questions/` — guest/mobile parity session APIs
- `POST follow-ups/` — contextual follow-up prompts
- `POST mantra/` — verse as mantra for mood (calm/focus/courage/peace/strength/clarity); **auth required**
- `GET|POST quote-art/...` — styles, generate, featured; same **browser vs token** rule as chapter browse
- `GET chapters/` — list all 18 chapters with metadata for browsing
- `GET chapters/<chapter_number>/` — chapter detail with verse list
- `GET verses/<chapter>.<verse>/` — full verse detail with multi-author commentary
- `GET verses/search/?q=&limit=` — reader search helper
  - **Browse policy:** same-origin / browser-style `GET` (no `Authorization`
    header) is allowed so the chat UI reader works for guests and all plans.
    Requests authenticated with `Authorization: Token …` require **Plus or
    Pro**; **Free** token clients get `403` (`GitaBrowseAPIPermission` in
    `guide_api/permissions.py`).
- `GET|POST feedback/`
- `POST support/` — guest/auth support ticket intake
- `GET support/tickets/` — signed-in user ticket history
- `GET|POST saved-reflections/`, `DELETE saved-reflections/<id>/`
- `GET daily-verse/`, `GET daily-verse/history/` (payload includes **`meaning_plain`** for mobile Today + push copy)
- history under `history/me/`, `history/<user_id>/` (owner)
- `GET|POST|DELETE conversations/...` — mobile-native thread management
- `POST eval/retrieval/` — retrieval trace / benchmark (no generation); **auth required**
- payment/subscription: `payments/create-order` (body `product`: `subscription`
  default, `sadhana_cycle`, **`practice_workflow`** + `workflow_slug`),
  `payments/verify`, `payments/history`, `payments/status`, **`payments/checkout/bridge/`** (GET),
  `payments/webhook`, `subscription/status`
- **Practice workflows (curated sessions):** `GET practice/tags/`,
  `GET practice/workflows/?tag=<slug>`, `GET practice/workflows/<slug>/`,
  `GET practice/workflows/me/` — catalog + per-step tags; access modes
  `free_public` | `pro_included` | `purchase_required`. Purchases:
  `POST payments/create-order/` with `product=practice_workflow` and
  `workflow_slug`; prices on `PracticeWorkflow.purchase_price_minor_*`; enrollment
  opened by `POST payments/verify/` and Razorpay `payment.captured` webhook
  (`activate_workflow_enrollment`).
- device/reminder: `GET|PATCH notifications/preferences`,
  `GET devices/`, `POST devices/register`, `DELETE devices/<id>`;
  `manage.py send_push_reminders` sends Expo push for due profiles (cron).
- `GET|POST chat-ui/` — browser test UI (forms, CSRF, session-backed UX,
  separate threads, and sidebar conversation selection)

---

## Product semantics

- **Reflection (field):** Short contemplative takeaway in the structured LLM response.
- **Saved reflections:** User bookmarks of a response bundle + optional note; owner-scoped API for mobile reuse.

---

## Behavioral notes for changes

- Prefer **additive** API changes for mobile clients; avoid breaking field renames without version bump.
- **Safety:** Risky prompts are blocked before generation; events logged (`AskEvent` and related).
- **Fallback:** Without `OPENAI_API_KEY` or on failure, app uses deterministic local guidance (`response_mode` reflects this).
- **Conversation-aware guidance:** On the LLM path, the latest user message is
  the primary task. Recent thread history is passed as supporting context only.
- **Chat UI thread management:** Sidebar cards show compact metadata (title,
  message count, updated time) and can delete a thread without affecting
  unrelated saved reflections.
- **Chat UI global settings:** Sidebar language selector (`en`/`hi`) and mode
  selector apply to the next message across all threads.
- **Chat UI ownership model:** Signed-in users only see their own saved
  threads. Logged-out chat uses a session-only guest transcript and does not
  create `Conversation` rows or account-bound feedback/bookmarks.
- **Growth event tracking:** `_track_web_visit(request, source=)` is called from all landing views and chat-ui GET to upsert `WebAudienceProfile` + emit `landing_view` `GrowthEvent`. UTM params (`utm_source`, `utm_medium`, `utm_campaign`) from query strings are captured as first/last attribution fields. Frontend calls `POST /api/analytics/events/` to record `starter_click`, `share_click`, `copy_link_click`, and `ask_submit` events without blocking UX.
- **Analytics CLI:** `python manage.py growth_report` prints 7d and 30d windows: unique visitors, unique askers, queries fired/served, starter/share/ask rates, and top 10 UTM sources.
- **Support flow:** chat-ui now includes a support panel and support form;
  submissions persist as `SupportTicket` rows and are visible in Django admin.
- **Plan test controls:** any plan-switch utilities are intended for local
  debug/testing only, and should remain hidden in production UX.
- **Retrieval:** Hybrid + semantic path; tuning via `eval_retrieval` and `data/retrieval_eval_cases.json`.
- **Style:** Match existing code; keep lines PEP8-friendly (~79 chars) where the repo already does; run `make test` after non-trivial edits.

---

## Security

- Never commit real API keys or production `SECRET_KEY`. Use `.env` locally; `.env.example` documents variables only.
- Session-backed payment/subscription endpoints should keep normal CSRF protection enabled. Do not reintroduce CSRF-exempt session auth for billing actions.
- Production must set an explicit `SECRET_KEY`; the app now treats the old fallback key as invalid when `DEBUG=false`.
- Chapter/verse browse APIs are not intended as a public token-authenticated
  free tier: token auth on those routes requires Plus or Pro (see
  `GitaBrowseAPIPermission`). Unguarded anonymous HTTP access is unchanged for
  the web reader; further abuse mitigation would be rate limits or edge rules.

---

## Current status (snapshot)

**Implemented:** Auth + token, ask with quota, structured responses, follow-ups, saved reflections, support ticket intake (`/api/support/` + chat-ui support panel), engagement/streak/reminder **preferences** (storage only), chat-ui UX with guest-temporary chat plus account-owned conversation threads/sidebar metadata/delete controls, dedicated mobile thread APIs (`/api/conversations/...`), guest session APIs (`/api/guest/*`), account profile/password APIs, payment/subscription APIs, device registration APIs, admin ask analytics, retrieval eval pipeline, `/api/v1/` alias, standardized errors, pagination on relevant lists, bilingual guidance selection (`en`/`hi`) across API + chat-ui, viral landing (starter journey cards, share bar, trust blocks), unique visitor + query tracking (`WebAudienceProfile`), full growth analytics stack (`GrowthEvent`, UTM attribution, `analytics/events/`, `analytics/summary/`, admin funnel dashboard, `growth_report` CLI), in-memory verse-list cache + Redis Insights response cache, `GZipMiddleware` + `CONN_MAX_AGE` production optimizations, practice workflows (models, enrollment, per-currency pricing, checkout via Razorpay), `generate_verse_syntheses` management command, japa timer bell audio, weekly digest command, admin rate-throttle on auth endpoints, Insights API with Redis caching.

**Mobile companion app (2026-05-01 quality pass in `bhagavadgitaguide_mobile-main`):**
- 401 auto-logout via `setUnauthorizedHandler` / `AuthGate` integration
- `textDim` WCAG AA contrast fix, shared `dateUtils.ts`, `SacredMandala` on auth screens
- `SudarshanChakraLoader` replaces all `ActivityIndicator` usages
- `OfflineBanner` rewritten to use `@react-native-community/netinfo`
- `Background.tsx` pauses animations off-screen (battery saving)
- `SkeletonPulse` + `ask.tsx` streaming text accessibility props
- `ScreenHeader` standardized; `sadhana` cards with `FadeInView`/`PressScale`
- `Insights` tab fully built (4-tab segmented control, computed signals, interactive grids)
- TypeScript 0 errors, ESLint 0 warnings baseline enforced

Deployment/ops snapshot:
- live deployment on Fly is active
- Fly **`Dockerfile`** must include WeasyPrint OS dependencies if operators use the
  WeasyPrint PDF button on ITR (`libcairo`, `libpango`, `libglib2.0-0`, etc.)
- Neon-backed Postgres connectivity verified; migrations applied as released
- run `make test` locally for current count (`guide_api` suite is the main gate)
- if app appears slow after idle, this is expected in free mode due to cold starts
- if `/api/*` loops with repeated 301 redirects, re-check `SECURE_PROXY_SSL_HEADER`
- if shell shows SQLite in production unexpectedly, validate Fly `DATABASE_URL`
  secret value and redeploy
- if production fails to boot after deploy, verify Fly has a real `SECRET_KEY`
  secret set rather than relying on any local/dev fallback

**Explicitly not done / next waves:** Push or email **delivery** for reminders, **scheduled** reminder worker, automated **subscription renewal** beyond current Razorpay one-shot checkout + webhooks, possible **pgvector** migration for retrieval at scale (SQLite + embeddings in DB today), SEO FAQ schema markup for topic pages, shareable answer pages with og:image.

**See `PROGRESS.md` for the authoritative checklist** and “Next 3 Tasks” before large new scope.

---

## Session checklist for agents

1. Read this file + `PROGRESS.md` “Next 3 Tasks” / “Deferred”.
2. Run `make test` before and after substantive changes.
3. Update `PROGRESS.md` when finishing a milestone (per project convention).
4. For major frontend redesign or UI/UX polish work, read
   `docs/design-playbook.md` and follow the root `AGENTS.md` frontend redesign
   protocol before editing templates/styles.
5. If user-facing behavior changes, sync `docs/USER_GUIDE.md` or `docs/DEVELOPER_GUIDE.md` as appropriate.

---

*Last aligned with repo state: 2026-05-01. Edit this file when architecture, permissions, or major endpoints change. Mobile companion app state reflects `bhagavadgitaguide_mobile-main` quality pass from the same date.*

Current operational note:
- the app supports `DISABLE_ALL_QUOTAS=true` as a temporary operator switch to
  remove guest and signed-in ask caps without changing plan/payment code
- normal default posture is quota-on (`DISABLE_ALL_QUOTAS=false`)
- admin quota singleton lookups are protected by a short-lived cache so guest
  chat remains resilient if production Postgres is briefly slow
