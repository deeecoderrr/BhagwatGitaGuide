# User Guide

## What This App Does

Bhagwat Gita Guide helps you reflect on day-to-day problems using
Bhagavad Gita verses. You can ask a question, get guided suggestions,
and give feedback on whether the answer was useful.

## Who This Guide Is For

- End users trying the app in browser/API
- QA testers validating user-facing behavior

## Quick Start (Browser)

1. Open one of these:
  - local: `http://127.0.0.1:8000/api/chat-ui/`
  - live: `https://askbhagavadgita.fly.dev/api/chat-ui`
2. If you are logged out, chat in guest mode:
   - choose `mode` (`simple` or `deep`)
   - choose `language` (`English` or `Hindi`)
   - enter your message
   - guest chat stays temporary in the current browser session only
3. If you want saved history, register or log in first.
4. Optional: click any starter prompt chip to begin quickly.
5. Submit and review:
   - guidance
   - meaning
   - actions
   - reflection
   - verses used
   - continue directly from the in-chat message box above the transcript
6. Optional: continue with follow-up chips or recent-question chips.
7. When logged in, mark answer as `Helpful` or `Not Helpful`.
8. When logged in, use the `Conversations` sidebar to reopen an older thread, or click
   `Start New Conversation` to begin a separate thread.
9. Each saved thread card shows message count and last-updated time. Use
   `Delete` on a card to remove that conversation.
10. The sidebar `Mode` and `Language` selectors are global for the whole chat
    UI. Whatever you select there will be used for the next message in any
    conversation.
11. The chat UI uses smooth animations and transitions; if a CDN is blocked,
    core chat functionality still works without the visual effects.

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
  "mode": "simple",
  "language": "en"
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

### Chat UI account modes

On `GET /api/chat-ui/`:
- logged-out users get a temporary guest chat that is not saved to any user
- logged-in users get saved conversation history scoped to their own account
- only logged-in users can use the plan selector, feedback form, saved
  reflections, and conversation sidebar/history

`chat-ui` also includes:
- a `Today` card in the sidebar for a daily spiritual framing moment
- starter prompts for first-time users
- follow-up prompt chips after each response
- a primary in-chat composer above the transcript for direct back-and-forth
- asking from chat now updates the conversation in place without a full page reload
- a thinking animation appears in the thread while waiting for the reply
- sending a message keeps the page focused on the active conversation panel
- the assistant's structured reply rendered inside the conversation itself
- newest assistant replies animate into the chat with a typing effect
- recent question shortcuts (up to 3)
- a sidebar list of recent conversations for the signed-in user
- one global sidebar mode selector shared across all conversations
- one global sidebar language selector shared across all conversations
- per-thread message counts and updated timestamps in the sidebar
- thread deletion directly from the sidebar
- `Start New Conversation` for beginning a separate thread

When the app uses the LLM path, the latest message is treated as the main
question. Recent thread history is used only as supporting context so the
reply stays relevant to the current message while still feeling continuous.

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

### Contact support

If you need help with payments, account access, or app issues:

1. Open chat UI and expand `Support` in the sidebar.
2. Fill name, email, issue type, and message.
3. Submit `Send Support Request`.

You can also call API directly:

- `POST /api/support/`

```json
{
  "name": "Seeker Name",
  "email": "you@example.com",
  "issue_type": "payment",
  "message": "My payment succeeded but Pro is not active yet."
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

`follow-ups` accepts the same language selector:
- `language = en` (English)
- `language = hi` (Hindi)

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

- Live app feels slow on first request:
  - in free hosting mode, the app machine may cold-start after idling
  - first request can be slower; subsequent requests are usually faster
- Live app shows redirect loop on `/api/*`:
  - ask a developer to verify proxy HTTPS settings in production
    (`SECURE_PROXY_SSL_HEADER`)
- Empty/less relevant answers:
  - run theme tagging and embeddings (developer task)
  - refresh dataset from latest Kaggle multi-script file:
    `python manage.py ingest_gita_multiscript --input /path/bhagavad-gita.xlsx`
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

## Live App URL

- current production URL: `https://askbhagavadgita.fly.dev/`
