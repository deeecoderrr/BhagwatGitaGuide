"""REST APIs for curated practice workflows (single-session flows, catalog + tags)."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from guide_api.models import (
    BillingRecord,
    PracticeTag,
    PracticeWorkflow,
    PracticeWorkflowEnrollment,
    PracticeWorkflowStep,
)
from guide_api.sadhana_views import (
    _coerce_subtitle_tracks,
    _coerce_timed_cues,
    _primary_media,
    _resolve_request_user,
)
from guide_api.subscription_helpers import user_has_active_pro


def purchase_currency_options(workflow: PracticeWorkflow) -> list[str]:
    """Currencies with a configured purchase price (for client checkout)."""
    out: list[str] = []
    if workflow.purchase_price_minor_inr and int(workflow.purchase_price_minor_inr) > 0:
        out.append("INR")
    if workflow.purchase_price_minor_usd and int(workflow.purchase_price_minor_usd) > 0:
        out.append("USD")
    return out


def workflow_purchase_amount_minor(workflow: PracticeWorkflow, *, currency: str) -> int | None:
    """Return Razorpay minor units for the workflow in the given currency, or None if unset."""
    cur = (currency or "").upper()
    if cur == "INR":
        return workflow.purchase_price_minor_inr
    return workflow.purchase_price_minor_usd


@transaction.atomic
def activate_workflow_enrollment(
    *,
    user,
    workflow: PracticeWorkflow,
    billing_record: BillingRecord | None = None,
) -> PracticeWorkflowEnrollment:
    """Create or extend access after a verified workflow purchase."""
    now = timezone.now()
    days = workflow.purchase_access_days
    if days is not None and int(days) > 0:
        delta = timedelta(days=int(days))
        new_end = now + delta
    else:
        delta = None
        new_end = None

    enrollment, created = PracticeWorkflowEnrollment.objects.get_or_create(
        user=user,
        workflow=workflow,
        defaults={
            "access_starts_at": now,
            "access_ends_at": new_end,
            "billing_record": billing_record,
        },
    )
    if not created:
        if new_end is None:
            enrollment.access_ends_at = None
        else:
            assert delta is not None
            base_end = enrollment.access_ends_at
            if base_end is None or base_end <= now:
                enrollment.access_ends_at = now + delta
            else:
                enrollment.access_ends_at = base_end + delta
        if billing_record:
            enrollment.billing_record = billing_record
        enrollment.save(
            update_fields=[
                "access_ends_at",
                "billing_record",
                "updated_at",
            ],
        )
    elif billing_record:
        enrollment.billing_record = billing_record
        enrollment.save(update_fields=["billing_record", "updated_at"])
    return enrollment


def _billing_grants_access(br: BillingRecord | None) -> bool:
    if br is None:
        return True
    return br.payment_status in (
        BillingRecord.STATUS_VERIFIED,
        BillingRecord.STATUS_CAPTURED,
    )


def _active_workflow_enrollment(
    user,
    workflow: PracticeWorkflow,
) -> PracticeWorkflowEnrollment | None:
    if not user:
        return None
    now = timezone.now()
    qs = (
        PracticeWorkflowEnrollment.objects.filter(
            user=user,
            workflow=workflow,
            access_starts_at__lte=now,
        )
        .filter(Q(access_ends_at__isnull=True) | Q(access_ends_at__gte=now))
        .select_related("billing_record")
        .order_by("-access_ends_at")
    )
    for enr in qs:
        if enr.billing_record_id and not _billing_grants_access(enr.billing_record):
            continue
        return enr
    return None


def _workflow_content_unlocked(user, workflow: PracticeWorkflow) -> bool:
    if workflow.access_mode == PracticeWorkflow.ACCESS_FREE_PUBLIC:
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if workflow.access_mode == PracticeWorkflow.ACCESS_PRO_INCLUDED:
        return user_has_active_pro(user)
    if workflow.access_mode == PracticeWorkflow.ACCESS_PURCHASE_REQUIRED:
        return _active_workflow_enrollment(user, workflow) is not None
    return False


def _locked_reason(user, workflow: PracticeWorkflow, unlocked: bool) -> str | None:
    if unlocked:
        return None
    if workflow.access_mode == PracticeWorkflow.ACCESS_PRO_INCLUDED:
        if not user or not getattr(user, "is_authenticated", False):
            return "sign_in_required"
        return "pro_required"
    if workflow.access_mode == PracticeWorkflow.ACCESS_PURCHASE_REQUIRED:
        if not user or not getattr(user, "is_authenticated", False):
            return "sign_in_required"
        return "purchase_required"
    return None


def _tag_payload(tag: PracticeTag) -> dict:
    return {
        "slug": tag.slug,
        "label": tag.label,
        "category": tag.category or "",
    }


def _collect_workflow_tags(workflow: PracticeWorkflow) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for step in workflow.steps.all():
        for tag in step.tags.all():
            if tag.slug in seen:
                continue
            seen.add(tag.slug)
            out.append(_tag_payload(tag))
    out.sort(key=lambda x: (x["category"], x["slug"]))
    return out


def _workflow_step_outline(step: PracticeWorkflowStep) -> dict:
    return {
        "sequence": step.sequence,
        "step_type": step.step_type,
        "title": step.title,
        "duration_minutes": step.duration_minutes,
        "tags": [_tag_payload(t) for t in step.tags.all()],
    }


def _workflow_step_full(step: PracticeWorkflowStep) -> dict:
    return {
        "id": step.id,
        "sequence": step.sequence,
        "step_type": step.step_type,
        "title": step.title,
        "instructions": step.instructions or "",
        "audio_url": step.audio_url or "",
        "video_url": step.video_url or "",
        "duration_minutes": step.duration_minutes,
        "subtitle_tracks": _coerce_subtitle_tracks(step.subtitle_tracks),
        "timed_cues": _coerce_timed_cues(step.timed_cues),
        "safety_tier": step.safety_tier,
        "requires_standing": step.requires_standing,
        "primary_media": _primary_media(step),
        "tags": [_tag_payload(t) for t in step.tags.all()],
    }


class PracticeTagListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = PracticeTag.objects.all().order_by("sort_order", "slug")
        category = (request.GET.get("category") or "").strip()
        if category:
            qs = qs.filter(category=category)
        tags = list(qs)
        return Response(
            {
                "results": [_tag_payload(t) for t in tags],
                "count": len(tags),
            },
        )


class PracticeWorkflowListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        user = _resolve_request_user(request)
        qs = PracticeWorkflow.objects.filter(is_published=True)
        tag_slug = (request.GET.get("tag") or "").strip()
        if tag_slug:
            qs = qs.filter(steps__tags__slug=tag_slug).distinct()
        qs = qs.order_by("sort_order", "title").prefetch_related(
            Prefetch(
                "steps",
                queryset=PracticeWorkflowStep.objects.order_by(
                    "sequence",
                ).prefetch_related("tags"),
            ),
        )
        results = []
        for w in qs:
            unlocked = _workflow_content_unlocked(user, w)
            results.append(
                {
                    "slug": w.slug,
                    "title": w.title,
                    "subtitle": w.subtitle or "",
                    "description": w.description or "",
                    "access_mode": w.access_mode,
                    "is_featured": w.is_featured,
                    "estimated_total_minutes": w.estimated_total_minutes,
                    "tags": _collect_workflow_tags(w),
                    "content_unlocked": unlocked,
                    "locked_reason": _locked_reason(user, w, unlocked),
                },
            )
        return Response({"results": results, "count": len(results)})


class PracticeWorkflowDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        try:
            workflow = PracticeWorkflow.objects.prefetch_related(
                Prefetch(
                    "steps",
                    queryset=PracticeWorkflowStep.objects.order_by(
                        "sequence",
                    ).prefetch_related("tags"),
                ),
            ).get(slug=slug, is_published=True)
        except PracticeWorkflow.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Workflow not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        user = _resolve_request_user(request)
        unlocked = _workflow_content_unlocked(user, workflow)
        enr = _active_workflow_enrollment(user, workflow) if user else None
        steps_qs = list(workflow.steps.all())
        return Response(
            {
                "slug": workflow.slug,
                "title": workflow.title,
                "subtitle": workflow.subtitle or "",
                "description": workflow.description or "",
                "philosophy_blurb": workflow.philosophy_blurb or "",
                "access_mode": workflow.access_mode,
                "is_featured": workflow.is_featured,
                "estimated_total_minutes": workflow.estimated_total_minutes,
                "purchase_notes": workflow.purchase_notes or "",
                "purchase_currency_options": purchase_currency_options(workflow),
                "tags": _collect_workflow_tags(workflow),
                "content_unlocked": unlocked,
                "locked_reason": _locked_reason(user, workflow, unlocked),
                "has_active_enrollment": bool(enr),
                "access_starts_at": enr.access_starts_at.isoformat() if enr else None,
                "access_ends_at": enr.access_ends_at.isoformat() if enr and enr.access_ends_at else None,
                "steps": [_workflow_step_full(s) for s in steps_qs] if unlocked else [],
                "step_outline": (
                    [_workflow_step_outline(s) for s in steps_qs] if not unlocked else []
                ),
            },
        )


class PracticeWorkflowMeView(APIView):
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
        for enr in PracticeWorkflowEnrollment.objects.filter(user=user).select_related(
            "workflow",
            "billing_record",
        ):
            if enr.access_starts_at > now:
                continue
            if enr.access_ends_at is not None and enr.access_ends_at < now:
                continue
            if enr.billing_record_id and not _billing_grants_access(enr.billing_record):
                continue
            rows.append(
                {
                    "workflow_slug": enr.workflow.slug,
                    "title": enr.workflow.title,
                    "access_starts_at": enr.access_starts_at.isoformat(),
                    "access_ends_at": (
                        enr.access_ends_at.isoformat() if enr.access_ends_at else None
                    ),
                },
            )
        return Response({"enrollments": rows})
