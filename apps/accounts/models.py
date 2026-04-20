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

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="itr_profile",
    )
    plan = models.CharField(max_length=16, choices=PLAN_CHOICES, default=PLAN_FREE)
    subscription_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Pro access valid until this instant (UTC).",
    )
    exports_this_month = models.PositiveSmallIntegerField(default=0)
    export_cycle_year = models.PositiveSmallIntegerField(default=0)
    export_cycle_month = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def __str__(self) -> str:
        return f"{self.user.username} ({self.plan})"
