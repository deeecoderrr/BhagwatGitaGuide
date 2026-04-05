# Bhagwat Gita Guide API

DRF backend starter for a Gita-based life guidance app.

See `PROGRESS.md` for live build status and next milestones.

## Documentation

- User documentation: `docs/USER_GUIDE.md`
- Developer documentation: `docs/DEVELOPER_GUIDE.md`
- AI / coding-agent handoff: `AGENTS.md` (start here) and `docs/AI_AGENT_HANDOFF.md`

## Stack

- Django + Django REST Framework
- SQLite for local development
- Python 3.14

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
make import-gita FILE=data/gita_700.json  # import full verse dataset
make tag-gita-themes  # auto-tag themes using verse text
make embed-gita-verses  # generate OpenAI embeddings for semantic retrieval
make eval-retrieval  # run retrieval eval on labeled prompts
make auth-flow USERNAME=demo-user PASSWORD=demo-pass-123  # auth + ask + history smoke flow
make auth-flow-benchmark USERNAME=demo-user PASSWORD=demo-pass-123  # auth + retrieval benchmark + ask
make auth-flow-benchmark-summary USERNAME=demo-user PASSWORD=demo-pass-123  # benchmark with concise summary
```

## Environment Variables

```bash
cp .env.example .env
```

`OPENAI_API_KEY` is optional for local testing:
- when provided, `/api/ask/` uses OpenAI generation
- when empty, app falls back to deterministic local guidance

Quota variables:
- `ASK_LIMIT_FREE_DAILY` default `10`
- `ASK_LIMIT_PRO_DAILY` default `1000`

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
- `POST /api/eval/retrieval/` (retrieval trace only, no generation)
- `GET /api/daily-verse/`
- `GET /api/history/me/` (auth required)
- `GET /api/history/<user_id>/` (auth required, owner-only)
- `GET /api/feedback/` (auth required)
- `POST /api/feedback/` (auth required)
- `GET /api/saved-reflections/` (auth required)
- `POST /api/saved-reflections/` (auth required)
- `DELETE /api/saved-reflections/<reflection_id>/` (auth required)
- `GET/POST /api/chat-ui/` (manual browser testing page)
  - includes starter prompts, structured response sections, follow-up chips,
    recent question shortcuts, separate conversation threads, and a sidebar
    conversation list
- Admin analytics dashboard:
  - open `Ask events` in Django admin for asks/day, fallback rate, helpful
    rate, and quota block counters

Authentication:
- Uses Django/DRF authentication (session or basic auth).
- Also supports token auth via `Authorization: Token <token>`.
- `ask`, `history`, and `feedback` endpoints are tied to authenticated user.
- `ask` applies plan quota checks and returns `429` when daily limit is reached.
- `auth/plan` lets you switch `free`/`pro` for local quota testing.
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
```

Run retrieval quality evaluation:

```bash
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode pipeline
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode hybrid
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode semantic
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode pipeline --strict
python manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode hybrid --report-misses
```

### `POST /api/ask/` sample body

```json
{
  "message": "I feel anxious about my career growth.",
  "mode": "simple"
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
  "mode": "simple"
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
