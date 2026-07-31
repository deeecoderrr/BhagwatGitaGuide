from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.db.models import Prefetch
from django.http import Http404, HttpRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from apps.comments.forms import CommentForm
from apps.comments.models import Comment
from apps.marketing.forms import AppointmentLeadForm
from apps.marketing.lead_email import send_appointment_lead_email
from apps.marketing.models import ServiceAppointmentLead
from apps.marketing.services_catalog import (
    CA_SERVICE_BY_KEY,
    ITR_FILING_SERVICES,
    SERVICE_PAGES,
    SERVICE_PAGE_SLUG_BY_KEY,
    services_by_category,
)
from apps.marketing.seo import (
    SEO_META_KEYWORDS,
    structured_data_json_ld,
    structured_data_pricing_json_ld,
)


def _appointment_form_for_request(
    request: HttpRequest,
    *,
    bound: AppointmentLeadForm | None = None,
    service_key: str = "",
) -> AppointmentLeadForm:
    if bound is not None:
        return bound
    key = (service_key or request.GET.get("service") or "").strip()
    return AppointmentLeadForm(service_key=key)


def _appointment_context(
    request: HttpRequest,
    *,
    appointment_form: AppointmentLeadForm | None = None,
    service_key: str = "",
    source_page: str = "home",
) -> dict:
    form = _appointment_form_for_request(
        request,
        bound=appointment_form,
        service_key=service_key,
    )
    if not form.is_bound and source_page != "home":
        form.fields["source_page"].initial = source_page
    return {
        "appointment_form": form,
        "ca_services_by_category": services_by_category(),
        "itr_filing_services": ITR_FILING_SERVICES,
        "service_page_slug_by_key": SERVICE_PAGE_SLUG_BY_KEY,
        "appointment_source_page": source_page,
    }


def _home_context(
    request: HttpRequest,
    *,
    appointment_form: AppointmentLeadForm | None = None,
) -> dict:
    site_url = request.build_absolute_uri("/").rstrip("/")
    canonical = request.build_absolute_uri(reverse("marketing:home"))
    page_title = (
        "ITR Computation & Income Tax Computation Summary PDF | From ₹20 Instant Export "
        "(ITR-1, ITR-2, ITR-3, ITR-4 JSON — India)"
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
        "ITR computation & income tax computation summary: import filed ITR-1, ITR-2, ITR-3, or "
        "ITR-4 JSON, review figures free, export a CA-style ITR summary PDF. "
        "Book CA help for ITR filing, GST, and MSME registration."
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
        **_appointment_context(request, appointment_form=appointment_form),
    }
    if itr_beta:
        from apps.documents.forms import ItrUploadForm

        ctx["beta_try_form"] = ItrUploadForm()
    return ctx


def _service_page_context(
    request: HttpRequest,
    page,
    *,
    appointment_form: AppointmentLeadForm | None = None,
) -> dict:
    svc = CA_SERVICE_BY_KEY[page.service_key]
    canonical = request.build_absolute_uri(
        reverse("marketing:service_page", kwargs={"slug": page.slug})
    )
    return {
        "page": page,
        "service": svc,
        "page_title": page.page_title,
        "meta_description": page.meta_description[:320],
        "canonical_url": canonical,
        "structured_data": None,
        **_appointment_context(
            request,
            appointment_form=appointment_form,
            service_key=page.service_key,
            source_page=page.slug,
        ),
    }


def _save_lead_and_notify(request: HttpRequest, form: AppointmentLeadForm) -> ServiceAppointmentLead:
    svc = CA_SERVICE_BY_KEY[form.cleaned_data["service"]]
    visitor_id = getattr(request, "audience_id", "") or ""
    source = (form.cleaned_data.get("source_page") or "home").strip()[:64]
    lead = ServiceAppointmentLead.objects.create(
        name=form.cleaned_data["name"].strip(),
        phone=form.cleaned_data["phone"].strip(),
        email=form.cleaned_data["email"].strip().lower(),
        service_key=svc.key,
        service_label=svc.label,
        assessment_year=(form.cleaned_data.get("assessment_year") or "").strip(),
        income_source=(form.cleaned_data.get("income_source") or "").strip(),
        notes=(form.cleaned_data.get("notes") or "").strip(),
        source_page=source or "home",
        visitor_id=visitor_id[:64],
    )
    lead.email_sent = send_appointment_lead_email(lead, form)
    lead.save(update_fields=["email_sent"])

    try:
        from apps.analytics.events import EVENT_APPOINTMENT_LEAD, log_itr_funnel_event

        log_itr_funnel_event(
            request,
            EVENT_APPOINTMENT_LEAD,
            metadata={"service": svc.key, "lead_id": lead.pk, "source": source},
        )
    except Exception:
        pass
    return lead


def _flash_lead_result(
    request: HttpRequest,
    lead: ServiceAppointmentLead,
    *,
    thread=None,
) -> None:
    from django.conf import settings

    if thread:
        messages.success(
            request,
            "Your request is saved — continue the conversation below. "
            "Our team typically replies within 24 hours.",
        )
        return

    chat_hint = ""
    if getattr(settings, "ITR_SUPPORT_CHAT_ENABLED", False):
        if request.user.is_authenticated:
            chat_hint = " Track updates in Support Chat."
        else:
            chat_hint = (
                " Sign in to open Support Chat and track this request in one thread."
            )

    if lead.email_sent:
        messages.success(
            request,
            "Thank you — we received your request. Our team will call or email you within 24 hours."
            + chat_hint,
        )
    else:
        messages.warning(
            request,
            "Your request was saved, but we could not send the alert email right now. "
            "We will still follow up using the details you provided.",
        )


def _redirect_after_book(source_page: str) -> str:
    if source_page and source_page in SERVICE_PAGES:
        return reverse("marketing:service_page", kwargs={"slug": source_page}) + "#book-appointment"
    return reverse("marketing:home") + "#book-appointment"


@require_GET
def home(request):
    return render(request, "marketing/home.html", _home_context(request))


@require_GET
def service_page(request, slug: str):
    page = SERVICE_PAGES.get(slug)
    if not page:
        raise Http404("Service not found")
    return render(
        request,
        "marketing/service_page.html",
        _service_page_context(request, page),
    )


@require_http_methods(["POST"])
def appointment_book(request):
    form = AppointmentLeadForm(request.POST)
    source_page = (request.POST.get("source_page") or "home").strip()
    is_service_page = source_page in SERVICE_PAGES

    if not form.is_valid():
        messages.error(request, "Please fix the errors in the appointment form.")
        if is_service_page:
            page = SERVICE_PAGES[source_page]
            return render(
                request,
                "marketing/service_page.html",
                _service_page_context(request, page, appointment_form=form),
                status=400,
            )
        return render(
            request,
            "marketing/home.html",
            _home_context(request, appointment_form=form),
            status=400,
        )

    lead = _save_lead_and_notify(request, form)
    thread = None
    if getattr(settings, "ITR_SUPPORT_CHAT_ENABLED", False) and request.user.is_authenticated:
        from apps.support_chat.lead_bridge import create_thread_from_lead

        thread = create_thread_from_lead(request.user, lead)
    _flash_lead_result(request, lead, thread=thread)
    if thread:
        return redirect(reverse("support_chat:thread", kwargs={"pk": thread.pk}))
    return redirect(_redirect_after_book(source_page))


@require_GET
def pricing(request):
    site_url = request.build_absolute_uri("/").rstrip("/")
    canonical = request.build_absolute_uri(request.path)
    itr_home_abs = request.build_absolute_uri(reverse("marketing:home"))
    from apps.billing.views import ITR_BUNDLES
    contact_email = getattr(
        settings, "ITR_CONTACT_EMAIL", "askbhagwatgitasupport@gmail.com"
    )
    pro_inr = ITR_BUNDLES["professional"]["amount_inr"]
    plan_status = None
    if request.user.is_authenticated:
        from apps.accounts.models import UserProfile
        from apps.accounts.services import get_plan_status
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        plan_status = get_plan_status(profile)
    ctx = {
        "plan_status": plan_status,
        "page_title": (
            "ITR Computation PDF Pricing — Income Tax Summary Exports | India"
        ),
        "meta_description": (
            "ITR computation PDF exports from ₹20 — Pay-as-you-go, Value pack, Essentials, or Professional plans. "
            "Filed ITR JSON (ITR-1, ITR-2, ITR-3, ITR-4). "
            "Free preview before pay. UPI, card, netbanking via Razorpay."
        ),
        "meta_keywords": SEO_META_KEYWORDS,
        "canonical_url": canonical,
        "pro_inr": pro_inr,
        "itr_bundles": ITR_BUNDLES,
        "contact_email": contact_email,
        "structured_data": structured_data_pricing_json_ld(
            site_url=site_url,
            page_url=canonical,
            pro_inr=pro_inr,
            itr_home_url=itr_home_abs,
        ),
    }
    return render(request, "marketing/pricing.html", ctx)
