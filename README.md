# Bhagwat Gita Guide API

DRF backend for a Bhagavad Gita–based life guidance app (RAG + OpenAI, auth, quota, growth analytics).

See `PROGRESS.md` for live build status and next milestones.
Run `make test` for the current test count (see `guide_api/tests.py`).

## Documentation

- User documentation: `docs/USER_GUIDE.md`
- Developer documentation: `docs/DEVELOPER_GUIDE.md`
- Production operations runbook: `docs/PRODUCTION_RUNBOOK.md`
- AI / coding-agent handoff: `AGENTS.md` (start here) and `docs/AI_AGENT_HANDOFF.md`

## Stack

- Django + Django REST Framework
- SQLite for local development
- Python 3.14
- Production deploy: Fly.io app + Neon PostgreSQL

## Production Deployment (Current)

- Primary app slug: `askbhagavadgita`
- Live URL: `https://askbhagavadgita.fly.dev/`
- Legacy URL (if still retained): `https://bhagwatgitaguide.fly.dev/`
- Runtime DB in production: Neon Postgres via Fly `DATABASE_URL` secret

### Free-Cost Runtime Mode

To stay in strict low-cost mode on Fly:

- `auto_stop_machines = 'stop'`
- `min_machines_running = 0`
- `ENABLE_SEMANTIC_RETRIEVAL=false` (optional speed/cost trade-off)
- `OPENAI_API_KEY=''` to disable paid LLM generation path entirely

Note: in free mode, the first request after idle may be slower due to machine
cold start.

## Quick Start

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Reproducible Setup (Recommended)

Use the lock file to install exact versions:

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock.txt
python manage.py migrate
python manage.py runserver
```

## Makefile Shortcuts

Use these to speed up daily work:

```bash
make setup        # create venv + install requirements.txt + migrate
make setup-lock   # create venv + install requirements.lock.txt + migrate
make run          # start Django server
make test         # run test suite
make lock         # refresh requirements.lock.txt from current venv
make convert-gita-csv INPUT=data/Bhagwad_Gita.csv  # convert Kaggle CSV to JSON
make ingest-gita-multiscript INPUT=/path/bhagavad-gita.xlsx  # add supplemental angles from multi-script CSV/XLSX
make import-gita FILE=data/gita_700.json  # import full verse dataset
make tag-gita-themes  # auto-tag themes using verse text
make embed-gita-verses  # generate OpenAI embeddings for semantic retrieval
make setup-pgvector-index  # create pgvector extension/table/index (PostgreSQL)
make sync-pgvector-embeddings  # sync Verse.embedding -> pgvector table
make eval-retrieval  # run retrieval eval on labeled prompts
make auth-flow USERNAME=demo-user PASSWORD=demo-pass-123  # auth + ask + history smoke flow
make auth-flow-benchmark USERNAME=demo-user PASSWORD=demo-pass-123  # auth + retrieval benchmark + ask
make auth-flow-benchmark-summary USERNAME=demo-user PASSWORD=demo-pass-123  # benchmark with concise summary
make growth-report  # print 7d/30d growth funnel in terminal (requires running server)
```

## Growth Analytics

The app ships a lightweight growth analytics stack:

- Visitor tracking via durable cookie (`web_audience_id`) and `WebAudienceProfile` model
- `GrowthEvent` model records landing views, starter clicks, ask submits, share/copy clicks
- UTM attribution (`utm_source`, `utm_medium`, `utm_campaign`) captured as first/last touch
- `POST /api/analytics/events/` — frontend event ingest (public)
- `GET /api/analytics/summary/?days=N` — staff-only growth summary API
- Admin dashboard (`/admin/`) → `Ask events` shows 7-day funnel + UTM sources
- CLI: `python manage.py growth_report` for weekly/monthly terminal reports

## Environment Variables

```bash
cp .env.example .env
```

`OPENAI_API_KEY` is optional for local testing:
- when provided, `/api/ask/` uses OpenAI generation
- when empty, app falls back to deterministic local guidance

Quota variables:
- `ASK_LIMIT_FREE_DAILY` default `5`
- `ASK_LIMIT_PRO_DAILY` default `10000`
- `SUPPORT_EMAIL` support contact shown in chat UI (default:
  `support@askbhagavadgita.com`)

pgvector phase-1 variables (optional):
- `ENABLE_PGVECTOR_RETRIEVAL` default `false`
- `PGVECTOR_TABLE` default `guide_api_verse_embedding_index`
- `PGVECTOR_EMBEDDING_DIM` default `1536`
- `PGVECTOR_PROBES` default `10`

Production note:
- Do not commit `DATABASE_URL` or API keys.
- Set all secrets on Fly using `flyctl secrets set ...`.

### Fly Quick Ops

```bash
flyctl status -a askbhagavadgita
flyctl secrets list -a askbhagavadgita
flyctl deploy -a askbhagavadgita
flyctl ssh console -a askbhagavadgita -C "python manage.py migrate --noinput"
```

## API Endpoints

Versioning:
- stable base: `/api/`
- alias for mobile versioning: `/api/v1/` (same routes for now)

- `GET /api/health/`
- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/` (auth required)
- `GET /api/auth/me/` (auth required)
- `POST /api/auth/plan/` (auth required, local mock plan switch)
- `GET /api/engagement/me/` (auth required)
- `PATCH /api/engagement/me/` (auth required)
- `POST /api/ask/` (auth required)
- `POST /api/follow-ups/` (auth required)
- `POST /api/eval/retrieval/` (auth required; retrieval trace only, no generation)
- `POST /api/mantra/` (auth required)
- `GET /api/daily-verse/`
- `GET /api/chapters/` — list chapters (reader)
- `GET /api/chapters/<chapter_number>/` — chapter detail + verse list
- `GET /api/verses/<chapter>.<verse>/` — full verse + commentary
- `GET /api/quote-art/styles/`, `POST /api/quote-art/generate/`,
  `GET /api/quote-art/featured/` — same token rule as chapter browse (browser
  without token OK; token auth requires Plus or Pro)
- `GET /api/history/me/` (auth required)
- `GET /api/history/<user_id>/` (auth required, owner-only)
- `GET /api/feedback/` (auth required)
- `POST /api/feedback/` (auth required)
- `POST /api/support/` (guest/auth support request intake)
- `GET /api/saved-reflections/` (auth required)
- `POST /api/saved-reflections/` (auth required)
- `DELETE /api/saved-reflections/<reflection_id>/` (auth required)
- `GET/POST /api/chat-ui/` (manual browser testing page)
  - includes starter prompts, structured response sections, follow-up chips,
    recent question shortcuts, separate conversation threads, and a sidebar
    conversation list
  - includes progressive animation effects via `Animate.css`, `AOS`, `GSAP`,
    and `VanillaTilt` layered on top of existing live-chat behavior
- Admin analytics dashboard:
  - open `Ask events` in Django admin for asks/day, fallback rate, helpful
    rate, and quota block counters

Authentication:
- Uses Django/DRF authentication (session or basic auth).
- Also supports token auth via `Authorization: Token <token>`.
- Chapter/verse **browse** and **quote-art** JSON endpoints: same-origin web
  requests without an `Authorization` header are allowed (chat UI). Requests
  that authenticate with a **token** require **Plus or Pro**; **Free** token
  clients receive `403`. See `guide_api/permissions.py` —
  `GitaBrowseAPIPermission`.
- `ask`, `history`, and `feedback` endpoints are tied to authenticated user.
- `ask` and `follow-ups` accept `language` (`en` or `hi`) and default to
  `en` when omitted.
- `ask` applies plan quota checks and returns `429` when daily limit is reached.
- `auth/plan` and chat-ui plan switch controls are for local/debug testing only.
  Production upgrades should flow through payment verification.
- list endpoints support `limit` and `offset` query params for pagination.
- engagement profile powers mobile streak and reminder preferences.
- chat-ui supports separate threads and selecting older conversations by
  `conversation_id`
- LLM guidance uses recent conversation history only as supporting context
  and still answers the latest user message as the main query

Auth smoke flow (requires server running):

```bash
make auth-flow USERNAME=demo-user PASSWORD=demo-pass-123
make auth-flow-benchmark USERNAME=demo-user PASSWORD=demo-pass-123
make auth-flow-benchmark-summary USERNAME=demo-user PASSWORD=demo-pass-123
```

## Import Full Verse Dataset

Use the built-in management command to load all verses from JSON:

```bash
python manage.py import_gita --file data/gita_700.json
```

Dry-run validation without writing to DB:

```bash
python manage.py import_gita --file data/gita_700.json --dry-run
```

Strict mode (fail on first invalid row):

```bash
python manage.py import_gita --file data/gita_700.json --strict
```

Sample file format is available at:

`data/gita_import_sample.json`

### Kaggle CSV -> Import JSON

If your source is Kaggle `Bhagwad_Gita.csv`, convert first:

```bash
python scripts/convert_kaggle_gita_csv.py \
  --input data/Bhagwad_Gita.csv \
  --output data/gita_700.json
```

Then run the importer:

```bash
python manage.py import_gita --file data/gita_700.json --dry-run
python manage.py import_gita --file data/gita_700.json
```

### Kaggle Multi-Script CSV/XLSX Ingestion

If you downloaded the Kaggle multi-script bundle (CSV or XLSX), run:

```bash
python manage.py ingest_gita_multiscript \
  --input "/Users/deecoderr/Downloads/archive (1)/bhagavad-gita.xlsx"
```

What this does in one step:
- normalizes columns and deduplicates by `chapter.verse`
- merges data into `data/gita_additional_angles.json` (additive source cache)
- keeps existing canonical files untouched by default (`Bhagwad_Gita.csv`, `gita_700.json`)

If you explicitly want to refresh canonical files as well:

```bash
python manage.py ingest_gita_multiscript \
  --input "/Users/deecoderr/Downloads/archive (1)/bhagavad-gita.xlsx" \
  --update-canonical \
  --import-db \
  --overwrite
```

After import, auto-tag themes for better retrieval:

```bash
python manage.py tag_gita_themes --dry-run
python manage.py tag_gita_themes
```

Generate embeddings for semantic retrieval:

```bash
python manage.py embed_gita_verses
```

Optional flags:

```bash
python manage.py embed_gita_verses --limit 100
python manage.py embed_gita_verses --overwrite
python manage.py embed_gita_verses --batch-size 25
python manage.py embed_gita_verses --sync-pgvector
```

### PostgreSQL + pgvector (Phase 1, safe rollout)

Current app still works fully on SQLite. pgvector path is optional and only
activates when:
- database backend is PostgreSQL
- `ENABLE_PGVECTOR_RETRIEVAL=true`
- pgvector index table is set up and synced

Setup steps:

```bash
# 1) point app to PostgreSQL
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# 2) create extension + index table
python manage.py setup_pgvector_index

# 3) ensure Verse.embedding is populated
python manage.py embed_gita_verses --overwrite

# 4) sync embeddings to pgvector table
python manage.py sync_pgvector_embeddings

# 5) enable runtime pgvector retrieval
export ENABLE_PGVECTOR_RETRIEVAL=true
```

Run retrieval quality evaluation:

```bash
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode pipeline
python manage.py eval_retrieval --file data/retrieval_eval_cases_user_mix.json --mode pipeline
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode hybrid
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode semantic
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode pipeline --strict
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode hybrid --report-misses
python manage.py eval_retrieval --file data/retrieval_eval_cases_user_mix.json --mode pipeline --report-misses
```

### `POST /api/ask/` sample body

```json
{
  "message": "I feel anxious about my career growth.",
  "mode": "simple",
  "language": "en"
}
```

### `POST /api/auth/plan/` sample body

```json
{
  "plan": "pro"
}
```

### `POST /api/saved-reflections/` sample body

```json
{
  "conversation_id": 1,
  "message": "I feel anxious about my career growth.",
  "guidance": "Do your duty with sincerity and release outcome anxiety.",
  "meaning": "Focus on effort over result pressure.",
  "actions": ["Do one focused block of work", "Pause and breathe before stress"],
  "reflection": "What effort can I fully own today?",
  "verse_references": ["2.47", "3.19"],
  "note": "Useful for daily review"
}
```

### `POST /api/follow-ups/` sample body

```json
{
  "message": "I feel anxious about my career growth.",
  "mode": "simple",
  "language": "en"
}
```

### `POST /api/eval/retrieval/` benchmark sample body

```json
{
  "message": "I am anxious about career growth and performance.",
  "mode": "benchmark"
}
```

In `benchmark` mode, response includes side-by-side traces:
- `semantic`: semantic-only retrieval result
- `hybrid`: hybrid-only retrieval result

### Response shape

```json
{
  "conversation_id": 1,
  "guidance": "...",
  "verses": [
    {
      "reference": "2.47",
      "chapter": 2,
      "verse": 47,
      "translation": "...",
      "commentary": "...",
      "themes": ["career", "anxiety"]
    }
  ],
  "meaning": "...",
  "actions": ["...", "..."],
  "reflection": "...",
  "plan": "free",
  "daily_limit": 10,
  "used_today": 1,
  "remaining_today": 9,
  "engagement": {
    "daily_streak": 3,
    "last_active_date": "2026-04-04",
    "reminder_enabled": true,
    "reminder_time": "08:30:00",
    "timezone": "Asia/Kolkata",
    "preferred_channel": "push"
  },
  "response_mode": "llm",
  "retrieval_mode": "semantic",
  "retrieved_references": ["2.47", "3.19", "6.26"],
  "retrieval_scores": [{"reference": "2.47", "score": 0.82}],
  "query_themes": ["anxiety", "career"]
}
```

`retrieval_mode` may also be `curated_fallback` when deterministic
confidence checks detect weak initial verse relevance.

Error shape (non-breaking, additive):

```json
{
  "error": {
    "code": "quota_exceeded",
    "message": "Daily ask limit reached for your plan. Please upgrade to Pro or try again tomorrow."
  },
  "detail": "Daily ask limit reached for your plan. Please upgrade to Pro or try again tomorrow."
}
```

## Current Scope

- Starter models for `Verse`, `Conversation`, and `Message`
- Seed verses auto-loaded on first retrieval
- Basic theme matching + deterministic verse retrieval
- Risky prompt blocking for crisis/unsafe requests
- OpenAI-based response generation with fallback mode
- Verse-grounding validation against retrieved references
- UX pass v1 on `chat-ui`:
  - sidebar `Today` card for daily spiritual framing
  - starter prompt onboarding
  - latest structured answer rendered inside the conversation thread
  - primary in-chat composer for direct back-and-forth messaging
  - in-place chat updates and thinking animation while waiting for reply
  - structured rendering (guidance/meaning/actions/reflection/verses)
  - follow-up prompt chips and recent-question shortcuts
  - progressive typing effect for the newest assistant reply
- Threaded conversation pass on `chat-ui`:
  - logged-out chat stays session-temporary and is not tagged to any user
  - signed-in users only see and manage their own saved threads
  - one sidebar mode selector controls the next message across all threads
  - separate conversation threads with sidebar selection
  - `Start New Conversation` resets the active visible thread
  - sidebar cards show message counts and last-updated timestamps
  - threads can be deleted directly from the sidebar
  - recent thread history is sent to the LLM as supporting context for the
    latest user message
- Ask analytics event tracking + admin dashboard counters.
- Saved reflections/bookmarks API (mobile-ready CRUD surface).
- Contextual follow-up prompts API and analytics events.
- Engagement profile API with streak and reminder preferences.

## Next Build Steps

1. Replace keyword retrieval with pgvector semantic retrieval.
2. Add retrieval eval dataset + scoring command for quality tracking.
3. Add streak/reminder signals for daily return behavior.
4. Add Stripe checkout and paid plan lifecycle hooks.
