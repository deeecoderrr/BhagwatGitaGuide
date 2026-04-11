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

3. Set pricing values
   flyctl secrets set SUBSCRIPTION_PRICE_INR="9900" -a askbhagavadgita
   flyctl secrets set SUBSCRIPTION_PRICE_USD="299" -a askbhagavadgita

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

Notes
- Do not commit secrets to git.
- After changing any Fly secret, Fly performs rolling updates automatically.
- Change default admin password immediately after first login.
