# Web and Mobile Functionality Audit - 2026-05-17

Scope:

- Mobile app: `/Users/deecoderr/Work/Personal/Projects/bhagavadgitaguide_mobile-main`
- Backend and web portal: `/Users/deecoderr/Work/Personal/Projects/BhagwatGitaGuide`
- Purpose: re-analyse the changed repos end to end, map every major user workflow to its UI and API process, identify web/mobile parity gaps, and recommend improvements.

Important working-tree note:

- Both repos had existing uncommitted changes before this audit. Do not revert them casually.
- Mobile existing changes included `expo/app.json`, `expo/app/(tabs)/_layout.tsx`, `.DS_Store`, and generated AAB files.
- Backend existing changes included the shared web portal shell, account/meditation/privacy templates, and `guide_api/views.py`.

## Executive Summary

The product has grown into a full devotional guidance platform, not only an Ask UI. The current canonical mobile model is:

1. Today - daily cockpit and spiritual home.
2. Ask - Krishna/Gita guidance, guest/auth chat, history, feedback, saved reflections.
3. Meditate - practice hub that includes meditation types, japa, sadhana, workflows, and tracked sessions.
4. History - conversation threads.
5. Insights - progress, reading, ask, practice, and japa summaries.
6. You/Profile - account, plans, notifications, saved items, support, and personal settings.

The web app now has most of these pages, including newer `history`, `notifications`, and `support` pages. The biggest remaining issue is not page existence; it is contract drift. Some web pages still call old or missing API shapes while the mobile app is correctly using the newer backend contract. This creates pages that render but fail after client-side interaction.

Implementation update from the same day:

- Web Japa was updated to use the current commitment-first backend/mobile contract for create, detail, session start, pause, resume, finish-day, fulfill, archive, and page-leave abandonment.
- Web chapter detail now uses the chapter detail API payload instead of a missing verse-list endpoint.
- Web verse detail now uses the dot verse route.
- Today now reads Japa progress from `GET /api/v1/insights/me/` instead of a missing Japa summary endpoint.
- The shared web bottom navigation now follows the mobile mental model more closely: Today, Ask, Practice, History, Insights, You.

## Critical Findings

### Fixed - Web Japa is aligned with backend and mobile

Files:

- `guide_api/templates/guide_api/japa.html`
- `guide_api/serializers.py`
- `guide_api/japa_views.py`
- Mobile reference: `expo/app/japa/new.tsx`, `expo/app/japa/[id].tsx`

Problems:

- Web starts a session with `POST /api/v1/japa/sessions/start/`, but the backend route is `POST /api/v1/japa/commitments/<id>/sessions/start/`.
- Web creates commitments with `mantra_name`, `daily_target`, and `intention`, but the backend expects `title`, `focus_label`, `mantra_label`, `daily_target_malas`, `started_on`, optional `ends_on`, and optional `preferred_time`.
- Web finishes sessions with `elapsed_seconds` and `status`, but the backend expects `local_date` and `malas_completed`.
- Web renders fields like `daily_target`, `today_count`, `total_count`, `mantra_name`, and `is_active`; the backend returns `daily_target_malas`, `mantra_label`, status fields, active session, and daily completion data.

Impact:

- Japa page can load, but commitment creation, session start, completion, and progress UI are unreliable or broken.
- Insights will not receive meaningful practice data from web japa users.

Implemented:

- Web Japa now uses the mobile/backend flow as the canonical implementation.
- New commitments send `title`, `focus_label`, `mantra_label`, `daily_target_malas`, and `started_on`.
- Sessions start via `/api/v1/japa/commitments/<id>/sessions/start/`.
- Sessions finish via `/api/v1/japa/sessions/<session_id>/finish-day/` with `local_date` and `malas_completed`.
- The page supports selecting a commitment, pausing/resuming an active session, fulfilling a sankalpa, archiving a track, and abandoning an in-progress session on page leave.

### Fixed - Web chapter and verse detail fetches use current endpoints

Files:

- `guide_api/templates/guide_api/chapter_detail.html`
- `guide_api/templates/guide_api/verse_detail.html`
- `guide_api/urls.py`

Problems:

- Chapter detail fetches `/api/v1/verses/chapter/<chapter>/?language=...&page_size=100`, which is not registered.
- Verse detail fetches `/api/v1/verses/<chapter>/<verse>/?language=...`, but the backend route is `/api/v1/verses/<chapter>.<verse>/`.

Impact:

- Page shells return 200, but verse content can fail client-side.

Implemented:

- Chapter detail should fetch only `/api/v1/chapters/<chapter>/?language=...`, because that response already includes `chapter` and `verses`.
- Verse detail should fetch `/api/v1/verses/<chapter>.<verse>/?language=...`.
- Add a route smoke plus client endpoint contract test for these two pages.

### Fixed - Today page no longer calls a missing japa summary endpoint

File:

- `guide_api/templates/guide_api/today.html`

Problem:

- Today calls `/api/v1/japa/today-summary/`, but no such API route exists.

Impact:

- Japa progress cannot reliably appear on Today's web page.

Implemented:

- Today reuses `GET /api/v1/insights/me/` and extracts `japa.malas_logged_via_tracks_30d`.
- This avoids adding a redundant endpoint while keeping Today connected to the same insights source used elsewhere.

### Fixed - Web shell navigation is closer to the mobile canonical model

Files:

- Mobile: `expo/app/(tabs)/_layout.tsx`
- Web: `guide_api/static/guide_api/js/gita-web-portal.js`

Current mobile tabs:

- Today
- Ask
- Meditate
- History
- Insights
- You

Current web nav:

- Today
- Ask
- Read
- Practice
- Journal
- Insights

Implemented:

- Web bottom nav now uses Today, Ask, Practice, History, Insights, You.
- Read remains a quick-action route through `/read-gita/` instead of occupying a primary tab.
- Mood, Gratitude, Quote Art, Community, Plans, Support, and Notifications are grouped under You/Profile-style destinations or quick actions.

## End-to-End Workflow Map

### 1. Auth, Guest Mode, Onboarding, Account

Mobile UI:

- `/auth`
- `/onboarding`
- `/account`
- `(tabs)/profile`
- `/plans`
- `/payments/index`
- `/payments/callback`

Web UI:

- `/api/chat-ui/` auth modal and guest ask entry
- `/account/`
- `/plans/`
- `/reset-password/`
- shared portal auth slot in `gita-web-portal.js`

Backend APIs:

- `POST /api/v1/auth/register/`
- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/google/`
- `POST /api/v1/auth/logout/`
- `GET /api/v1/auth/me/`
- `PATCH /api/v1/auth/profile/`
- `POST /api/v1/auth/change-password/`
- `POST /api/v1/auth/forgot-password/`
- `POST /api/v1/auth/reset-password/confirm/`
- `GET /api/v1/plans/catalog/`
- payment APIs under `/api/v1/payments/*`

Current state:

- Mobile is the richer reference for account and payment callback UX.
- Web has shared auth slot, plans, and account pages.
- Auth token storage is duplicated across web templates and shared shell.

Improvements:

- Extract a shared web API/auth helper used by all templates.
- Standardize token lookup, error handling, CSRF, `credentials`, and redirect behavior.
- Add a payment history panel on web account/plans if not already visible enough.
- Make guest versus signed-in state clearer on every web page.

### 2. Ask Guidance

Mobile UI:

- `(tabs)/ask`
- `/conversation/[id]`
- helpful/not helpful feedback controls
- save reflection and share flows

Web UI:

- `/api/chat-ui/`
- shared answer page `/share/<uuid>/`
- `/history/`
- `/saved-reflections/`

Backend APIs:

- `POST /api/v1/ask/`
- `POST /api/v1/ask/stream/`
- `POST /api/v1/guest/ask/`
- `GET /api/v1/guest/history/`
- `POST /api/v1/guest/history/reset/`
- `GET /api/v1/conversations/`
- `POST /api/v1/conversations/`
- `GET /api/v1/conversations/<id>/messages/`
- `DELETE /api/v1/conversations/<id>/`
- `POST /api/v1/feedback/`
- `GET|POST /api/saved-reflections/`

Current state:

- Ask appears mature on both surfaces.
- Backend has intent-aware answer generation work from earlier sessions.
- The user-facing quality goal remains: answer exactly what was asked; do not force actions, reflections, or related verses when they are not needed.

Improvements:

- In the web answer renderer, make optional sections truly optional: Meaning, Context, Actions, Reflection, Verses Used, Related Verses.
- Add a UI explanation for why each cited verse was selected.
- Show related verses only if the LLM/reranker marks them highly relevant.
- Add "too much advice" and "wrong verse" feedback tags, not only helpful/not helpful.
- Feed feedback into review queue and future retrieval eval cases.

### 3. Today Home

Mobile UI:

- `(tabs)/index`
- daily verse signal
- Ask, practice, read, saved, community, mood, gratitude, streak/insight prompts

Web UI:

- `/today/`

Backend APIs:

- `GET /api/daily-verse/`
- `GET /api/v1/daily-verse/history/`
- `GET /api/v1/insights/me/`
- `GET|POST /api/v1/mood/`
- `GET|POST /api/v1/gratitude/`
- `GET /api/v1/verses/<ref>/?include=synthesis`
- `GET /api/community/posts/`

Current state:

- Web page renders and has many mobile-like sections.
- One client API call is stale: `/api/v1/japa/today-summary/`.

Improvements:

- Reduce redundancy: Today should not be a directory of all features.
- Recommended Today blocks:
  - Morning welcome and one primary CTA.
  - Today's verse with Sanskrit, translation, short personal meaning, and "Read full context".
  - Continue where you left off: latest conversation, reading path, active japa, or meditation.
  - Quick check-in: mood and gratitude.
  - One practice prompt: ask, japa, meditation, or sadhana based on recent behavior.
- Use the same priority engine for mobile and web so Today feels intelligent rather than static.

### 4. Reading and Scripture Study

Mobile UI:

- `(tabs)/read` hidden from bottom nav
- `/read-journey`
- `/chapter/[number]`
- `/verse/[ref]`
- `/verse-reader`

Web UI:

- `/read-gita/`
- `/read-journey/`
- `/read/chapter/<number>/`
- `/read/<chapter>.<verse>/`

Backend APIs:

- `GET /api/chapters/`
- `GET /api/chapters/<chapter>/`
- `GET /api/v1/verses/<chapter>.<verse>/`
- `GET /api/v1/verses/search/`
- `POST /api/v1/reading/state/`
- `POST /api/v1/reading/verse-open/`
- `GET|POST /api/v1/reading/gita-path/`
- `POST /api/v1/reading/gita-path/start/`
- `POST /api/v1/reading/gita-path/advance/`
- `POST /api/v1/reading/gita-path/abandon/`
- `GET|POST /api/v1/verses/<ref>/note/`

Current state:

- Reading exists on both platforms.
- Web chapter and verse detail client fetches need endpoint correction.

Improvements:

- Add "Why Krishna says this here" context block on verse pages.
- Add commentary tabs/summaries where backend data exists.
- Add "Explain this to me" CTA from every verse into Ask with exact verse context.
- Add reading continuity state across web and mobile.
- Improve search result ranking and empty-state suggestions.

### 5. Meditation, Practice, Sadhana, and Japa

Mobile UI:

- `(tabs)/meditate`
- `/meditation/index`
- `/meditation/[slug]`
- `/meditation/content/[id]`
- `/meditation/type-insights/[slug]`
- `/japa/index`
- `/japa/new`
- `/japa/[id]`
- `/sadhana/index`
- `/sadhana/[slug]/index`
- `/sadhana/[slug]/day/[dayNumber]`
- `/practice/index`
- `/practice/[slug]`

Web UI:

- `/meditation/`
- `/japa/`
- `/sadhana/`
- `/practice/`

Backend APIs:

- `GET /api/v1/meditation/types/`
- `GET /api/v1/meditation/types/<slug>/`
- `GET /api/v1/meditation/contents/`
- `GET /api/v1/meditation/contents/<id>/`
- `POST /api/v1/meditation/sessions/start/`
- `POST /api/v1/meditation/sessions/<id>/complete/`
- `POST /api/v1/meditation/sessions/<id>/interrupt/`
- `GET /api/v1/meditation/sessions/recent/`
- `GET /api/v1/meditation/insights/`
- `GET /api/v1/meditation/type-insights/<slug>/`
- `GET|POST /api/v1/japa/commitments/`
- `GET|PATCH|DELETE /api/v1/japa/commitments/<id>/`
- `POST /api/v1/japa/commitments/<id>/sessions/start/`
- `POST /api/v1/japa/sessions/<id>/pause/`
- `POST /api/v1/japa/sessions/<id>/resume/`
- `POST /api/v1/japa/sessions/<id>/finish-day/`
- `POST /api/v1/japa/sessions/<id>/abandon/`
- `GET /api/v1/sadhana/programs/`
- `GET /api/v1/sadhana/programs/<slug>/`
- `POST /api/v1/sadhana/programs/<slug>/day/<day>/complete/`
- `GET /api/v1/practice/workflows/`
- `GET /api/v1/practice/workflows/<slug>/`
- `POST /api/v1/practice/log/`
- `POST /api/v1/practice/meditation-sessions/`

Current state:

- Mobile has the more complete multi-route structure.
- Web meditation page has a strong single-page practice workspace.
- Web japa is behind and must be fixed first.

Improvements:

- Treat Meditate as the umbrella "Practice" hub across both apps.
- Add a reusable practice model in the frontend:
  - learn mode
  - practice-together mode
  - timer/media player
  - optional sankalpa
  - completion reflection
  - streak/insight update
  - free/plus/pro/exclusive purchase locks
- Make adding new meditation types data-driven from backend content.
- Make all practice cards show the same access language: Free, Plus, Pro, or One-time unlock.

### 6. Insights and Progress

Mobile UI:

- `(tabs)/insights`
- streak reveal modal
- practice, japa, read journey, saved, and ask summary links

Web UI:

- `/insights/`

Backend APIs:

- `GET /api/v1/insights/me/`
- `GET|PATCH /api/v1/engagement/me/`
- `POST /api/v1/streak/freeze/`

Current state:

- Both apps use insights as a personal dashboard.
- Backend already aggregates ask, reading, japa, meditation, and engagement data.

Improvements:

- Add clearer "why this matters" explanations for streak, japa, meditation, and reading.
- Add weekly reflection: "What Krishna's guidance has been pointing you toward this week."
- Add unlockable insight cards for Plus/Pro, but keep basic progress free.
- Ensure every tracked practice updates insights quickly on both web and mobile.

### 7. History, Saved Reflections, Mood, Gratitude, Quote Art

Mobile UI:

- `(tabs)/history`
- `/saved-reflections`
- `/saved-reflection/[id]`
- `/mood`
- `/gratitude`
- `/quote-art`

Web UI:

- `/history/`
- `/saved-reflections/`
- `/mood/`
- `/gratitude/`
- `/quote-art/`

Backend APIs:

- conversations endpoints
- saved-reflections endpoints
- `GET|POST /api/v1/mood/`
- `GET|POST /api/v1/gratitude/`
- `GET /api/v1/quote-art/styles/`
- `POST /api/v1/quote-art/generate/`
- `GET /api/v1/quote-art/featured/`

Current state:

- Web has the pages and mobile has richer route detail pages.

Improvements:

- Add web saved-reflection detail parity if not already deep-linkable enough.
- Allow mood/gratitude to feed Ask context intentionally, not silently.
- Add "turn this answer into quote art" from saved reflection and shared answer pages.
- Add better empty states: examples, starter cards, and why the feature matters.

### 8. Community, Support, Notifications

Mobile UI:

- `/community`
- `/support`
- `/notifications`
- notification routing in root layout

Web UI:

- `/community/`
- `/support/`
- `/notifications/`

Backend APIs:

- `GET|POST /api/community/posts/`
- `GET|POST /api/v1/support/`
- `GET /api/v1/support/tickets/`
- `GET|PATCH /api/v1/notifications/preferences/`
- `GET /api/v1/devices/`
- `POST /api/v1/devices/register/`
- `DELETE /api/v1/devices/<id>/`

Current state:

- Support and notifications pages now exist on web.
- Mobile can register push devices; web currently should not pretend it can unless a web-push implementation is added.

Improvements:

- Web notifications page should clearly say "mobile reminders are managed by the app" if web push is unavailable.
- Community needs moderation/flag UX before being promoted heavily.
- Add support ticket status timeline on both web and mobile.

## UI/UX Improvement Direction

Use the mobile devotional/consciousness theme as the source of truth:

- Deep consciousness background instead of generic dark panels.
- Gold, rose, tulsi, cream, and soft aura accents.
- Glass cards with meaningful hierarchy, not every card equally bright.
- Sacred atmosphere/VFX as a subtle layer, not as decoration that competes with reading.
- Fewer duplicate entry cards.
- Stronger active/empty/loading/error states.
- More "parent/guide" tone in microcopy: compassionate, clear, and personal.

Recommended screen philosophy:

- Today answers: "What should I do now?"
- Ask answers: "What is Krishna/Gita saying to me here?"
- Practice answers: "How do I embody it?"
- History answers: "What have I already asked?"
- Insights answers: "What is changing in me?"
- You answers: "How do I manage my journey?"

## Testing and QA Recommendations

Add these tests before large UI rewrites:

1. Django route render smoke tests for all web pages.
2. Client endpoint contract tests for high-risk templates:
   - Today
   - Chapter detail
   - Verse detail
   - Japa
   - Meditation
   - Plans
   - Account
3. API contract tests that compare mobile/web expected payload fields for:
   - japa commitment list/create/detail
   - japa session start/pause/resume/finish/abandon
   - verse detail
   - chapter detail
   - insights summary
4. Browser QA using the in-app browser or Playwright after JS-heavy changes.
5. Visual QA screenshots for mobile-sized web pages, because web is being designed as a mobile-like portal.

Targeted smoke check performed during this audit:

- `/today/` returned 200
- `/history/` returned 200
- `/read/chapter/1/` returned 200
- `/read/2.47/` returned 200
- `/japa/` returned 200
- `/meditation/` returned 200
- `/notifications/` returned 200
- `/support/` returned 200

Original client-side endpoint validation found these missing or stale endpoints, which are now addressed in the web code:

- `/api/v1/verses/chapter/1/` returned 404
- `/api/v1/verses/2/47/` returned 404
- `/api/v1/verses/2.47/` returned 200
- `/api/v1/japa/today-summary/` returned 404
- `/api/v1/japa/sessions/start/` returned 404

Post-fix verification performed:

- Shared web shell syntax check passed.
- Inline scripts for Japa, Today, Chapter detail, and Verse detail parsed successfully after template-variable substitution.
- Targeted page shells returned 200 for Today, History, Read chapter, Read verse, Japa, Meditation, Notifications, Support, and Read Gita.
- `python manage.py check` completed with no issues.
- Authenticated Japa API smoke passed for commitment create, detail, session start, pause, resume, and finish-day.

## Recommended Implementation Order

1. Extract a shared web API/auth helper.
2. Add route and endpoint contract tests for the fixed web workflows.
3. Upgrade Today into a personalized cockpit with fewer duplicate cards.
4. Bring Practice/Meditation/Japa/Sadhana into one coherent data-driven UX.
5. Add deeper feedback tags and route low-quality answers into eval/review workflows.
6. Run browser QA and mobile visual QA before release.

## Best Next Task

The best next engineering task is to add automated contract tests and then extract a shared web API/auth helper, so this drift does not return as more templates are added.
