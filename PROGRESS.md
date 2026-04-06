# Bhagwat Gita Guide - Progress Tracker

Last updated: 2026-04-06

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
