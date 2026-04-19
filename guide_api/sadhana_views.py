"""REST APIs for guided sadhana programs (mobile + web reuse)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from guide_api.models import (
    BillingRecord,
    SadhanaDay,
    SadhanaDayCompletion,
    SadhanaEnrollment,
    SadhanaProgram,
    SadhanaStep,
)


def _resolve_request_user(request):
    """Match chat-ui session, token session, or DRF authentication."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    session = getattr(request, "session", None)
    if session is None:
        session = getattr(request, "_request", request).session
    username = session.get("chat_ui_auth_username")
    if username:
        User = get_user_model()
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            pass
    django_request = getattr(request, "_request", request)
    if getattr(django_request, "user", None) and django_request.user.is_authenticated:
        return django_request.user
    token_key = session.get("chat_ui_auth_token")
    if token_key:
        try:
            return Token.objects.select_related("user").get(key=token_key).user
        except Token.DoesNotExist:
            return None
    return None


def _payment_amount_for_sadhana_cycle(*, currency: str) -> int:
    currency = (currency or "").upper()
    if currency == "INR":
        return int(settings.SADHANA_CYCLE_PRICE_INR)
    return int(settings.SADHANA_CYCLE_PRICE_USD)


def _is_sadhana_cycle_amount(*, amount: int, currency: str) -> bool:
    cur = (currency or "").upper()
    return amount == _payment_amount_for_sadhana_cycle(currency=cur)


@transaction.atomic
def activate_sadhana_enrollment(
    *,
    user,
    program: SadhanaProgram,
    billing_record: BillingRecord | None = None,
) -> SadhanaEnrollment:
    """Create or extend a 30-day (configurable) access window after payment."""
    now = timezone.now()
    duration_days = int(getattr(settings, "SADHANA_CYCLE_DURATION_DAYS", 30) or 30)
    delta = timedelta(days=duration_days)
    enrollment, created = SadhanaEnrollment.objects.get_or_create(
        user=user,
        program=program,
        defaults={
            "access_starts_at": now,
            "access_ends_at": now + delta,
            "billing_record": billing_record,
            "renewal_count": 0,
        },
    )
    if not created:
        base_end = enrollment.access_ends_at
        if base_end and base_end > now:
            enrollment.access_ends_at = base_end + delta
        else:
            enrollment.access_ends_at = now + delta
        enrollment.renewal_count = (enrollment.renewal_count or 0) + 1
        if billing_record:
            enrollment.billing_record = billing_record
        enrollment.save(
            update_fields=[
                "access_ends_at",
                "renewal_count",
                "billing_record",
                "updated_at",
            ],
        )
    elif billing_record:
        enrollment.billing_record = billing_record
        enrollment.save(update_fields=["billing_record", "updated_at"])
    return enrollment


def _active_enrollment(user, program: SadhanaProgram) -> SadhanaEnrollment | None:
    if not user:
        return None
    now = timezone.now()
    return (
        SadhanaEnrollment.objects.filter(
            user=user,
            program=program,
            access_starts_at__lte=now,
            access_ends_at__gte=now,
        )
        .order_by("-access_ends_at")
        .first()
    )


def _step_payload(step: SadhanaStep) -> dict:
    return {
        "id": step.id,
        "sequence": step.sequence,
        "step_type": step.step_type,
        "title": step.title,
        "instructions": step.instructions or "",
        "audio_url": step.audio_url or "",
        "video_url": step.video_url or "",
        "duration_minutes": step.duration_minutes,
    }


def _completed_day_ids(
    *,
    program: SadhanaProgram,
    enrollment: SadhanaEnrollment | None,
    user,
) -> set[int]:
    ids: set[int] = set()
    if enrollment:
        ids.update(
            SadhanaDayCompletion.objects.filter(
                enrollment=enrollment,
            ).values_list(
                "day_id",
                flat=True,
            ),
        )
    if user:
        ids.update(
            SadhanaDayCompletion.objects.filter(
                user=user,
                enrollment__isnull=True,
                day__program=program,
            ).values_list(
                "day_id",
                flat=True,
            ),
        )
    return ids


def _steps_content_unlocked(
    program: SadhanaProgram,
    day: SadhanaDay,
    enrollment: SadhanaEnrollment | None,
) -> bool:
    if day.day_number == program.free_sample_day_number:
        return True
    if enrollment is None:
        return False
    if day.day_number <= 1:
        return True
    return SadhanaDayCompletion.objects.filter(
        enrollment=enrollment,
        day__program=program,
        day__day_number=day.day_number - 1,
    ).exists()


def _day_summary_dict(
    program: SadhanaProgram,
    day: SadhanaDay,
    enrollment: SadhanaEnrollment | None,
    completed_ids: set[int],
) -> dict:
    is_free_day = day.day_number == program.free_sample_day_number
    unlocked = _steps_content_unlocked(program, day, enrollment)
    return {
        "day_number": day.day_number,
        "title": day.title,
        "summary": day.summary or "",
        "unlocked": unlocked,
        "completed": day.id in completed_ids,
        "is_free_sample": is_free_day,
    }


class SadhanaProgramListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        user = _resolve_request_user(request)
        qs = SadhanaProgram.objects.filter(is_published=True).order_by(
            "sort_order",
            "title",
        )
        results = []
        for p in qs:
            enr = _active_enrollment(user, p) if user else None
            results.append(
                {
                    "slug": p.slug,
                    "title": p.title,
                    "subtitle": p.subtitle or "",
                    "description": p.description or "",
                    "philosophy_blurb": p.philosophy_blurb or "",
                    "duration_days": p.duration_days,
                    "estimated_minutes_per_day": p.estimated_minutes_per_day,
                    "free_sample_day_number": p.free_sample_day_number,
                    "has_active_enrollment": bool(enr),
                    "access_ends_at": (
                        enr.access_ends_at.isoformat()
                        if enr
                        else None
                    ),
                "pricing": {
                    "cycle_days": settings.SADHANA_CYCLE_DURATION_DAYS,
                    "amount_minor_inr": settings.SADHANA_CYCLE_PRICE_INR,
                    "amount_minor_usd": settings.SADHANA_CYCLE_PRICE_USD,
                },
                },
            )
        return Response({"results": results, "count": len(results)})


class SadhanaProgramDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        try:
            program = SadhanaProgram.objects.prefetch_related(
                Prefetch(
                    "days",
                    queryset=SadhanaDay.objects.order_by("day_number"),
                ),
            ).get(slug=slug, is_published=True)
        except SadhanaProgram.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Program not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        user = _resolve_request_user(request)
        enrollment = _active_enrollment(user, program) if user else None
        completed_ids = _completed_day_ids(
            program=program,
            enrollment=enrollment,
            user=user,
        )
        days_out = []
        for d in program.days.all():
            days_out.append(
                _day_summary_dict(program, d, enrollment, completed_ids),
            )
        return Response(
            {
                "slug": program.slug,
                "title": program.title,
                "subtitle": program.subtitle or "",
                "description": program.description or "",
                "philosophy_blurb": program.philosophy_blurb or "",
                "duration_days": program.duration_days,
                "estimated_minutes_per_day": program.estimated_minutes_per_day,
                "free_sample_day_number": program.free_sample_day_number,
                "has_active_enrollment": bool(enrollment),
                "access_starts_at": (
                    enrollment.access_starts_at.isoformat() if enrollment else None
                ),
                "access_ends_at": (
                    enrollment.access_ends_at.isoformat() if enrollment else None
                ),
                "renewal_count": enrollment.renewal_count if enrollment else 0,
                "days": days_out,
                "pricing": {
                    "cycle_days": settings.SADHANA_CYCLE_DURATION_DAYS,
                    "amount_minor_inr": settings.SADHANA_CYCLE_PRICE_INR,
                    "amount_minor_usd": settings.SADHANA_CYCLE_PRICE_USD,
                },
            },
        )


class SadhanaDayDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug: str, day_number: int):
        try:
            program = SadhanaProgram.objects.get(slug=slug, is_published=True)
            day = SadhanaDay.objects.prefetch_related(
                Prefetch(
                    "steps",
                    queryset=SadhanaStep.objects.order_by("sequence"),
                ),
            ).get(program=program, day_number=day_number)
        except (SadhanaProgram.DoesNotExist, SadhanaDay.DoesNotExist):
            return Response(
                {"error": {"code": "not_found", "message": "Day not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        user = _resolve_request_user(request)
        enrollment = _active_enrollment(user, program) if user else None
        completed_ids = _completed_day_ids(
            program=program,
            enrollment=enrollment,
            user=user,
        )
        is_free = day.day_number == program.free_sample_day_number
        unlocked = _steps_content_unlocked(program, day, enrollment)
        locked_reason = None
        if not unlocked:
            if (
                enrollment is None
                and day.day_number != program.free_sample_day_number
            ):
                locked_reason = "purchase_required"
            elif enrollment is not None:
                locked_reason = "complete_previous_day"

        return Response(
            {
                "slug": program.slug,
                "day_number": day.day_number,
                "title": day.title,
                "summary": day.summary or "",
                "intention": day.intention or "",
                "unlocked": unlocked,
                "completed": day.id in completed_ids,
                "is_free_sample": is_free,
                "steps": (
                    [_step_payload(s) for s in day.steps.all()]
                    if unlocked
                    else []
                ),
                "locked_reason": locked_reason,
            },
        )


class SadhanaDayCompleteView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, slug: str, day_number: int):
        user = _resolve_request_user(request)
        if not user:
            return Response(
                {"error": {"code": "auth_required", "message": "Sign in required."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            program = SadhanaProgram.objects.get(slug=slug, is_published=True)
            day = SadhanaDay.objects.get(program=program, day_number=day_number)
        except (SadhanaProgram.DoesNotExist, SadhanaDay.DoesNotExist):
            return Response(
                {"error": {"code": "not_found", "message": "Day not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        enrollment = _active_enrollment(user, program)
        is_free = day.day_number == program.free_sample_day_number

        if not _steps_content_unlocked(program, day, enrollment):
            return Response(
                {
                    "error": {
                        "code": "day_locked",
                        "message": "Open this day in order — complete the previous step first.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not enrollment and not is_free:
            return Response(
                {
                    "error": {
                        "code": "purchase_required",
                        "message": "Subscribe to a sadhana cycle to complete this day.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        created = False
        if enrollment:
            _, created = SadhanaDayCompletion.objects.get_or_create(
                enrollment=enrollment,
                day=day,
            )
        elif is_free:
            _, created = SadhanaDayCompletion.objects.get_or_create(
                user=user,
                day=day,
                enrollment=None,
                defaults={},
            )

        return Response(
            {
                "success": True,
                "day_number": day_number,
                "already_completed": not created,
            },
        )


def _browser_billing_currency(request) -> str:
    """Match ``CreateOrderView`` INR vs USD heuristics without importing ``views``."""
    meta = request.META
    for key in (
        "HTTP_CF_IPCOUNTRY",
        "HTTP_CLOUDFRONT_VIEWER_COUNTRY",
        "HTTP_X_COUNTRY_CODE",
        "HTTP_X_APPENGINE_COUNTRY",
    ):
        value = str(meta.get(key, "")).strip().upper()
        if len(value) == 2 and value.isalpha():
            return "INR" if value == "IN" else "USD"
    accept_language = str(meta.get("HTTP_ACCEPT_LANGUAGE", "")).lower()
    if (
        "-in" in accept_language
        or "en-in" in accept_language
        or "hi-in" in accept_language
    ):
        return "INR"
    requested = str(request.GET.get("currency") or "").strip().upper()
    if requested in {"INR", "USD"}:
        return requested
    return "INR"


class SadhanaMeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        user = _resolve_request_user(request)
        if not user:
            return Response(
                {"error": {"code": "auth_required", "message": "Sign in required."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        now = timezone.now()
        rows = []
        for enr in SadhanaEnrollment.objects.filter(
            user=user,
            access_ends_at__gte=now,
        ).select_related("program"):
            rows.append(
                {
                    "program_slug": enr.program.slug,
                    "title": enr.program.title,
                    "access_starts_at": enr.access_starts_at.isoformat(),
                    "access_ends_at": enr.access_ends_at.isoformat(),
                    "renewal_count": enr.renewal_count,
                },
            )
        return Response({"enrollments": rows})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class PracticeHubView(View):
    """Browser practice hub (same APIs as mobile with session cookies)."""

    def get(self, request):
        return render(
            request,
            "guide_api/practice_hub.html",
            {
                "language": request.GET.get("language") or "en",
                "billing_currency": _browser_billing_currency(request),
            },
        )
