from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.support_chat.forms import NewThreadForm, ReplyForm
from apps.support_chat.models import SupportMessage, SupportThread
from apps.support_chat.notifications import notify_owner_new_user_message, notify_user_staff_reply


def _chat_enabled(request: HttpRequest) -> bool:
    from django.conf import settings

    return getattr(settings, "ITR_SUPPORT_CHAT_ENABLED", False)


def _require_chat_enabled(view_func):
    def wrapper(request, *args, **kwargs):
        if not _chat_enabled(request):
            raise Http404("Support chat is not available.")
        return view_func(request, *args, **kwargs)

    return wrapper


def _user_thread(request: HttpRequest, pk: int) -> SupportThread:
    return get_object_or_404(SupportThread, pk=pk, user=request.user)


def _staff_thread(pk: int) -> SupportThread:
    return get_object_or_404(
        SupportThread.objects.select_related("user"),
        pk=pk,
    )


def _mark_staff_messages_read(thread: SupportThread) -> None:
    SupportMessage.objects.filter(
        thread=thread,
        is_staff=True,
        read_by_user_at__isnull=True,
    ).update(read_by_user_at=timezone.now())


def _mark_user_messages_read(thread: SupportThread) -> None:
    SupportMessage.objects.filter(
        thread=thread,
        is_staff=False,
        read_by_staff_at__isnull=True,
    ).update(read_by_staff_at=timezone.now())


def _post_message(
    *,
    thread: SupportThread,
    sender,
    body: str,
    is_staff: bool,
) -> SupportMessage:
    msg = SupportMessage.objects.create(
        thread=thread,
        sender=sender,
        body=body,
        is_staff=is_staff,
    )
    thread.last_message_at = msg.created_at
    if is_staff:
        thread.status = SupportThread.STATUS_WAITING_USER
    else:
        thread.status = SupportThread.STATUS_WAITING_STAFF
    thread.save(update_fields=["last_message_at", "status", "updated_at"])
    return msg


def _log_chat_event(request: HttpRequest, event_type: str, **metadata) -> None:
    try:
        from apps.analytics.events import log_itr_funnel_event

        log_itr_funnel_event(request, event_type, metadata=metadata)
    except Exception:
        pass


@require_GET
@login_required
@_require_chat_enabled
def thread_list(request: HttpRequest) -> HttpResponse:
    threads = (
        SupportThread.objects.filter(user=request.user)
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__is_staff=True, messages__read_by_user_at__isnull=True),
            )
        )
        .order_by("-last_message_at", "-created_at")
    )
    _log_chat_event(request, "support_chat_open")
    return render(
        request,
        "support_chat/list.html",
        {
            "page_title": "Support chat — ITR Summary",
            "threads": threads,
        },
    )


@require_http_methods(["GET", "POST"])
@login_required
@_require_chat_enabled
def thread_new(request: HttpRequest) -> HttpResponse:
    initial = {}
    service_key = (request.GET.get("service") or "").strip()
    if service_key:
        initial["service"] = service_key
    subject = (request.GET.get("subject") or "").strip()
    if subject:
        initial["subject"] = subject[:200]

    if request.method == "POST":
        form = NewThreadForm(request.POST)
        if form.is_valid():
            thread = SupportThread.objects.create(
                user=request.user,
                subject=form.cleaned_data["subject"].strip(),
                service_key=form.cleaned_data.get("service") or "",
                status=SupportThread.STATUS_WAITING_STAFF,
            )
            msg = _post_message(
                thread=thread,
                sender=request.user,
                body=form.cleaned_data["body"].strip(),
                is_staff=False,
            )
            notify_owner_new_user_message(msg)
            _log_chat_event(request, "support_chat_message", thread_id=thread.pk, new_thread=True)
            messages.success(request, "Your conversation has started. We typically reply within 24 hours.")
            return redirect(reverse("support_chat:thread", kwargs={"pk": thread.pk}))
    else:
        form = NewThreadForm(initial=initial)

    return render(
        request,
        "support_chat/new.html",
        {
            "page_title": "New conversation — ITR Summary",
            "form": form,
        },
    )


@require_http_methods(["GET", "POST"])
@login_required
@_require_chat_enabled
def thread_detail(request: HttpRequest, pk: int) -> HttpResponse:
    thread = _user_thread(request, pk)
    _mark_staff_messages_read(thread)

    if request.method == "POST":
        form = ReplyForm(request.POST)
        if form.is_valid():
            msg = _post_message(
                thread=thread,
                sender=request.user,
                body=form.cleaned_data["body"],
                is_staff=False,
            )
            notify_owner_new_user_message(msg)
            _log_chat_event(request, "support_chat_message", thread_id=thread.pk)
            return redirect(reverse("support_chat:thread", kwargs={"pk": thread.pk}))
    else:
        form = ReplyForm()

    chat_messages = thread.messages.select_related("sender").order_by("created_at")
    return render(
        request,
        "support_chat/thread.html",
        {
            "page_title": f"{thread.subject} — Support chat",
            "thread": thread,
            "chat_messages": chat_messages,
            "reply_form": form,
            "poll_url": reverse("support_chat:thread_poll", kwargs={"pk": thread.pk}),
        },
    )


@require_GET
@login_required
@_require_chat_enabled
def thread_poll(request: HttpRequest, pk: int) -> HttpResponse:
    thread = _user_thread(request, pk)
    _mark_staff_messages_read(thread)
    chat_messages = thread.messages.select_related("sender").order_by("created_at")
    return render(
        request,
        "support_chat/_message_list.html",
        {
            "thread": thread,
            "chat_messages": chat_messages,
        },
    )


@require_GET
@staff_member_required
@_require_chat_enabled
def staff_inbox(request: HttpRequest) -> HttpResponse:
    threads = (
        SupportThread.objects.select_related("user")
        .exclude(status=SupportThread.STATUS_CLOSED)
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__is_staff=False, messages__read_by_staff_at__isnull=True),
            )
        )
        .order_by("-last_message_at", "-created_at")
    )
    return render(
        request,
        "support_chat/staff_inbox.html",
        {
            "page_title": "Staff inbox — ITR Support",
            "threads": threads,
        },
    )


@require_http_methods(["GET", "POST"])
@staff_member_required
@_require_chat_enabled
def staff_thread(request: HttpRequest, pk: int) -> HttpResponse:
    thread = _staff_thread(pk)
    _mark_user_messages_read(thread)

    if request.method == "POST":
        action = (request.POST.get("action") or "reply").strip()
        if action == "close":
            thread.status = SupportThread.STATUS_CLOSED
            thread.save(update_fields=["status", "updated_at"])
            messages.success(request, "Conversation closed.")
            return redirect(reverse("support_chat:staff_inbox"))

        form = ReplyForm(request.POST)
        if form.is_valid():
            msg = _post_message(
                thread=thread,
                sender=request.user,
                body=form.cleaned_data["body"],
                is_staff=True,
            )
            notify_user_staff_reply(msg)
            messages.success(request, "Reply sent.")
            return redirect(reverse("support_chat:staff_thread", kwargs={"pk": thread.pk}))
    else:
        form = ReplyForm()

    chat_messages = thread.messages.select_related("sender").order_by("created_at")
    return render(
        request,
        "support_chat/staff_thread.html",
        {
            "page_title": f"Staff: {thread.subject}",
            "thread": thread,
            "chat_messages": chat_messages,
            "reply_form": form,
        },
    )
