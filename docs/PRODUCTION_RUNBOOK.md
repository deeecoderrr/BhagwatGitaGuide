# Production Runbook

This file contains the commands used for production operations on Fly.

App name
- askbhagavadgita

Prerequisites
1. Install Fly CLI and login
   flyctl auth login
2. Be in the project root
   cd /Users/deecoderr/Work/Personal/Projects/BhagwatGitaGuide

Daily operational flow
1. Check app status
   flyctl status -a askbhagavadgita

2. Check current secrets
   flyctl secrets list -a askbhagavadgita

3. Deploy latest code
   flyctl deploy -a askbhagavadgita

4. Run migrations on production
   flyctl ssh console -a askbhagavadgita -C "python manage.py migrate --noinput"

5. Verify migrations for guide_api
   flyctl ssh console -a askbhagavadgita -C "python manage.py showmigrations guide_api"

6. Quick health check
   curl -s https://askbhagavadgita.fly.dev/api/health/

Support and payment config
1. Set support email
   flyctl secrets set SUPPORT_EMAIL="askbhagwatgitasupport@gmail.com" -a askbhagavadgita

2. Set Razorpay keys
   flyctl secrets set RAZORPAY_KEY_ID="your_key_id" -a askbhagavadgita
   flyctl secrets set RAZORPAY_KEY_SECRET="your_key_secret" -a askbhagavadgita
   flyctl secrets set RAZORPAY_WEBHOOK_SECRET="your_webhook_secret" -a askbhagavadgita

   Webhook behavior: **`payment.captured`** for tagged **practice workflow** and **sadhana**
   orders only completes enrollment when the capture **amount/currency** match the
   catalog price and the existing **`BillingRecord`** row. Skips are logged at **INFO**
   (`razorpay_webhook_skip_practice_workflow_capture`, `razorpay_webhook_skip_sadhana_capture`);
   ensure production log level or sinks include **`guide_api`** INFO if you rely on these
   for support. See **`PAYMENT_INTEGRATION_ANALYSIS.md`**.

3. Set pricing values
   flyctl secrets set SUBSCRIPTION_PRICE_PLUS_INR="4900" -a askbhagavadgita
   flyctl secrets set SUBSCRIPTION_PRICE_PLUS_USD="149" -a askbhagavadgita
   flyctl secrets set SUBSCRIPTION_PRICE_PRO_INR="9900" -a askbhagavadgita
   flyctl secrets set SUBSCRIPTION_PRICE_PRO_USD="299" -a askbhagavadgita

Admin access operations
1. Create or reset production admin user
   flyctl ssh console -a askbhagavadgita -C "python manage.py shell -c \"from django.contrib.auth import get_user_model; User=get_user_model(); u,created=User.objects.get_or_create(username='admin',defaults={'email':'askbhagwatgitasupport@gmail.com','is_staff':True,'is_superuser':True}); u.email='askbhagwatgitasupport@gmail.com'; u.is_staff=True; u.is_superuser=True; u.set_password('Admin@Bhagwat2026!'); u.save(); print('CREATED' if created else 'EXISTS'); print('PROD_ADMIN_READY')\""

2. Open admin page
   https://askbhagavadgita.fly.dev/admin/

Troubleshooting commands
1. Check if support ticket migration is applied
   flyctl ssh console -a askbhagavadgita -C "python manage.py showmigrations guide_api"

2. Confirm verse count in production DB
   flyctl ssh console -a askbhagavadgita -C "python manage.py shell -c \"from guide_api.models import Verse; print(Verse.objects.count())\""

3. Verify SupportTicket rows
   flyctl ssh console -a askbhagavadgita -C "python manage.py shell -c \"from guide_api.models import SupportTicket; print(SupportTicket.objects.count())\""

Safe release checklist
1. Run local tests first
   source .venv/bin/activate && python manage.py test
2. Deploy
3. Run migrate
4. Check health endpoint
5. Verify admin login
6. Verify support form submission appears in admin

ITR Summary Generator (if enabled in production)
- Set `ITR_ENABLED=true` and `ITR_URL_PREFIX` (e.g. `/itr-computation`) if the ITR
  app is shipped. Gita-only: `ITR_ENABLED=false`.
- **Public beta try (anonymous upload + review on marketing home):** set
  `ITR_BETA_RELEASE=true` (or `false` to hide the strip in production). Example:
  `flyctl secrets set ITR_BETA_RELEASE=true -a askbhagavadgita`
- Retention: set `ITR_OUTPUT_RETENTION_HOURS` (default 24) and optional
  `ITR_DELETE_INPUT_AFTER_EXPORT`. Schedule periodic storage cleanup, e.g. hourly:
  `python manage.py purge_itr_retention`
- Configure a **separate** Razorpay webhook URL for ITR billing if used, or set
  `ITR_RAZORPAY_WEBHOOK_SECRET` as needed. Gita subscription webhooks stay on
  `/api/payments/webhook/`.
- After deploy, apply ITR migrations: `showmigrations documents exports` and
  `migrate` as usual.
- **Lifetime ITR funnel stats** (exports anonymous vs logged-in, documents,
  marketing `GrowthEvent` counts — see command help for caveats). From your laptop
  (requires `flyctl auth login`). One-shot:

  ```
  flyctl ssh console -a askbhagavadgita -C "python manage.py itr_computation_stats"
  ```

  If the SSH session starts outside the app directory, run:

  ```
  flyctl ssh console -a askbhagavadgita \
    -C "cd /code && python manage.py itr_computation_stats"
  ```

  Interactive shell: `flyctl ssh console -a askbhagavadgita`, then
  `cd /code` if needed, then `python manage.py itr_computation_stats`.
  Deploy code that contains the command before relying on this in production.
- **WeasyPrint (CA-layout PDF):** the Fly image must install Pango, cairo, and
  GLib/GObject packages; these are listed in the repo `Dockerfile`. If production
  shows `libgobject-2.0-0` / shared library errors, redeploy after pulling the
  latest Dockerfile (do not rely on `pip install weasyprint` alone).
- **ITR “Continue with Google”:** requires **both** an OAuth client id and **client
  secret** (django-allauth). `GOOGLE_OAUTH_CLIENT_ID` alone (chat-ui GIS) is not
  enough. Set `GOOGLE_CLIENT_SECRET` or `GOOGLE_OAUTH_CLIENT_SECRET` on Fly, and add
  authorized redirect URI `https://<your-domain>/accounts/google/login/callback/`.

Notes
- Do not commit secrets to git.
- After changing any Fly secret, Fly performs rolling updates automatically.
- Change default admin password immediately after first login.
