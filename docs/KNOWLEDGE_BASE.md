# Bhagavad Gita Guide — full-stack knowledge base

**Purpose:** Single reference for AI agents and humans: what the product does, where code lives, how backend and mobile connect. Keep this file updated when you add major features or routes.

**Companion repos (typical local layout):**

| Repository | Role |
|------------|------|
| `BhagwatGitaGuide/` | Django API, web chat UI, SEO site, admin, payments |
| `bhagavadgitaguide_mobile-main/` | Expo (React Native) iOS/Android app |

**Also read:** `docs/AI_AGENT_HANDOFF.md`, `PROGRESS.md`, `docs/DEVELOPER_GUIDE.md`, mobile `AGENTS.md`, `PAYMENT_INTEGRATION_ANALYSIS.md`.

**Mobile user journeys (Mermaid):** `docs/USER_APP_FLOWS.md`

**Deep companion notes:** `docs/CODEBASE_KNOWLEDGE_BASE.md` now contains a
backend-focused feature map generated from the full codebase review. The mobile
repo also has `CODEBASE_KNOWLEDGE_BASE.md` for the Expo app screen/API map.

---

## 1. Product intent

- **Bhagavad Gita–grounded guidance:** Users ask life questions; the system answers with structured spiritual guidance, verse references, optional commentary depth, and safety guardrails—not generic chat.
- **Reading:** Browse 18 chapters, verse detail (translations, themes, optional AI synthesis), search.
- **Practice:** Daily verse, naam-japa section on web home, **Sadhana** (paid structured multi-day programs), **practice workflows** (tagged curated sessions; free / Pro / purchase), **personal japa commitments** with session timers, **practice logs** (japa rounds, meditation minutes, read minutes), **meditation session logs**, **reading state** (streak, last verse, verses opened).
- **Community:** Threaded posts (`CommunityPost`), web wall + API; mobile full-screen community.
- **Account & growth:** Token auth, plans (free/plus/pro), quotas, engagement/streak/reminder **preferences**, Expo **push** reminders, optional email in prefs.
- **Monetization:** Razorpay—subscriptions, sadhana cycle purchases, practice workflow purchases; web checkout bridge for hosted payment pages.

---

## 2. Backend (`BhagwatGitaGuide`)

### 2.1 Stack & runtime

- **Django + DRF**, SQLite locally, **PostgreSQL** on Fly (Neon) in production.
- **OpenAI** for chat + embeddings; deterministic fallback when no key or on failure.
- **Auth:** Session (web) + `Authorization: Token <key>` (mobile/API).
- **URL aliases:** `config/urls.py` mounts `guide_api.urls` at both **`/api/`** and **`/api/v1/`** (identical routes).

### 2.2 Entry points

| Path | File / notes |
|------|----------------|
| HTTP API routes | `guide_api/urls.py` |
| Giant view module | `guide_api/views.py` (Ask, auth, browse, payments, chat-ui, SEO helpers, …) |
| Intent + RAG + LLM | `guide_api/services.py` (`classify_user_intent`, retrieval, generation, guardrails) |
| Validation / DRF serializers | `guide_api/serializers.py` |
| Permission classes | `guide_api/permissions.py` (e.g. `GitaBrowseAPIPermission`: browser without token OK; **token + Free plan → 403** on chapter/verse quote-art JSON APIs) |
| Data models | `guide_api/models.py` |
| Tests | `guide_api/tests.py` (primary gate: `make test`) |

### 2.3 Feature-specific backend modules

| Module | Responsibility |
|--------|----------------|
| `user_insights_summary.py` | **`GET …/insights/me/`** — aggregates journey snapshot (conversations, saved reflections, verse companions, recent asks, community counts, sadhana, reading, practice rollups, `japa_insights_for_user`). |
| `japa_views.py` | Japa commitments CRUD, sessions (start/pause/resume/finish-day/abandon), fulfill; **`japa_insights_for_user`**. |
| `sadhana_views.py` | Sadhana program list/detail/day, day completion, enrollments; web **PracticeHubView**. |
| `practice_workflow_views.py` | Practice tags, workflow list/detail, **`/practice/workflows/me/`**. |
| `push_reminders.py` + `management/commands/send_push_reminders.py` | Expo push for reminder due users (cron). |
| `subscription_helpers.py` | Plan normalization, subscription/workflow/sadhana activation helpers. |
| `google_auth.py` | Google token exchange for mobile/web flows where used. |
| `staff_views.py` | **Staff course studio** (`/staff/course-studio/`). |
| `middleware.py` | Canonical host / HTTPS helpers per production notes. |
| `web_urls.py` | Public SEO pages: landing index, topic pages, FAQ archive, daily verse hub, **community wall**, **practice hub**, privacy, delete-account, **shareable answers**, robots/sitemap. |

### 2.4 Web-only surfaces

| Surface | Purpose |
|---------|---------|
| `guide_api/templates/guide_api/chat_ui.html` | Main interactive chat: threads, guest vs logged-in, reader embed, naam japa, community preview, support panel, language/mode. |
| SEO topic landings | `SEO_LANDING_PAGES` in views + `web_urls.py` slugs. |
| `/api/chat-ui/` | Chat UI HTML + session-backed behavior (CSRF). |
| `/share/<uuid>/` | Shareable answer cards (`SharedAnswer`). |

### 2.5 Optional ITR app (same Django project)

- Toggle **`ITR_ENABLED`**. Routes: `config/urls_itr.py`, settings patch `config/settings_itr.py`.
- **Separate** product area (documents, exports, billing apps under `apps/`). Shares **`User`** model with Gita.
- **Not** required for Gita mobile/backend features.

### 2.6 Domain models (concise)

| Model | Role |
|-------|------|
| `Verse`, `VerseSynthesis` | Gita text + optional AI synthesis per verse. |
| `Conversation`, `Message` | Chat threads (`user_id` string ties to username). |
| `GuestChatIdentity` | Guest caps / daily usage. |
| `UserSubscription`, `BillingRecord`, `DailyAskUsage`, `RequestQuotaSettings` | Plans, payments, quotas. |
| `AskEvent` | Analytics / safety logging for asks. |
| `WebAudienceProfile`, `GrowthEvent` | Landing attribution, UTM, funnel analytics. |
| `SavedReflection` | Bookmarked responses + notes + verse refs. |
| `UserEngagementProfile`, `EngagementEvent` | Streak, reminder prefs, `reminder_language`, last push dedupe fields. |
| `SupportTicket` | Support requests from API + chat UI. |
| `NotificationDevice` | Expo push tokens. |
| `QuoteArt` | Generated quote art metadata. |
| `CommunityPost` | Threaded community (parent optional). |
| `SharedAnswer` | Public share links. |
| `SadhanaProgram`, `SadhanaDay`, `SadhanaStep`, `SadhanaEnrollment`, `SadhanaDayCompletion` | Guided programs. |
| `PracticeTag`, `PracticeWorkflow`, `PracticeWorkflowStep`, `PracticeWorkflowEnrollment` | Curated workflow catalog + purchases. |
| `VerseUserNote` | Per-user verse notes. |
| `UserReadingState` | Read streak, last verse, `verses_seen`. |
| `PracticeLogEntry` | japa rounds / meditation minutes / read minutes by day. |
| `MeditationSessionLog` | Meditation session records (e.g. from mobile meditate flow). |
| `JapaCommitment`, `JapaSession`, `JapaDailyCompletion` | Personal japa tracks. |

### 2.7 API route inventory (`/api/` = `/api/v1/`)

**System & auth:** `health/`, `starter-prompts/`, `plans/catalog/`, `auth/register|login|logout|me|profile|change-password|forgot-password|reset-password/confirm|plan/`, `auth/google/`  

**Engagement & insights:** `engagement/me/`, `insights/me/`  

**Notifications:** `notifications/preferences/`, `devices/`, `devices/register/`, `devices/<id>/`  

**Core Q&A:** `ask/`, `guest/ask/`, `guest/history/`, `guest/history/reset/`, `guest/recent-questions/`, `follow-ups/`, `mantra/`  

**Analytics:** `analytics/events/`, `analytics/summary/`  

**Quote art:** `quote-art/styles/`, `quote-art/generate/`, `quote-art/featured/`  

**Reader:** `daily-verse/`, `daily-verse/history/`, `chapters/`, `chapters/<n>/`, `verses/<ch>.<v>/`, `verses/<ch>.<v>/note/`, `verses/search/`, `reading/state/`, `reading/verse-open/`  

**Practice:** `practice/log/`, `practice/meditation-sessions/`, `practice/tags/`, `practice/workflows/`, `practice/workflows/me/`, `practice/workflows/<slug>/`  

**Japa:** `japa/commitments/`, `japa/commitments/<id>/`, `japa/commitments/<id>/fulfill/`, `japa/commitments/<id>/sessions/start/`, `japa/sessions/<id>/pause|resume|finish-day|abandon/`  

**History & threads:** `history/me/`, `history/<user_id>/`, `conversations/`, `conversations/<id>/`, `conversations/<id>/messages/`  

**Community:** `community/posts/`, `community/posts/<id>/`  

**Feedback & support:** `feedback/`, `support/`, `support/tickets/`  

**Saved content:** `saved-reflections/`, `saved-reflections/<id>/`, `answers/share/`  

**Eval:** `eval/retrieval/` (auth required)  

**Payments:** `payments/create-order/`, `payments/verify/`, `payments/history/`, `payments/status/`, `payments/checkout/bridge/`, `payments/webhook/`, `subscription/status/`  

**Sadhana:** `sadhana/programs/`, `sadhana/programs/<slug>/`, `sadhana/programs/<slug>/days/<n>/`, `sadhana/programs/<slug>/days/<n>/complete/`, `sadhana/me/`  

**Chat UI:** `chat-ui/`  

---

## 3. Mobile app (`bhagavadgitaguide_mobile-main`)

### 3.1 Stack

- **Expo Router** (file-based routes), **React Query**, **AsyncStorage** for token.
- **Default API host:** `expo/lib/api.ts` → `API_BASE` (`https://askbhagavadgita.co.in`). Paths are appended (`/api/...` or `/api/v1/...`).
- **i18n:** `providers/i18n.tsx` — large inline `en` / `hi` string maps (not separate JSON files).

### 3.2 Auth model

- **`providers/auth.tsx`:** Login/register → `POST /api/auth/login/` and `/api/auth/register/` → stores **token + username**; optional **guest mode** (no token, guest APIs).
- Logout clears session; attempts push unregister via `lib/pushRegistration.ts`.
- **`AuthGate`** in `app/_layout.tsx:** Unauthenticated non-guest users → `/auth`; authed users skip auth screen.

### 3.3 Navigation map (Expo Router)

| Route file | Screen purpose |
|------------|----------------|
| `app/(tabs)/index.tsx` | **Today** — daily verse, shortcuts, naam japa section, community preview, healing CTAs |
| `app/(tabs)/ask.tsx` | **Ask** — guest or authed ask, conversations, save reflection, feedback |
| `app/(tabs)/read.tsx` | **Read** — chapter list, verse search |
| `app/(tabs)/history.tsx` | Conversation list / delete |
| `app/(tabs)/insights.tsx` | Journey insights (`GET /api/v1/insights/me/`) |
| `app/(tabs)/meditate.tsx` | Workflow catalog + guided meditate logging (`meditation-sessions`, `practice/log`) |
| `app/(tabs)/profile.tsx` | Saved reflections list, note edits, reminder language PATCH |
| `app/auth.tsx` | Login / register / guest |
| `app/chapter/[number].tsx` | Chapter verses |
| `app/verse/[ref].tsx` | Verse detail, note, reading open |
| `app/conversation/[id].tsx` | Thread continuation + ask |
| `app/saved-reflection/[id].tsx` | Saved reflection detail / delete |
| `app/community.tsx` | Full community feed |
| `app/sadhana/index.tsx`, `[slug]/index.tsx`, `[slug]/day/[dayNumber].tsx` | Sadhana browse + day player |
| `app/practice/index.tsx`, `practice/[slug].tsx` | Practice workflows + purchase |
| `app/japa/index.tsx`, `japa/new.tsx`, `japa/[id].tsx` | Japa commitments |
| `app/plans.tsx`, `app/payments/*.tsx` | Plans, checkout bridge, verify callback, history |
| `app/account.tsx` | Profile PATCH, password change |
| `app/notifications.tsx` | Reminder prefs + device registration |
| `app/support.tsx` | Support tickets + new ticket |
| `app/quote-art.tsx` | Quote art (Plus/Pro browse policy applies when using token) |

### 3.4 Mobile → API mapping (primary)

| Feature | Endpoints used (typical) |
|---------|---------------------------|
| Session | `/api/auth/*` (non-v1 prefix in code) |
| Ask | `/api/v1/ask/` or `/api/v1/guest/ask/`, guest history/reset |
| Conversations | `/api/v1/conversations/`, `.../messages/` |
| Saved reflections | `/api/saved-reflections/` (list/create/delete — mixed `/api/` prefix in app) |
| Daily verse | `/api/daily-verse/` |
| Chapters / verse | `/api/chapters/`, `/api/v1/verses/...`, `/api/v1/verses/search/` |
| Verse note / reading | `/api/v1/verses/.../note/`, `/api/v1/reading/verse-open/` |
| Insights | `/api/v1/insights/me/` |
| Community | `/api/community/posts/` |
| Sadhana | `/api/v1/sadhana/programs/`, program detail, day detail |
| Practice workflows | `/api/v1/practice/tags/`, `workflows/`, `workflows/<slug>/`, payments |
| Meditate tab | `/api/v1/practice/workflows/`, `practice/meditation-sessions/`, `practice/log/` |
| Japa | `/api/v1/japa/commitments/`, sessions, fulfill |
| Plans / pay | `/api/v1/plans/catalog/`, `subscription/status/`, `payments/*` |
| Notifications | `/api/v1/notifications/preferences/`, `devices/` |
| Support | `/api/v1/support/`, `support/tickets/` |
| Quote art | `/api/v1/quote-art/*` |

**Note:** Mobile mixes `/api/...` and `/api/v1/...`; both are valid on the server.

### 3.5 Shared libraries (`expo/lib/`)

| File | Role |
|------|------|
| `api.ts` | `API_BASE`, `api()` fetch wrapper with token, types for DTOs |
| `pushRegistration.ts` | Register/delete Expo push token with API |
| `verseRef.ts` | Parse / format verse refs |
| `sadhanaPlayback.ts` | Sadhana step media helpers |
| `reflectionDisplay.ts`, `conversationDisplay.ts` | UI helpers |

### 3.6 Native widgets

- **`expo/modules/widget-app-group`:** App group bridge for **iOS/Android home screen widgets** (e.g. daily verse snapshot from Today screen via `setDailyVerseWidgetSnapshot`).

### 3.7 Push behavior

- **`app/_layout.tsx`:** Notification tap with `type === "daily_reminder"` navigates to `/verse/<chapter>.<verse>`.
- Backend `send_push_reminders` uses engagement profile + device tokens.

---

## 4. Cross-cutting behavior

- **Quotas:** `POST /api/ask/` enforces plan limits; `429` when exhausted; operator flag `DISABLE_ALL_QUOTAS` in backend docs.
- **Language:** `language` / `lang` query or body fields (`en` | `hi`) on ask and reader endpoints as documented in `DEVELOPER_GUIDE.md`.
- **Payments:** Native Razorpay return → mobile **`/payments/callback`** → `POST /api/v1/payments/verify/`. Web uses checkout bridge URL. See `PAYMENT_INTEGRATION_ANALYSIS.md` and `docs/PAYMENT_AND_CHECKOUT_E2E_WORKFLOWS.md`.
- **Browse API policy:** Mobile uses token on verse/chapter calls; **Free** users may get **403** on token-authenticated Gita JSON routes—browser without `Authorization` remains allowed for web reader parity.

---

## 5. Gaps / backend features not obvious in mobile grep

- **`POST …/sadhana/.../complete/`** — exists on API for marking day complete; mobile day screen may show playback without calling complete (verify product intent before relying).
- **`GET engagement/me/`** — full engagement profile beyond insights snapshot; mobile may use insights + notifications prefs instead.
- **`POST follow-ups/`**, **`POST mantra/`**, **`GET daily-verse/history/`**, **`GET reading/state/`** — may be web-only or future mobile.
- **`POST eval/retrieval/`** — dev/eval tool, auth required.
- **Starter prompts** — mobile may not call `starter-prompts/` if not in current tabs.

---

## 6. Maintenance checklist

When adding a feature:

1. Implement backend route in `guide_api/urls.py` + view (or split module like `japa_views.py`).
2. Prefer **`/api/` and `/api/v1/`** parity (same `include`).
3. Add types to mobile `expo/lib/api.ts` if mobile consumes it.
4. Update this **`KNOWLEDGE_BASE.md`** section + `PROGRESS.md` + `AI_AGENT_HANDOFF.md` if API inventory changes materially.
5. Run **`make test`** in `BhagwatGitaGuide`.

---

*Generated for agent continuity; last structured pass: 2026-04-27.*
