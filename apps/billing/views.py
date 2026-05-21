from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
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
@require_http_methods(["GET"])
def checkout_bundle(request, bundle: str):
    """Show the single-page checkout for an ITR credit bundle (AJAX order creation)."""
    bundle_info = ITR_BUNDLES.get(bundle)
    if not bundle_info:
        messages.error(request, "Invalid plan selected.")
        return redirect("marketing:pricing")

    doc_pk = (request.GET.get("doc") or "").strip()
    return render(request, "billing/checkout_bundle.html", {
        "bundle": bundle_info,
        "client_available": _razorpay_client() is not None,
        "doc_pk": doc_pk,
        "user_email": request.user.email or "",
        "bundle_init_url": reverse("billing:checkout_bundle_init", kwargs={"bundle": bundle}),
        "success_url": reverse("billing:payment_success"),
    })


@login_required
@require_http_methods(["POST"])
def checkout_bundle_init(request, bundle: str):
    """AJAX: create Razorpay order for a logged-in user and return JSON."""
    bundle_info = ITR_BUNDLES.get(bundle)
    if not bundle_info:
        return JsonResponse({"error": "Invalid plan."}, status=400)

    client = _razorpay_client()
    if not client:
        return JsonResponse({"error": "Payments are not configured."}, status=503)

    key_id = getattr(settings, "RAZORPAY_KEY_ID", "").strip()
    amount_paise = bundle_info["amount_paise"]
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
    except Exception:
        logger.exception("Razorpay bundle order create failed")
        return JsonResponse({"error": "Payment setup failed. Please try again."}, status=500)

    return JsonResponse({
        "order_id": order_data["id"],
        "key_id": key_id,
        "amount_paise": amount_paise,
        "amount_inr": bundle_info["amount_inr"],
        "label": bundle_info["label"],
        "description": bundle_info["description"],
    })


@login_required
@require_http_methods(["POST"])
def payment_success(request):
    """Verify Razorpay signature and grant export credits / activate annual plan."""
    try:
        return _payment_success_inner(request)
    except Exception as exc:
        rzp_order_id = request.POST.get("razorpay_order_id", "?")
        logger.critical(
            "UNHANDLED EXCEPTION in payment_success — user=%s order=%s error=%s",
            getattr(request.user, "pk", "?"),
            rzp_order_id,
            exc,
            exc_info=True,
        )
        messages.warning(
            request,
            "Your payment was received by Razorpay, but a server error occurred "
            "while applying your credits. Your money is safe. "
            f"Please contact support with reference: {rzp_order_id}",
        )
        return redirect("marketing:pricing")


def _payment_success_inner(request):
    """Core logic for payment_success — wrapped in a top-level try/except by the caller."""
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

    rzp_order_id = params["razorpay_order_id"]

    # Idempotency: check if this order was already processed (e.g. page refresh)
    already_paid = RazorpayOrder.objects.filter(
        user=request.user,
        razorpay_order_id=rzp_order_id,
        status=RazorpayOrder.STATUS_PAID,
    ).first()
    if already_paid:
        info = ITR_BUNDLES.get(already_paid.bundle_key, {})
        bundle_label = info.get("label", "credit bundle")
        messages.success(request, f"Payment already confirmed — {bundle_label} applied to your account.")
        if doc_pk:
            try:
                return redirect("exports:create", pk=int(doc_pk))
            except (ValueError, TypeError):
                pass
        return redirect("documents:list")

    order = RazorpayOrder.objects.filter(
        user=request.user,
        razorpay_order_id=rzp_order_id,
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
        bundle_key = order.bundle_key
        try:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
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
        except Exception as exc:
            logger.critical(
                "PAYMENT CREDIT SAVE FAILED — user=%s order=%s payment=%s bundle=%s credits=%s error=%s",
                request.user.pk,
                order.razorpay_order_id,
                order.razorpay_payment_id,
                bundle_key,
                credits_to_add,
                exc,
                exc_info=True,
            )
            messages.warning(
                request,
                "Your payment was captured successfully, but there was a temporary error "
                "applying your credits. Your account will be updated within 24 hours. "
                f"Please contact support with reference: {order.razorpay_order_id}",
            )
    elif not order:
        messages.warning(
            request,
            "Payment recorded but order not found. Please contact support with your Razorpay receipt.",
        )

    # Redirect back to the export page when coming from a specific document
    if doc_pk:
        try:
            return redirect("exports:create", pk=int(doc_pk))
        except (ValueError, TypeError, NoReverseMatch):
            pass

    return redirect("documents:list")


@csrf_exempt
@require_http_methods(["POST"])
def razorpay_webhook(request):
    """Webhook fallback — activates credits when payment.captured fires.

    Handles the case where a user closes the tab before the payment_success
    redirect fires, so the payment is captured but credits are never granted.
    All logic is idempotent: if the order is already STATUS_PAID, it is skipped.
    """
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

    event = payload.get("event")
    logger.info("Razorpay ITR webhook event: %s", event)

    if event == "payment.captured":
        try:
            _webhook_activate_payment(payload)
        except Exception as exc:
            logger.exception("Razorpay webhook activation failed: %s", exc)
            # Return 200 so Razorpay does not retry endlessly;
            # the CRITICAL log above will alert on-call.

    return HttpResponse(status=200)


def _webhook_activate_payment(payload: dict) -> None:
    """Activate credits for an authenticated or guest captured payment (idempotent)."""
    from datetime import timedelta

    from apps.billing.models import GuestOrder

    payment_entity = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
    )
    rzp_order_id = payment_entity.get("order_id", "").strip()
    rzp_payment_id = payment_entity.get("id", "").strip()

    if not rzp_order_id:
        logger.warning("Razorpay webhook: no order_id in payment.captured payload")
        return

    # ── Authenticated order ──────────────────────────────────────────────────
    order = (
        RazorpayOrder.objects.filter(
            razorpay_order_id=rzp_order_id,
            status=RazorpayOrder.STATUS_CREATED,
        )
        .select_related("user")
        .first()
    )

    if order:
        logger.info(
            "Razorpay webhook activating authenticated order=%s user=%s bundle=%s",
            rzp_order_id,
            order.user_id,
            order.bundle_key,
        )
        order.status = RazorpayOrder.STATUS_PAID
        order.razorpay_payment_id = rzp_payment_id
        order.save(update_fields=["status", "razorpay_payment_id"])

        if order.credits_granted > 0:
            profile, _ = UserProfile.objects.get_or_create(user=order.user)
            bundle_key = order.bundle_key
            if bundle_key in (
                RazorpayOrder.BUNDLE_ESSENTIALS,
                RazorpayOrder.BUNDLE_PROFESSIONAL,
            ):
                profile.itr_plan = bundle_key
                profile.itr_plan_until = timezone.now() + timedelta(days=365)
                profile.itr_annual_exports_used = 0
                profile.save(
                    update_fields=["itr_plan", "itr_plan_until", "itr_annual_exports_used"]
                )
            else:
                profile.itr_export_credits = (
                    profile.itr_export_credits or 0
                ) + order.credits_granted
                profile.save(update_fields=["itr_export_credits"])
        return

    # ── Already paid (idempotency guard) ────────────────────────────────────
    if RazorpayOrder.objects.filter(
        razorpay_order_id=rzp_order_id,
        status=RazorpayOrder.STATUS_PAID,
    ).exists():
        logger.info(
            "Razorpay webhook: authenticated order=%s already paid, skipping",
            rzp_order_id,
        )
        return

    # ── Guest order ──────────────────────────────────────────────────────────
    guest_order = GuestOrder.objects.filter(
        razorpay_order_id=rzp_order_id,
        status=GuestOrder.STATUS_CREATED,
    ).first()
    if guest_order:
        logger.info(
            "Razorpay webhook activating guest order=%s email=%s",
            rzp_order_id,
            guest_order.guest_email,
        )
        guest_order.status = GuestOrder.STATUS_PAID
        guest_order.razorpay_payment_id = rzp_payment_id
        guest_order.save(update_fields=["status", "razorpay_payment_id"])
        return

    if GuestOrder.objects.filter(
        razorpay_order_id=rzp_order_id,
        status=GuestOrder.STATUS_PAID,
    ).exists():
        logger.info(
            "Razorpay webhook: guest order=%s already paid, skipping",
            rzp_order_id,
        )
        return

    logger.warning(
        "Razorpay webhook: no pending order found for order_id=%s", rzp_order_id
    )


# ── Guest PAYG checkout (no login required) ──────────────────────────────────

# Session key used to track a guest's paid export credits.
SESSION_GUEST_CREDITS = "itr_guest_credits"


@require_http_methods(["GET"])
def guest_checkout(request):
    """PAYG ₹50 checkout for unauthenticated guests — email-only, AJAX flow."""
    # Logged-in users go through the normal checkout.
    if request.user.is_authenticated:
        doc_pk = (request.GET.get("doc") or "").strip()
        url = reverse("billing:checkout_bundle", kwargs={"bundle": "payg"})
        if doc_pk:
            url = f"{url}?doc={doc_pk}"
        return redirect(url)

    bundle_info = ITR_BUNDLES["payg"]
    doc_pk = (request.GET.get("doc") or "").strip()
    return render(
        request,
        "billing/guest_checkout.html",
        {
            "bundle": bundle_info,
            "doc_pk": doc_pk,
            "client_available": _razorpay_client() is not None,
            "guest_init_url": reverse("billing:guest_checkout_init"),
            "guest_success_url": reverse("billing:guest_payment_success"),
        },
    )


@require_http_methods(["POST"])
def guest_checkout_init(request):
    """AJAX: create Razorpay order and return JSON (no email required from user).

    GuestOrder is created later in guest_payment_success once we have the
    email the user typed inside the Razorpay modal.

    Response: {"order_id": ..., "key_id": ..., "amount_paise": ..., "amount_inr": ...}
    """
    client = _razorpay_client()
    if not client:
        return JsonResponse(
            {"error": "Payments are not configured. Contact support."},
            status=503,
        )

    bundle_info = ITR_BUNDLES["payg"]
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "").strip()
    receipt = f"itr_g_{int(timezone.now().timestamp())}"

    try:
        order_data = client.order.create(
            {
                "amount": bundle_info["amount_paise"],
                "currency": "INR",
                "receipt": receipt[:40],
                "notes": {"bundle": "payg"},
            }
        )
    except Exception:
        logger.exception("Guest checkout init: Razorpay order create failed")
        return JsonResponse(
            {"error": "Payment setup failed. Please try again or contact support."},
            status=500,
        )

    return JsonResponse(
        {
            "order_id": order_data["id"],
            "key_id": key_id,
            "amount_paise": bundle_info["amount_paise"],
            "amount_inr": bundle_info["amount_inr"],
        }
    )


@require_http_methods(["POST"])
def guest_payment_success(request):
    """Verify guest Razorpay signature and grant one session export credit."""
    from apps.billing.models import GuestOrder

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
        logger.warning("Guest payment signature verify failed: %s", exc)
        messages.error(
            request,
            "Payment verification failed. Contact support with your Razorpay receipt.",
        )
        return redirect("marketing:pricing")

    rzp_order_id = params["razorpay_order_id"]

    # Idempotency: already processed (e.g. page refresh after success).
    already = GuestOrder.objects.filter(
        razorpay_order_id=rzp_order_id,
        status=GuestOrder.STATUS_PAID,
    ).first()
    if already:
        request.session[SESSION_GUEST_CREDITS] = max(
            request.session.get(SESSION_GUEST_CREDITS, 0), 1
        )
        request.session.modified = True
        messages.success(request, "Payment already confirmed — your export credit is ready.")
        if doc_pk:
            try:
                from django.core import signing as _signing
                _token = _signing.dumps(
                    {"go": already.pk, "doc": int(doc_pk)},
                    salt="itr-guest-export",
                )
                return redirect(
                    reverse("exports:create", args=[int(doc_pk)]) + "?guest_token=" + _token
                )
            except (ValueError, TypeError):
                pass
        return redirect("documents:list")

    # No pre-existing GuestOrder (email-free flow): create it now using the
    # email the user typed inside Razorpay's own checkout modal.
    guest_order = GuestOrder.objects.filter(
        razorpay_order_id=rzp_order_id,
    ).first()

    if not guest_order:
        # Fetch payment details from Razorpay to get the customer's email.
        try:
            pay_data = client.payment.fetch(params["razorpay_payment_id"])
            guest_email = (pay_data.get("email") or "").strip().lower()
            guest_phone = (pay_data.get("contact") or "").strip()
        except Exception:
            logger.exception("Guest checkout: failed to fetch payment details from Razorpay")
            guest_email = ""
            guest_phone = ""

        # EmailField is required; fall back to a placeholder if Razorpay gives nothing.
        if not guest_email:
            guest_email = f"guest+{rzp_order_id}@razorpay.internal"

        try:
            guest_order = GuestOrder.objects.create(
                guest_name="Guest",
                guest_email=guest_email,
                guest_phone=guest_phone,
                razorpay_order_id=rzp_order_id,
                amount_paise=ITR_BUNDLES["payg"]["amount_paise"],
                credits_granted=1,
                status=GuestOrder.STATUS_PAID,
                razorpay_payment_id=params["razorpay_payment_id"],
                raw_payload={},
            )
        except Exception as exc:
            logger.critical(
                "GUEST PAYMENT SAVE FAILED — order=%s payment=%s error=%s",
                rzp_order_id,
                params["razorpay_payment_id"],
                exc,
                exc_info=True,
            )
            messages.warning(
                request,
                "Your payment was captured but there was a temporary error. "
                f"Contact support with reference: {rzp_order_id}",
            )
            return redirect("marketing:pricing")
    else:
        # Pre-existing order (e.g. created via legacy email flow or webhook).
        if guest_order.status == GuestOrder.STATUS_CREATED:
            try:
                guest_order.status = GuestOrder.STATUS_PAID
                guest_order.razorpay_payment_id = params["razorpay_payment_id"]
                guest_order.save(update_fields=["status", "razorpay_payment_id"])
            except Exception as exc:
                logger.critical(
                    "GUEST PAYMENT SAVE FAILED — order=%s payment=%s error=%s",
                    rzp_order_id,
                    params["razorpay_payment_id"],
                    exc,
                    exc_info=True,
                )
                messages.warning(
                    request,
                    "Your payment was captured but there was a temporary error. "
                    f"Contact support with reference: {rzp_order_id}",
                )
                return redirect("marketing:pricing")

    # Grant session credit.
    request.session[SESSION_GUEST_CREDITS] = (
        request.session.get(SESSION_GUEST_CREDITS, 0) + (guest_order.credits_granted if guest_order else 1)
    )
    request.session.modified = True
    messages.success(
        request,
        "Payment confirmed — your export credit is ready. Generate your PDF now.",
    )

    if doc_pk:
        try:
            from django.core import signing as _signing
            _token = _signing.dumps(
                {"go": guest_order.pk, "doc": int(doc_pk)},
                salt="itr-guest-export",
            )
            return redirect(
                reverse("exports:create", args=[int(doc_pk)]) + "?guest_token=" + _token
            )
        except (ValueError, TypeError):
            pass
    return redirect("documents:list")


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
def _pro_payment_success(request):  # noqa: unused — shadowed by ITR payment_success above
    """Verify Razorpay signature and activate Pro (legacy/dead-code path)."""
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
