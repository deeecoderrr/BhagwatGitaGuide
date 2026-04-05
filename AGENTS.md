# Agent instructions — BhagwatGitaGuide

Any AI assistant working in this repository should treat the following as **mandatory context** (read before large edits):

1. **`docs/AI_AGENT_HANDOFF.md`** — Architecture, file map, API surface, conventions, security, roadmap snapshot.
2. **`PROGRESS.md`** — What is done, what is next, deferred items; update when you finish a milestone.
3. **`docs/DEVELOPER_GUIDE.md`** — Deeper technical detail when changing behavior or adding endpoints.
4. **`docs/USER_GUIDE.md`** — End-user behavior when UX or API responses change.

## Non-negotiables

- Run **`make test`** (or `python manage.py test`) after non-trivial changes.
- Prefer **additive** API changes for mobile clients; keep `/api` and `/api/v1/` in sync.
- Do **not** commit secrets; use `.env` (see `.env.example`).
- Match existing style (PEP8-friendly line length as in the rest of the repo).

## Quick facts

- **Stack:** Django + DRF, SQLite locally, OpenAI for generation/embeddings (optional fallback without key).
- **Main code:** `guide_api/views.py`, `guide_api/services.py`, `guide_api/models.py`, `guide_api/tests.py`.

If instructions conflict, **`PROGRESS.md` + `docs/AI_AGENT_HANDOFF.md`** win for current scope.
