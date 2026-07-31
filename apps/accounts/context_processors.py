from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AnonymousUser


def google_oauth(request):
    return {
        "google_oauth_configured": getattr(
            settings, "GOOGLE_OAUTH_CONFIGURED", False
        ),
    }


def support_contact(request):
    """Expose SUPPORT_EMAIL for account templates (mailto, footnotes)."""
    return {"support_email": getattr(settings, "SUPPORT_EMAIL", "")}


def itr_support(request):
    """ITR support contact links (primary email, backup, WhatsApp)."""
    primary = getattr(
        settings,
        "ITR_CONTACT_EMAIL",
        "askbhagwatgitasupport@gmail.com",
    ).strip()
    backup = getattr(settings, "ITR_SUPPORT_EMAIL_BACKUP", "").strip()
    whatsapp = getattr(settings, "ITR_WHATSAPP_NUMBER", "").strip().lstrip("+")
    wa_url = f"https://wa.me/{whatsapp}" if whatsapp else ""
    guarantee_hours = int(getattr(settings, "ITR_GUARANTEE_HOURS", 24))
    from apps.marketing.itr_copy import ITR_FORMS_COMMA, ITR_FORMS_FAQ, ITR_FORMS_SLASH

    export_count = 0
    try:
        from apps.exports.models import ExportedSummary

        export_count = ExportedSummary.objects.count()
    except Exception:
        pass
    return {
        "itr_contact_email": primary,
        "itr_support_email_backup": backup,
        "itr_whatsapp_number": whatsapp,
        "itr_whatsapp_url": wa_url,
        "itr_guarantee_hours": guarantee_hours,
        "itr_exports_generated": export_count,
        "itr_show_export_stat": export_count >= 5,
        "itr_forms_comma": ITR_FORMS_COMMA,
        "itr_forms_slash": ITR_FORMS_SLASH,
        "itr_forms_faq": ITR_FORMS_FAQ,
    }


def account_profile(request):
    user = request.user
    if isinstance(user, AnonymousUser) or not user.is_authenticated:
        return {"account_profile": None}
    from apps.accounts.models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=user)
    return {"account_profile": profile}


def support_chat(request):
    enabled = getattr(settings, "ITR_SUPPORT_CHAT_ENABLED", False)
    unread = 0
    staff_inbox_unread = 0
    if enabled and request.user.is_authenticated:
        try:
            from apps.support_chat.models import SupportMessage

            unread = SupportMessage.objects.filter(
                thread__user=request.user,
                is_staff=True,
                read_by_user_at__isnull=True,
            ).count()
            if getattr(request.user, "is_staff", False):
                staff_inbox_unread = SupportMessage.objects.filter(
                    is_staff=False,
                    read_by_staff_at__isnull=True,
                    thread__status__in=(
                        "open",
                        "waiting_staff",
                        "waiting_user",
                    ),
                ).count()
        except Exception:
            unread = 0
            staff_inbox_unread = 0
    return {
        "itr_support_chat_enabled": enabled,
        "support_chat_unread": unread,
        "staff_inbox_unread": staff_inbox_unread,
    }
