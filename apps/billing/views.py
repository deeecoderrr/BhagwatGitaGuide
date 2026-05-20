from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserProfile
from apps.billing.models import RazorpayOrder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ITR credit bundles — completely separate from Bhagavad Gita app plans
# ---------------------------------------------------------------------------
ITR_BUNDLES: dict[str, dict] = {
    "payg": {
        "key": "payg",
        "label": "Pay-as-you-go",
        "credits": 1,
        "annual": False,
        "amount_paise": int(getattr(settings, "ITR_PAYG_AMOUNT_PAISE", 5000)),
        "amount_inr": int(getattr(settings, "ITR_PAYG_AMOUNT_PAISE", 5000)) // 100,
        "per_export_inr": int(getattr(settings, "ITR_PAYG_AMOUNT_PAISE", 5000)) // 100,
        "description": "One PDF export — pay only when you need it",
        "badge": None,
    },
    "essentials": {
        "key": "essentials",
        "label": "Essentials",
        "credits": 40,
        "annual": True,
        "amount_paise": int(getattr(settings, "ITR_ESSENTIALS_AMOUNT_PAISE", 100000)),
        "amount_inr": int(getattr(settings, "ITR_ESSENTIALS_AMOUNT_PAISE", 100000)) // 100,
        "per_export_inr": int(getattr(settings, "ITR_ESSENTIALS_AMOUNT_PAISE", 100000)) // 100 // 40,
        "description": "40 PDF exports per year — great for tax professionals",
        "badge": "Popular",
    },
    "professional": {
        "key": "professional",
        "label": "Professional",
        "credits": 100,
        "annual": True,
        "amount_paise": int(getattr(settings, "ITR_PROFESSIONAL_AMOUNT_PAISE", 200000)),
        "amount_inr": int(getattr(settings, "ITR_PROFESSIONAL_AMOUNT_PAISE", 200000)) // 100,
        "per_export_inr": int(getattr(settings, "ITR_PROFESSIONAL_AMOUNT_PAISE", 200000)) // 100 // 100,
        "description": "100 PDF exports per year — for busy CA offices",
        "badge": "Best value",
    },
}


def _razorpay_client():
    key = getattr(settings, "RAZORPAY_KEY_ID", "").strip()
    secret = getattr(settings, "RAZORPAY_KEY_SECRET", "").strip()
    if not key or not secret:
        return None
    import razorpay
    return razorpay.Client(auth=(key, secret))


@login_required
@require_http_methods(["GET", "POST"])
def checkout_bundle(request, bundle: str):
    """Create Razorpay order for an ITR credit bundle (payg / essentials / professional)."""
    bundle_info = ITR_BUNDLES.get(bundle)
    if not bundle_info:
        messages.error(request, "Invalid plan selected.")
        return redirect("marketing:pricing")

    doc_pk = (request.GET.get("doc") or request.POST.get("doc", "")).strip()
    client = _razorpay_client()
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "").strip()
    amount_paise = bundle_info["amount_paise"]

    if request.method == "POST" and client:
        receipt = f"itr_{bundle}_{request.user.pk}_{int(timezone.now().timestamp())}"
        try:
            order_data = client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt[:40],
                "notes": {
                    "user_id": str(request.user.pk),
                    "bundle": bundle,
                    "credits": str(bundle_info["credits"]),
                },
            })
            RazorpayOrder.objects.create(
                user=request.user,
                razorpay_order_id=order_data["id"],
                amount_paise=amount_paise,
                currency="INR",
                bundle_key=bundle,
                credits_granted=bundle_info["credits"],
                raw_payload=dict(order_data),
            )
        except Exception as exc:
            logger.exception("Razorpay bundle order create failed")
            messages.error(request, f"Payment setup failed: {exc}")
            return redirect("marketing:pricing")

        return render(request, "billing/checkout_bundle.html", {
            "key_id": key_id,
            "order_id": order_data["id"],
            "amount_paise": amount_paise,
            "bundle": bundle_info,
            "user_email": request.user.email or "",
            "doc_pk": doc_pk,
            "success_url": request.build_absolute_uri(reverse("billing:payment_success")),
        })

    return render(request, "billing/checkout_bundle.html", {
        "key_id": key_id,
        "order_id": None,
        "bundle": bundle_info,
        "client_available": client is not None,
        "doc_pk": doc_pk,
    })


@login_required
@require_http_methods(["POST"])
def payment_success(request):
    """Verify Razorpay signature and add export credits to user's wallet."""
    client = _razorpay_client()
    if not client:
        messages.error(request, "Payments are not configured.")
        return redirect("marketing:pricing")

    params = {
        "razorpay_order_id": request.POST.get("razorpay_order_id", ""),
        "razorpay_payment_id": request.POST.get("razorpay_payment_id", ""),
        "razorpay_signature": request.POST.get("razorpay_signature", ""),
    }
    doc_pk = request.POST.get("doc", "").strip()

    try:
        client.utility.verify_payment_signature(params)
    except Exception as exc:
        logger.warning("Razorpay signature verify failed: %s", exc)
        messages.error(
            request,
            "Payment verification failed. Contact support with your Razorpay receipt.",
        )
        return redirect("marketing:pricing")

    order = RazorpayOrder.objects.filter(
        user=request.user,
        razorpay_order_id=params["razorpay_order_id"],
        status=RazorpayOrder.STATUS_CREATED,
    ).first()

    credits_to_add = 0
    bundle_label = "export credit"

    if order:
        order.status = RazorpayOrder.STATUS_PAID
        order.razorpay_payment_id = params["razorpay_payment_id"]
        order.save(update_fields=["status", "razorpay_payment_id"])
        credits_to_add = order.credits_granted
        info = ITR_BUNDLES.get(order.bundle_key, {})
        bundle_label = info.get("label", "credit bundle")

    if order and credits_to_add > 0:
        from datetime import timedelta
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        bundle_key = order.bundle_key
        if bundle_key in (RazorpayOrder.BUNDLE_ESSENTIALS, RazorpayOrder.BUNDLE_PROFESSIONAL):
            # Annual plan — activate / renew
            profile.itr_plan = bundle_key
            profile.itr_plan_until = timezone.now() + timedelta(days=365)
            profile.itr_annual_exports_used = 0
            profile.save(update_fields=["itr_plan", "itr_plan_until", "itr_annual_exports_used"])
            messages.success(
                request,
                f"Payment confirmed — {bundle_label} annual plan activated. "
                f"You have {credits_to_add} exports available for the next 12 months.",
            )
        else:
            # PAYG — add to credit wallet
            profile.itr_export_credits = (profile.itr_export_credits or 0) + credits_to_add
            profile.save(update_fields=["itr_export_credits"])
            messages.success(
                request,
                f"Payment confirmed — {credits_to_add} export credit added. You can now generate your PDF.",
            )
    elif not order:
        messages.warning(
            request,
            "Payment recorded but order not found. Please contact support.",
        )

    # For PAYG: redirect back to the export page
    if doc_pk:
        try:
            return redirect("exports:create", pk=int(doc_pk))
        except (ValueError, TypeError):
            pass

    return redirect("documents:list")


@csrf_exempt
@require_http_methods(["POST"])
def razorpay_webhook(request):
    """Optional webhook for async payment capture (verify with signing secret)."""
    secret = getattr(settings, "ITR_RAZORPAY_WEBHOOK_SECRET", "").strip() or getattr(
        settings, "RAZORPAY_WEBHOOK_SECRET", "",
    ).strip()
    body = request.body
    sig = request.headers.get("X-Razorpay-Signature", "")
    if secret and sig:
        expected = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return HttpResponseBadRequest("invalid signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("bad json")

    logger.info("Razorpay webhook event: %s", payload.get("event"))
    return HttpResponse(status=200)


logger = logging.getLogger(__name__)


def _razorpay_client():
    key = getattr(settings, "RAZORPAY_KEY_ID", "").strip()
    secret = getattr(settings, "RAZORPAY_KEY_SECRET", "").strip()
    if not key or not secret:
        return None
    import razorpay

    return razorpay.Client(auth=(key, secret))


@login_required
@require_http_methods(["GET", "POST"])
def checkout_pro(request):
    """Create Razorpay order and render checkout (or show config hint)."""
    amount_paise = int(getattr(settings, "PRO_PLAN_AMOUNT_PAISE", 49900))
    client = _razorpay_client()
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "").strip()

    if request.method == "POST" and client:
        receipt = f"itr_pro_{request.user.pk}_{int(timezone.now().timestamp())}"
        try:
            order_data = client.order.create(
                {
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": receipt[:40],
                    "notes": {"user_id": str(request.user.pk)},
                }
            )
            RazorpayOrder.objects.create(
                user=request.user,
                razorpay_order_id=order_data["id"],
                amount_paise=amount_paise,
                currency="INR",
                raw_payload=dict(order_data),
            )
        except Exception as exc:
            logger.exception("Razorpay order create failed")
            messages.error(request, f"Payment setup failed: {exc}")
            return redirect("marketing:pricing")

        callback_url = request.build_absolute_uri(reverse("billing:payment_success"))
        return render(
            request,
            "billing/checkout.html",
            {
                "key_id": key_id,
                "order_id": order_data["id"],
                "amount_paise": amount_paise,
                "amount_inr": amount_paise / 100,
                "user_email": request.user.email or "",
                "callback_url": callback_url,
            },
        )

    return render(
        request,
        "billing/checkout.html",
        {
            "key_id": key_id,
            "order_id": None,
            "amount_paise": amount_paise,
            "amount_inr": amount_paise / 100,
            "client_available": client is not None,
        },
    )


@login_required
@require_http_methods(["POST"])
def payment_success(request):
    """Verify Razorpay signature and activate Pro."""
    client = _razorpay_client()
    if not client:
        messages.error(request, "Payments are not configured.")
        return redirect("marketing:pricing")

    params = {
        "razorpay_order_id": request.POST.get("razorpay_order_id", ""),
        "razorpay_payment_id": request.POST.get("razorpay_payment_id", ""),
        "razorpay_signature": request.POST.get("razorpay_signature", ""),
    }
    try:
        client.utility.verify_payment_signature(params)
    except Exception as exc:
        logger.warning("Razorpay signature verify failed: %s", exc)
        messages.error(request, "Payment verification failed. Contact support with your receipt.")
        return redirect("marketing:pricing")

    order = RazorpayOrder.objects.filter(
        user=request.user,
        razorpay_order_id=params["razorpay_order_id"],
    ).first()
    if order:
        order.status = RazorpayOrder.STATUS_PAID
        order.razorpay_payment_id = params["razorpay_payment_id"]
        order.save(update_fields=["status", "razorpay_payment_id"])

    days = int(getattr(settings, "PRO_SUBSCRIPTION_DAYS", 365))
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.plan = UserProfile.PLAN_PRO
    profile.subscription_until = timezone.now() + timedelta(days=days)
    profile.save(update_fields=["plan", "subscription_until"])

    messages.success(request, "Pro activated — unlimited computation PDF exports for your subscription period.")
    return redirect("documents:list")


@csrf_exempt
@require_http_methods(["POST"])
def razorpay_webhook(request):
    """Optional webhook for async payment capture (verify with signing secret)."""
    secret = getattr(settings, "ITR_RAZORPAY_WEBHOOK_SECRET", "").strip() or getattr(
        settings,
        "RAZORPAY_WEBHOOK_SECRET",
        "",
    ).strip()
    body = request.body
    sig = request.headers.get("X-Razorpay-Signature", "")
    if secret and sig:
        expected = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return HttpResponseBadRequest("invalid signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("bad json")

    logger.info("Razorpay webhook event: %s", payload.get("event"))
    return HttpResponse(status=200)
