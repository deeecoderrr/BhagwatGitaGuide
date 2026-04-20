"""Lifetime ITR funnel stats from the database (exports + analytics events)."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand


def _itr_prefix_segment() -> str:
    raw = getattr(settings, "ITR_URL_PREFIX", "/itr-computation")
    raw = raw or "/itr-computation"
    return raw.strip().strip("/")


def _itr_home_path() -> str:
    return f"/{_itr_prefix_segment()}/"


def _itr_pricing_path() -> str:
    return f"/{_itr_prefix_segment()}/pricing/"


class Command(BaseCommand):
    help = (
        "Print lifetime ITR computation stats: exports (anonymous vs logged-in), "
        "documents created, and marketing GrowthEvents. "
        "Home/pricing views are capped at once per browser per day "
        "(see analytics middleware)."
    )

    def handle(self, *args, **options):
        if not getattr(settings, "ITR_ENABLED", False):
            msg = "ITR_ENABLED is false — nothing to report."
            self.stdout.write(self.style.WARNING(msg))
            return

        from django.db.models import Max, Min

        from apps.analytics.models import GrowthEvent, VisitorProfile
        from apps.documents.models import Document
        from apps.exports.models import ExportedSummary

        home = _itr_home_path()
        pricing = _itr_pricing_path()

        exports = ExportedSummary.objects.all()
        total_exports = exports.count()
        anon_exports = exports.filter(document__user__isnull=True).count()
        auth_exports = exports.filter(document__user__isnull=False).count()

        export_range = exports.aggregate(
            first=Min("created_at"),
            last=Max("created_at"),
        )

        docs_anon = Document.objects.filter(user__isnull=True).count()
        docs_auth = Document.objects.filter(user__isnull=False).count()

        ge_home = GrowthEvent.objects.filter(
            event_type=GrowthEvent.EVENT_PAGE_VIEW,
            path=home,
        )
        ge_pricing = GrowthEvent.objects.filter(
            event_type=GrowthEvent.EVENT_PRICING_VIEW,
            path=pricing,
        )

        visitors = VisitorProfile.objects.count()

        title = "=== ITR Summary Generator — lifetime stats ==="
        self.stdout.write(self.style.NOTICE(title))
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Successful PDF exports"))
        self.stdout.write(
            f"  Total exports (rows in ExportedSummary): {total_exports}"
        )
        self.stdout.write(
            f"    • Anonymous (document has no user): {anon_exports}"
        )
        self.stdout.write(
            f"    • Logged-in accounts:              {auth_exports}"
        )
        if export_range["first"]:
            self.stdout.write(
                "  First export: %s — Last: %s"
                % (export_range["first"], export_range["last"])
            )
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Documents (upload / import rows)"))
        self.stdout.write(f"  Anonymous (user is null): {docs_anon}")
        self.stdout.write(f"  With account:             {docs_auth}")
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Marketing funnel (GrowthEvent)"))
        self.stdout.write(
            f"  ITR home page events ({home}): {ge_home.count()}"
        )
        self.stdout.write(
            f"  Pricing page events ({pricing}): {ge_pricing.count()}"
        )
        self.stdout.write(
            "  Unique browser cookies (VisitorProfile, ITR tracking): "
            f"{visitors}"
        )
        self.stdout.write("")
        notes = (
            "Notes:\n"
            "  • Each successful export creates one ExportedSummary row "
            "(even if the PDF is later purged from storage).\n"
            "  • Home/pricing GrowthEvents are logged at most once per browser "
            "per calendar day (session cap), so they under-count raw page "
            "loads.\n"
            "  • VisitorProfile counts distinct cookies that hit ITR routes "
            "with tracking — not only /itr-computation/.\n"
            "  • For full page-view analytics use Search Console / GA4 / "
            "Plausible in addition."
        )
        self.stdout.write(self.style.WARNING(notes))
