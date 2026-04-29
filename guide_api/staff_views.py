"""Staff-only tools (course preparation, etc.)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from datetime import timedelta

from guide_api.forms import SadhanaDayQuickForm, SadhanaProgramStudioForm
from guide_api.models import (
    AskEvent,
    GrowthEvent,
    SadhanaDay,
    SadhanaProgram,
    SadhanaStep,
    WebAudienceProfile,
)


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only authenticated staff users."""

    login_url = "/admin/login/"
    # Do not set raise_exception=True: it would make LoginRequiredMixin return 403
    # for anonymous users instead of redirecting to login (shared AccessMixin state).

    def test_func(self) -> bool:
        u = self.request.user
        return bool(u.is_authenticated and u.is_staff)


def _admin_change_url(instance) -> str:
    opts = instance._meta
    return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[instance.pk])


class AdminAnalyticsDashboardView(StaffRequiredMixin, View):
    """Staff-only visual dashboard for analytics."""
    
    template_name = "guide_api/staff_analytics_dashboard.html"

    def get(self, request):
        days = int(request.GET.get("days", 7))
        today = timezone.localdate()
        since = timezone.now() - timedelta(days=days - 1)

        ask_qs = AskEvent.objects.filter(created_at__gte=since)
        growth_qs = GrowthEvent.objects.filter(created_at__gte=since)

        daily_rows = []
        for offset in range(days):
            day = today - timedelta(days=(days - 1 - offset))
            day_ask_qs = ask_qs.filter(created_at__date=day)
            day_growth_qs = growth_qs.filter(created_at__date=day)
            landing_views = day_growth_qs.filter(
                event_type=GrowthEvent.EVENT_LANDING_VIEW,
            ).count()
            starter_clicks = day_growth_qs.filter(
                event_type=GrowthEvent.EVENT_STARTER_CLICK,
            ).count()
            ask_submits = day_growth_qs.filter(
                event_type=GrowthEvent.EVENT_ASK_SUBMIT,
            ).count()
            
            # Simple funnel math: landing -> starter -> submit
            daily_rows.append(
                {
                    "date": day,
                    "unique_visitors": WebAudienceProfile.objects.filter(
                        last_seen_at__date=day,
                    ).count(),
                    "queries_fired": day_ask_qs.count(),
                    "landing_views": landing_views,
                    "starter_clicks": starter_clicks,
                    "ask_submits": ask_submits,
                }
            )

        daily_rows.reverse() # Most recent first

        ctx = {
            "days": days,
            "daily_rows": daily_rows,
            "total_asks": ask_qs.count(),
            "total_growth_events": growth_qs.count(),
        }
        return render(request, self.template_name, ctx)


class CourseStudioView(StaffRequiredMixin, View):
    """
    Course preparation: program shell here; steps & media refined in Django admin.

    Recommended flow:
    1. Create course identity → save
    2. Add days (titles + summaries)
    3. Optional “Seed canonical steps” for each day → then paste audio/video URLs in admin
    4. Tick publish when ready
    """

    template_name = "guide_api/staff_course_studio.html"

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        if not request.user.is_staff:
            return HttpResponseForbidden()
        action = (request.POST.get("action") or "").strip()

        if action == "create_program":
            form = SadhanaProgramStudioForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(
                    request,
                    f"Course “{form.instance.title}” created. Add days next.",
                )
                return redirect(
                    f"{reverse('staff-course-studio')}?pk={form.instance.pk}",
                )
            messages.error(request, "Fix the highlighted fields.")
            ctx = self._context(request)
            ctx["new_program_form"] = form
            ctx["selected_program"] = None
            ctx["edit_program_form"] = None
            ctx["days_data"] = []
            ctx["day_quick_form"] = SadhanaDayQuickForm(initial={"day_number": 1})
            return render(request, self.template_name, ctx)

        if action == "save_program":
            program = get_object_or_404(SadhanaProgram, pk=request.POST.get("program_pk"))
            form = SadhanaProgramStudioForm(request.POST, instance=program)
            if form.is_valid():
                form.save()
                messages.success(request, "Saved.")
                return redirect(f"{reverse('staff-course-studio')}?pk={program.pk}")
            messages.error(request, "Could not save.")
            ctx = self._context(request, selected_program=program)
            ctx["edit_program_form"] = form
            return render(request, self.template_name, ctx)

        if action == "add_day":
            program = get_object_or_404(SadhanaProgram, pk=request.POST.get("program_pk"))
            form = SadhanaDayQuickForm(request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        day = form.save(commit=False)
                        day.program = program
                        max_n = program.days.aggregate(m=Max("day_number"))["m"]
                        if not day.day_number or day.day_number < 1:
                            day.day_number = (max_n or 0) + 1
                        day.save()
                except Exception:
                    messages.error(
                        request,
                        "That day number may already exist for this course.",
                    )
                    ctx = self._context(request, selected_program=program)
                    ctx["day_quick_form"] = form
                    return render(request, self.template_name, ctx)
                messages.success(
                    request,
                    f"Day {day.day_number} saved. Add steps in admin or seed placeholders.",
                )
                return redirect(f"{reverse('staff-course-studio')}?pk={program.pk}")
            messages.error(request, "Check day fields.")
            ctx = self._context(request, selected_program=program)
            ctx["day_quick_form"] = form
            return render(request, self.template_name, ctx)

        if action == "seed_day_steps":
            program = get_object_or_404(SadhanaProgram, pk=request.POST.get("program_pk"))
            day = get_object_or_404(
                SadhanaDay,
                pk=request.POST.get("day_pk"),
                program=program,
            )
            pairs = [
                (1, SadhanaStep.STEP_WARMUP_YOGA, "Warm-up"),
                (2, SadhanaStep.STEP_PRANAYAMA, "Prānāyāma"),
                (3, SadhanaStep.STEP_BHAKTI, "Bhakti / remembrance"),
                (4, SadhanaStep.STEP_MANTRA, "Mantra"),
                (5, SadhanaStep.STEP_INTEGRATION, "Living the mantra"),
            ]
            for seq, stype, title in pairs:
                SadhanaStep.objects.get_or_create(
                    day=day,
                    sequence=seq,
                    defaults={
                        "step_type": stype,
                        "title": title,
                        "instructions": "",
                    },
                )
            messages.success(
                request,
                "Five step slots created — edit in admin and add media URLs.",
            )
            return redirect(f"{reverse('staff-course-studio')}?pk={program.pk}")

        return redirect(reverse("staff-course-studio"))

    def _context(self, request, selected_program=None):
        programs = SadhanaProgram.objects.all().order_by("sort_order", "title")
        pk = request.GET.get("pk")
        program = selected_program
        if program is None and pk:
            program = SadhanaProgram.objects.filter(pk=pk).first()

        new_form = SadhanaProgramStudioForm()
        edit_form = SadhanaProgramStudioForm(instance=program) if program else None

        days_data = []
        next_day_hint = 1
        if program:
            qs = program.days.prefetch_related("steps").order_by("day_number")
            max_n = qs.aggregate(m=Max("day_number"))["m"]
            next_day_hint = (max_n or 0) + 1
            for d in qs:
                days_data.append(
                    {
                        "day": d,
                        "step_count": d.steps.count(),
                        "admin_url": _admin_change_url(d),
                    },
                )

        day_quick = SadhanaDayQuickForm(initial={"day_number": next_day_hint})

        return {
            "programs": programs,
            "selected_program": program,
            "new_program_form": new_form,
            "edit_program_form": edit_form,
            "days_data": days_data,
            "day_quick_form": day_quick,
            "next_day_hint": next_day_hint,
            "program_admin_url": _admin_change_url(program) if program else "",
            "step_types": SadhanaStep.STEP_CHOICES,
        }
