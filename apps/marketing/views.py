from __future__ import annotations

from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.comments.forms import CommentForm
from apps.comments.models import Comment
from apps.marketing.seo import (
    SEO_META_KEYWORDS,
    structured_data_json_ld,
    structured_data_pricing_json_ld,
)


@require_GET
def home(request):
    site_url = request.build_absolute_uri("/").rstrip("/")
    canonical = request.build_absolute_uri(request.path)
    page_title = (
        "ITR Computation & Income Tax Computation Summary PDF | Free ITR Summary "
        "(ITR-1, ITR-3, ITR-4 JSON — India)"
    )
    comments_qs = (
        Comment.objects.filter(page_slug=Comment.PAGE_HOME, parent__isnull=True)
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "replies",
                queryset=Comment.objects.select_related("user").order_by(
                    "created_at"
                ),
            )
        )
        .order_by("-created_at")[:100]
    )
    meta_desc = (
        "ITR computation & income tax computation summary: import filed ITR-1, ITR-3, or "
        "ITR-4 JSON, review figures, export a CA-style ITR summary PDF for assessment-year "
        "workflows in India. Human review before export."
    )
    itr_beta = getattr(settings, "ITR_BETA_RELEASE", False)
    ctx = {
        "page_title": page_title,
        "meta_description": meta_desc[:320],
        "meta_keywords": SEO_META_KEYWORDS,
        "canonical_url": canonical,
        "structured_data": structured_data_json_ld(
            site_url=site_url,
            page_url=canonical,
            page_heading=page_title,
        ),
        "comments": comments_qs,
        "comment_form": CommentForm(),
        "comments_page_slug": Comment.PAGE_HOME,
        "itr_beta_release": itr_beta,
        "beta_try_form": None,
    }
    if itr_beta:
        from apps.documents.forms import ItrUploadForm

        ctx["beta_try_form"] = ItrUploadForm()
    return render(request, "marketing/home.html", ctx)


@require_GET
def pricing(request):
    site_url = request.build_absolute_uri("/").rstrip("/")
    canonical = request.build_absolute_uri(request.path)
    itr_home_abs = request.build_absolute_uri(reverse("marketing:home"))
    paise = int(getattr(settings, "PRO_PLAN_AMOUNT_PAISE", 49900))
    pro_inr = paise // 100
    ctx = {
        "page_title": (
            "ITR Computation PDF Pricing — Income Tax Summary Exports | India"
        ),
        "meta_description": (
            "Compare Free vs Pro for ITR computation PDF exports from filed ITR JSON "
            "(ITR-1, ITR-3, ITR-4). "
            "Income tax computation summary downloads for assessment-year workflows — Razorpay checkout."
        ),
        "meta_keywords": SEO_META_KEYWORDS,
        "canonical_url": canonical,
        "pro_inr": pro_inr,
        "structured_data": structured_data_pricing_json_ld(
            site_url=site_url,
            page_url=canonical,
            pro_inr=pro_inr,
            itr_home_url=itr_home_abs,
        ),
    }
    return render(request, "marketing/pricing.html", ctx)
