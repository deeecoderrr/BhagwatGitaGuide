"""Print weekly/monthly growth snapshot for audience and ask metrics."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from guide_api.models import AskEvent, GrowthEvent, WebAudienceProfile


class Command(BaseCommand):
    """Report growth metrics for quick operator visibility."""

    help = "Print growth summary for 7-day and 30-day windows."

    def handle(self, *args, **options):
        """Compute and print audience, usage, and conversion metrics."""
        self._print_window("7d", 7)
        self.stdout.write("")
        self._print_window("30d", 30)

    def _print_window(self, label: str, days: int) -> None:
        now = timezone.now()
        since = now - timedelta(days=days)

        ask_qs = AskEvent.objects.filter(created_at__gte=since)
        growth_qs = GrowthEvent.objects.filter(created_at__gte=since)
        audience_qs = WebAudienceProfile.objects.filter(last_seen_at__gte=since)

        landing = growth_qs.filter(
            event_type=GrowthEvent.EVENT_LANDING_VIEW,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        starter = growth_qs.filter(
            event_type=GrowthEvent.EVENT_STARTER_CLICK,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        shares = growth_qs.filter(
            event_type=GrowthEvent.EVENT_SHARE_CLICK,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        ask_submit = growth_qs.filter(
            event_type=GrowthEvent.EVENT_ASK_SUBMIT,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()

        self.stdout.write(f"=== Growth Report ({label}) ===")
        self.stdout.write(f"Unique visitors: {audience_qs.count()}")
        self.stdout.write(
            "Unique users who asked: "
            f"{ask_qs.filter(outcome=AskEvent.OUTCOME_SERVED).values('user_id').distinct().count()}"
        )
        self.stdout.write(f"Queries fired: {ask_qs.count()}")
        self.stdout.write(
            "Queries served: "
            f"{ask_qs.filter(outcome=AskEvent.OUTCOME_SERVED).count()}"
        )
        self.stdout.write(f"Landing views: {landing}")
        self.stdout.write(
            "Starter clicks: "
            f"{starter} ({self._pct(starter, landing)}%)"
        )
        self.stdout.write(
            "Ask submits: "
            f"{ask_submit} ({self._pct(ask_submit, landing)}%)"
        )
        self.stdout.write(
            "Share clicks: "
            f"{shares} ({self._pct(shares, landing)}%)"
        )

        source_counts = {}
        for profile in audience_qs.exclude(first_utm_source=""):
            source = profile.first_utm_source
            source_counts[source] = source_counts.get(source, 0) + 1
        if source_counts:
            self.stdout.write("Top UTM sources:")
            for source, count in sorted(
                source_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:10]:
                self.stdout.write(f"  - {source}: {count}")

    @staticmethod
    def _pct(numerator: int, denominator: int) -> float:
        if not denominator:
            return 0.0
        return round((numerator / denominator) * 100, 2)
