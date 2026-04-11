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
- **Production:** Fly.io app (`askbhagavadgita`) + Neon PostgreSQL via `DATABASE_URL`.
- **Main code:** `guide_api/views.py`, `guide_api/services.py`, `guide_api/models.py`, `guide_api/tests.py`.

## Frontend Redesign Protocol

When the user asks for UI, UX, design, theme, animation, layout, colors,
imagery, or visual polish, follow this workflow before editing:

1. Inspect the codebase and the current UI implementation to infer:
   - app purpose
   - target user mindset
   - main workflows
   - emotional tone the product should create
2. Summarize the inferred product identity in 3-5 concise bullets.
3. Choose a fitting visual direction before making changes.
4. Implement the redesign directly in code, preserving functionality.
5. Refactor repeated styling into reusable tokens, shared classes, and
   maintainable patterns where possible.
6. Verify responsive behavior and run tests after non-trivial changes.

### Purpose-specific rule for this repository

This product is not a generic assistant UI. It is a Bhagavad Gita guidance
experience where the seeker asks for life guidance in the spirit of Arjuna
receiving wisdom from Krishna. The interface should therefore feel:

- calm
- sacred
- luminous
- reassuring
- premium
- spiritually immersive

Avoid making it feel like:

- a generic SaaS dashboard
- a crypto/trading app
- a gaming UI
- an over-decorated fantasy site
- a loud neon AI demo

### Visual direction constraints

- Prefer warm celestial or serene devotional palettes over harsh corporate
  colors.
- Motion should feel meaningful and graceful, not noisy.
- Typography should feel intentional and reverent, while remaining highly
  readable.
- Imagery, gradients, glows, and symbols should support the Bhagavad Gita /
  Krishna-Arjuna theme without making the UI kitschy.
- Preserve accessibility, clarity, and mobile responsiveness.
- Preserve existing backend and interaction behavior unless the task explicitly
  asks for UX flow changes.

### Expected redesign output

For substantial frontend passes, include in the final summary:

- inferred app purpose
- chosen theme direction
- main UX issues fixed
- design-system or token changes made
- files changed

### Design reference

See `docs/design-playbook.md` before major frontend redesign work.

If instructions conflict, **`PROGRESS.md` + `docs/AI_AGENT_HANDOFF.md`** win for current scope.
