# BhagwatGitaGuide — handoff for AI coding agents

**Purpose:** Upload or paste this file when starting or resuming work in GitHub Copilot Chat, Codex, Cursor, or similar tools. It summarizes architecture, conventions, and current scope so you do not need full repo exploration to be productive.

**Project:** Django + DRF backend for a Bhagavad Gita–based life guidance app (RAG + OpenAI generation, safety guardrails, auth, quota, mobile-friendly JSON APIs).

**Repo root:** `BhagwatGitaGuide/` (Django project `config/`, app `guide_api/`).

---

## Stack

- Python 3.14, Django, Django REST Framework
- SQLite locally (`db.sqlite3`)
- OpenAI: chat (`OPENAI_MODEL`, default `gpt-4.1-mini`), embeddings (`OPENAI_EMBEDDING_MODEL`, default `text-embedding-3-small`)
- Auth: session + basic + `Authorization: Token <token>` (DRF authtoken)

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
| HTTP / API surface | `guide_api/views.py`, `guide_api/urls.py` |
| Retrieval + LLM + safety | `guide_api/services.py` |
| Serializers / validation | `guide_api/serializers.py` |
| Models | `guide_api/models.py` |
| Admin + analytics summaries | `guide_api/admin.py`, `guide_api/templates/admin/guide_api/askevent/change_list.html` |
| Manual web UI | `guide_api/templates/guide_api/chat_ui.html` |
| Project URLs (includes `/api/v1/` alias) | `config/urls.py` |
| Settings / env | `config/settings.py`, `.env.example` |
| Verse data / eval | `data/gita_700.json`, `data/Bhagwad_Gita.csv`, `data/gita_additional_angles.json`, `data/retrieval_eval_cases.json` |
| Management commands | `guide_api/management/commands/` (`ingest_gita_multiscript`, `import_gita`, `tag_gita_themes`, `embed_gita_verses`, `setup_pgvector_index`, `sync_pgvector_embeddings`, `eval_retrieval`, …) |
| Tests | `guide_api/tests.py` |

Long procedures are documented in `docs/DEVELOPER_GUIDE.md`; user-facing behavior in `docs/USER_GUIDE.md`. Build status and roadmap: `PROGRESS.md`, `README.md`.

---

## API contract (high level)

- **Prefixes:** `/api/...` and **`/api/v1/...`** are equivalent (mobile versioning alias).
- **Errors:** Standardized envelope with `error.code`, `error.message`, and `detail` where applicable.
- **List endpoints:** Support `?limit=&offset=` where documented (e.g. feedback, saved-reflections).
- **Quota:** `POST /api/ask/` enforces daily limits (`ASK_LIMIT_FREE_DAILY`, `ASK_LIMIT_PRO_DAILY`); may return `429`. Plan mock: `POST /api/auth/plan/`.
- **Language:** `POST /api/ask/` and `POST /api/follow-ups/` accept
  `language=en|hi` (defaults to `en`).

**Important routes** (under both `/api/` and `/api/v1/`):

- `GET health/`
- `POST auth/register/`, `auth/login/`, `auth/logout/`, `GET auth/me/`, `POST auth/plan/`
- `GET|PATCH engagement/me/` — streak, reminder prefs (delivery not implemented yet)
- `POST ask/` — main Q&A (structured JSON: guidance, meaning, actions, reflection, verse_references, follow_ups, engagement snapshot, quota fields)
- `POST follow-ups/` — contextual follow-up prompts
- `POST mantra/` — verse as mantra for mood (calm/focus/courage/peace/strength/clarity)
- `GET chapters/` — list all 18 chapters with metadata for browsing
- `GET chapters/<chapter_number>/` — chapter detail with verse list
- `GET verses/<chapter>.<verse>/` — full verse detail with multi-author commentary
- `GET|POST feedback/`
- `GET|POST saved-reflections/`, `DELETE saved-reflections/<id>/`
- `GET daily-verse/`, history under `history/me/`, `history/<user_id>/` (owner)
- `POST eval/retrieval/` — retrieval trace / benchmark (no generation)
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
- **Retrieval:** Hybrid + semantic path; tuning via `eval_retrieval` and `data/retrieval_eval_cases.json`.
- **Style:** Match existing code; keep lines PEP8-friendly (~79 chars) where the repo already does; run `make test` after non-trivial edits.

---

## Security

- Never commit real API keys or production `SECRET_KEY`. Use `.env` locally; `.env.example` documents variables only.

---

## Current status (snapshot)

**Implemented:** Auth + token, ask with quota, structured responses, follow-ups, saved reflections, engagement/streak/reminder **preferences** (storage only), chat-ui UX with guest-temporary chat plus account-owned conversation threads/sidebar metadata/delete controls, admin ask analytics, retrieval eval pipeline, `/api/v1/` alias, standardized errors, pagination on relevant lists, and bilingual guidance selection (`en`/`hi`) across API + chat-ui.

**Explicitly not done / next waves:** Push or email **delivery** for reminders, **scheduled** reminder worker, **Stripe** and production billing, possible **pgvector** migration for retrieval at scale (SQLite + embeddings in DB today).

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

*Last aligned with repo state: 2026-04-05. Regenerate or edit this file when major architecture or endpoints change.*
