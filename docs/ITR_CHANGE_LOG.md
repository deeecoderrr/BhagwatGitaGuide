# ITR integration & related changes — tracking for revert / audit

Use this file to remember **what touched the repo** beyond pure “Gita-only” paths. When you need to undo work, combine **Git history** (`git log`, `git diff`) with the sections below.

---

## Kill switch (no code revert)

- **`ITR_ENABLED=false`** — Disables allauth, all `apps.*` ITR URLs, and ITR settings injection. Deploy looks like Bhagavad Gita only (still same `requirements.txt`; dependencies stay installed unless you trim them).

---

## Core Django wiring (Bhagwat Gita process)

| Area | Files | Notes |
|------|--------|--------|
| Settings entry | `config/settings.py` | Calls `_configure_optional_itr()` → `config/settings_itr.register_itr_settings`. |
| ITR settings bundle | `config/settings_itr.py` | Apps, backends, middleware, templates dir, media, Razorpay/RQ, **`ITR_OUTPUT_RETENTION_HOURS`**, **`ITR_DELETE_INPUT_AFTER_EXPORT`**, **`TEMPLATES`** context processors (**`apps.accounts`** `google_oauth`, `account_profile`), **`GOOGLE_OAUTH_CONFIGURED`**. |
| Root URLs | `config/urls.py` | Conditional `accounts/` + `{ITR_URL_PREFIX}/` when `ITR_ENABLED`. Debug media serve for ITR. |
| ITR URL include | `config/urls_itr.py` | Billing, documents, exports, reviews, comments, marketing. |

---

## OAuth templates & production WeasyPrint (2026-04)

| Area | Files | Notes |
|------|--------|--------|
| OAuth UX | `templates/account/login.html`, `templates/account/signup.html`, `templates/marketing/home.html`, `templates/marketing/pricing.html` | **Continue with Google** when **`google_oauth_configured`**; **`next`** preserves return to workspace or checkout. |
| Fly / Docker runtime | `Dockerfile` | Installs **Pango, cairo, GLib/GDK-Pixbuf, shared-mime-info**, fonts so **WeasyPrint** loads (**`libgobject`** et al.). |
| Ops | `docs/PRODUCTION_RUNBOOK.md` | Troubleshooting when WeasyPrint fails with missing shared libraries. |

---

## Shared `guide_api` (same deploy as Gita)

| File | Change |
|------|--------|
| `guide_api/views.py` | **`_session_auth_login()`** — passes `backend=` only when multiple `AUTHENTICATION_BACKENDS`; used for Google login + chat-ui register/login. |
| `guide_api/middleware.py` | **`CanonicalHostRedirectMiddleware`** — redirects **`*.onrender.com`** like **`*.fly.dev`** to `CANONICAL_HOST` (prod). |

Revert impact: removing `_session_auth_login` breaks chat-ui login when allauth + ModelBackend both active. Removing onrender redirect changes canonical behavior for Render default hostnames.

---

## ITR Python apps & data

| Area | Location |
|------|-----------|
| Apps | `apps/` (`accounts`, `analytics`, `billing`, `comments`, `core`, `documents`, `exports`, `extractors`, `marketing`, `reviews`) |
| Schemas | `schemas/` (if present) |
| Static | `static_itr/` |
| Media uploads | `media/` (runtime; gitignore-style—do not rely on repo) |

---

## Export retention & upload lifecycle

| File | Purpose |
|------|---------|
| `apps/exports/models.py` | **`expires_at`**, **`pdf_purged_at`**; **`pdf_file`** blankable after purge. |
| `apps/exports/migrations/0002_exportedsummary_retention.py` | DB migration. |
| `apps/exports/retention.py` | **`purge_expired_exports`**, **`delete_document_upload_after_export`**. |
| `apps/exports/views.py` | Sets **`expires_at`** on create; **`delete_document_upload_after_export`** after PDF; **`can_download`** on download; calls purge on views. |
| `apps/documents/models.py` | **`uploaded_file`** nullable after input delete. |
| `apps/documents/migrations/0010_document_upload_optional.py` | DB migration. |
| `apps/documents/views.py` | **`purge_expired_exports`** on list; prefetch exports; **`document_reprocess`** blocked if upload missing. |
| `apps/exports/management/commands/purge_itr_retention.py` | Cron-friendly purge command. |
| `apps/exports/templatetags/itr_export.py` | **`{% itr_output_retention_hours %}`** for docs text. |

---

## Templates (ITR-facing)

| Files | Purpose |
|-------|---------|
| `templates/base.html`, `templates/marketing/*.html`, `templates/documents/*.html`, `templates/exports/export_confirm.html`, … | Layout, retention copy, workspace list/detail. |

---

## Dependencies

| File | Addition |
|------|-----------|
| `requirements.txt` | `django-allauth`, `django-rq`, `redis`, `reportlab`, `weasyprint`, `PyJWT`, pins as added. |

---

## Documentation & env templates

Updated for ITR / retention / ops:

- `README.md`
- `PROGRESS.md`
- `AGENTS.md`
- `.env.example`
- `docs/AI_AGENT_HANDOFF.md`
- `docs/DEVELOPER_GUIDE.md`
- `docs/USER_GUIDE.md`
- `docs/PRODUCTION_RUNBOOK.md`

---

## How to revert (practical order)

1. **Disable ITR only:** set **`ITR_ENABLED=false`** and redeploy — fastest, keeps files in tree unused.
2. **Git selective revert:** identify commits that introduced ITR (`git log --oneline -- config/ apps/ templates/`), then **`git revert <commit>`** or restore paths from **`main`** before merge: **`git checkout <revision> -- path`**
3. **Remove ITR trees:** delete or move aside **`apps/`**, **`templates/`** ITR-specific, **`static_itr/`**, **`config/urls_itr.py`**, **`config/settings_itr.py`**, strip **`guide_api`** edits and **`config/settings.py`** / **`config/urls.py`** / **`requirements.txt`** manually — error-prone; prefer (1) or Git revert.
4. **Database:** reversing migrations (`documents`, `exports`, `account`, …) requires **`python manage.py migrate apps zero`** style steps only if you truly remove ITR tables from this database **— backup first.**

---

## Tests

Retention tests: **`apps/exports/tests/test_retention.py`**. Full gate: **`make test`**.

---

*Maintainer: bump this doc when adding or removing ITR-related behavior.*
