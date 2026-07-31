"""First-export promo and dynamic PAYG pricing."""
from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

SESSION_PROMO_USED = "itr_first_promo_used"


def first_export_promo_eligible(request: HttpRequest) -> bool:
    if not getattr(settings, "ITR_FIRST_EXPORT_PROMO_ENABLED", True):
        return False
    return not request.session.get(SESSION_PROMO_USED)


def payg_amount_paise(request: HttpRequest) -> int:
    base = int(getattr(settings, "ITR_PAYG_AMOUNT_PAISE", 2000))
    if first_export_promo_eligible(request):
        return int(getattr(settings, "ITR_FIRST_EXPORT_AMOUNT_PAISE", 1000))
    return base


def payg_list_amount_inr() -> int:
    return int(getattr(settings, "ITR_PAYG_AMOUNT_PAISE", 2000)) // 100


def mark_first_export_promo_used(request: HttpRequest) -> None:
    request.session[SESSION_PROMO_USED] = True
    request.session.modified = True


def first_export_promo_context(request: HttpRequest) -> dict:
    eligible = first_export_promo_eligible(request)
    amount_paise = payg_amount_paise(request)
    return {
        "first_export_promo": eligible,
        "payg_amount_paise": amount_paise,
        "payg_amount_inr": amount_paise // 100,
        "payg_list_amount_inr": payg_list_amount_inr(),
    }
