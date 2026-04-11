# Bhagwat Gita Guide - Progress Tracker

Last updated: 2026-04-11

## Completed

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
- Added public SEO landing pages at `/`, `/bhagavad-gita-for-anxiety/`, `/bhagavad-gita-for-career-confusion/`, and `/bhagavad-gita-for-relationships/` with dedicated metadata, focused copy, curated verses, and direct CTAs into the app.

## How To Update This File

At the end of each coding session:
- Move completed items from "Remaining" to "Completed".
- Add any new scope under "Remaining".
- Update "Next 3 Tasks" so the next session can start immediately.
