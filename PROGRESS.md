# Bhagwat Gita Guide - Progress Tracker

Last updated: 2026-04-04

## Completed

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

## In Progress

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
- Stripe integration and plan gates.

## Next 3 Tasks (Recommended)

1. Add push/email delivery service integration for reminder preferences.
2. Add Stripe checkout and paid entitlement lifecycle hooks.
3. Add automated nightly reminder job/worker for due users.

## Deferred (Do Later)

- Additional retrieval tuning iterations beyond current `0.78` hit rate (deferred).

## How To Update This File

At the end of each coding session:
- Move completed items from "Remaining" to "Completed".
- Add any new scope under "Remaining".
- Update "Next 3 Tasks" so the next session can start immediately.
