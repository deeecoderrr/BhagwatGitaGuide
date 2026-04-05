# User Guide

## What This App Does

Bhagwat Gita Guide helps you reflect on day-to-day problems using
Bhagavad Gita verses. You can ask a question, get guided suggestions,
and give feedback on whether the answer was useful.

## Who This Guide Is For

- End users trying the app in browser/API
- QA testers validating user-facing behavior

## Quick Start (Browser)

1. Open the app at `http://127.0.0.1:8000/api/chat-ui/`.
2. Enter:
   - `user_id` (any short identifier, for example `demo-user`)
   - `mode` (`simple` or `deep`)
   - your message
3. Optional: click any starter prompt chip to begin quickly.
4. Submit and review:
   - guidance
   - meaning
   - actions
   - reflection
   - verses used
5. Optional: continue with follow-up chips or recent-question chips.
6. Mark answer as `Helpful` or `Not Helpful`.

## Quick Start (API)

For API usage, sign in first (session auth) or call endpoints with
basic auth credentials.

You can call either:
- `/api/...`
- `/api/v1/...` (mobile-friendly version alias)

### Register / login

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `GET /api/auth/me/`
- `POST /api/auth/plan/` (switch between `free` and `pro` for local testing)

Login response includes token:

```json
{
  "token": "your-token-value",
  "username": "demo-user"
}
```

Use token in header for protected endpoints:

`Authorization: Token your-token-value`

`GET /api/auth/me/` also returns plan usage info:
- `plan` (`free` or `pro`)
- `daily_limit`
- `used_today`
- `remaining_today`

### Fast QA with Makefile

If the local server is running, execute full auth+chat smoke flow:

```bash
make auth-flow USERNAME=demo-user PASSWORD=demo-pass-123
make auth-flow-benchmark USERNAME=demo-user PASSWORD=demo-pass-123
make auth-flow-benchmark-summary USERNAME=demo-user PASSWORD=demo-pass-123
```

### Health check

- `GET /api/health/`

### Ask for guidance

- `POST /api/ask/`

```json
{
  "message": "I am anxious about my career growth.",
  "mode": "simple"
}
```

Ask responses now include quota fields (`plan`, `daily_limit`,
`used_today`, `remaining_today`).

If your plan limit is reached, `/api/ask/` returns `429` with an
upgrade/try-tomorrow message.

To test a plan change quickly:

```json
POST /api/auth/plan/
{
  "plan": "pro"
}
```

### Chat UI quota test

On `GET /api/chat-ui/`, you can use the plan selector to toggle `free`
or `pro` for an existing username and validate the quota behavior.

`chat-ui` also includes:
- starter prompts for first-time users
- follow-up prompt chips after each response
- recent question shortcuts (up to 3)

For product analytics review (developer/admin use), see Django Admin
`Ask events` for asks/day, fallback rate, helpful rate, and quota blocks.

### View latest history

- `GET /api/history/me/`

### Send feedback

- `POST /api/feedback/`

```json
{
  "message": "This helped me think clearly.",
  "mode": "simple",
  "response_mode": "llm",
  "helpful": true,
  "note": "Very practical"
}
```

### Save reflections/bookmarks

- `POST /api/saved-reflections/`
- `GET /api/saved-reflections/`
- `DELETE /api/saved-reflections/<id>/`

Use this to save helpful guidance and revisit it later from web, Android,
or iOS using the same API contract.

List endpoints (`feedback`, `saved-reflections`) support pagination:
- `?limit=<n>&offset=<n>`

### Generate contextual follow-ups

- `POST /api/follow-ups/`

Use this when Android/iOS needs fresh next-step prompts independent of
the immediate `ask` call.

### Engagement profile (streak + reminders)

- `GET /api/engagement/me/`
- `PATCH /api/engagement/me/`

Use this to read/update:
- daily streak state
- reminder enabled/time
- timezone
- preferred channel (`push`, `email`, `none`)

## Understanding Response Modes

- `response_mode = llm`: answer came from LLM generation
- `response_mode = fallback`: deterministic local fallback was used

## Safety Behavior

The app blocks risky prompts (for crisis/self-harm, medical, legal
decision-making). In those cases, it returns a refusal and asks users
to seek professional or emergency support.

## Troubleshooting

- Empty/less relevant answers:
  - run theme tagging and embeddings (developer task)
  - use `deep` mode for slightly broader retrieval
- Seeing fallback often:
  - check `OPENAI_API_KEY`
  - check account quota/billing
- Need citation/debug detail:
  - ask a developer to enable `DEBUG=true` in local environment
- `make auth-flow*` seems stuck:
  - ensure server is running in foreground (`make run`)
  - if previously suspended, run `fg` then `Ctrl+C`, and restart server
  - run `make migrate` once after auth/token updates
- `register` returns `{"detail":"Username is already taken."}`:
  - expected for existing users; login still works
