from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import UserProfile


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance: User, created: bool, **kwargs) -> None:
    if created:
        UserProfile.objects.get_or_create(user=instance)
