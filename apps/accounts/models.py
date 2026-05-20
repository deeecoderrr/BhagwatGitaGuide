from __future__ import annotations

from django.conf import settings
from django.db import models


class QuotaSettings(models.Model):
    """Singleton row (pk=1): admin-editable free-tier limits; env is fallback on first create."""

    free_exports_per_month = models.PositiveIntegerField(
        default=5,
        help_text="Max computation PDF exports per month for free users (Pro unlimited).",
    )

    class Meta:
        verbose_name_plural = "Quota settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    def __str__(self) -> str:
        return "Quota settings"

    @classmethod
    def get_solo(cls) -> "QuotaSettings":
        from django.conf import settings as dj_settings

        default_limit = int(
            getattr(dj_settings, "FREE_EXPORT_LIMIT_PER_MONTH", 5) or 5
        )
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={"free_exports_per_month": default_limit},
        )
        return obj


class UserProfile(models.Model):
    """ITR-only: PDF export quota / Pro (separate from guide_api.UserSubscription)."""

    PLAN_FREE = "free"
    PLAN_PRO = "pro"
    PLAN_CHOICES = [
        (PLAN_FREE, "Free"),
        (PLAN_PRO, "Pro"),
    ]

    # Annual plan keys
    ITR_PLAN_NONE = ""
    ITR_PLAN_ESSENTIALS = "essentials"
    ITR_PLAN_PROFESSIONAL = "professional"
    ITR_ANNUAL_PLAN_CHOICES = [
        ("", "None"),
        ("essentials", "Essentials — 40 exports/yr"),
        ("professional", "Professional — 100 exports/yr"),
    ]
    ANNUAL_EXPORT_LIMITS: dict[str, int] = {
        "essentials": 40,
        "professional": 100,
    }

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="itr_profile",
    )
    # Legacy fields (kept for migration safety, no longer used for quota)
    plan = models.CharField(max_length=16, choices=PLAN_CHOICES, default=PLAN_FREE)
    subscription_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="(Legacy) Pro access valid until this instant (UTC).",
    )
    exports_this_month = models.PositiveSmallIntegerField(default=0)
    export_cycle_year = models.PositiveSmallIntegerField(default=0)
    export_cycle_month = models.PositiveSmallIntegerField(default=0)

    # Active billing fields
    itr_export_credits = models.PositiveIntegerField(
        default=0,
        help_text="Pay-as-you-go credits remaining (1 credit = 1 export, never expire).",
    )
    itr_plan = models.CharField(
        max_length=16,
        choices=ITR_ANNUAL_PLAN_CHOICES,
        default="",
        blank=True,
        help_text="Active annual plan: essentials (40/yr) or professional (100/yr).",
    )
    itr_plan_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Annual plan valid until this instant (UTC).",
    )
    itr_annual_exports_used = models.PositiveIntegerField(
        default=0,
        help_text="Exports consumed in the current annual plan cycle.",
    )

    class Meta:
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def __str__(self) -> str:
        plan_display = self.itr_plan or "none"
        return f"{self.user.username} (itr_plan={plan_display}, credits={self.itr_export_credits})"
