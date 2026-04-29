"""Send scheduled weekly digest emails to active users."""

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from guide_api.models import Verse

User = get_user_model()


class Command(BaseCommand):
    help = "Send a weekly summary email of popular verses and reflections."

    def handle(self, *args, **options):
        verse = Verse.objects.order_by("?").first()
        if not verse:
            self.stdout.write("No verses found.")
            return

        subject = f"Your Weekly Bhagavad Gita Digest: Chapter {verse.chapter}, Verse {verse.verse}"
        body = (
            f"Here is a verse to guide you this week:\n\n"
            f"Sanskrit:\n{verse.sanskrit}\n\n"
            f"Translation:\n{verse.translation}\n\n"
            f"Commentary:\n{verse.commentary}\n\n"
            f"May this wisdom bring you peace."
        )

        users = User.objects.filter(is_active=True).exclude(email="")
        sent = 0
        for user in users:
            try:
                send_mail(
                    subject,
                    body,
                    getattr(settings, "DEFAULT_FROM_EMAIL", "askbhagwatgitasupport@gmail.com"),
                    [user.email],
                    fail_silently=True,
                )
                sent += 1
            except Exception:
                pass

        self.stdout.write(f"Weekly digest sent to {sent} users.")
