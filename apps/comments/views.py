from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.comments.forms import CommentForm
from apps.comments.models import Comment


@require_http_methods(["POST"])
def post_comment(request):
    """Create a top-level comment or reply; works for logged-in and guest users."""
    form = CommentForm(request.POST)
    raw_slug = (request.POST.get("page_slug") or Comment.PAGE_HOME).strip()
    page_slug = raw_slug[:64] if raw_slug else Comment.PAGE_HOME

    redirect_to = reverse("marketing:home")

    if not form.is_valid():
        messages.error(request, "Could not post: check your message.")
        return HttpResponseRedirect(f"{redirect_to}?comments=open")

    # Guest users must provide a name
    is_authenticated = request.user.is_authenticated
    guest_name = form.cleaned_data.get("guest_name", "").strip()
    if not is_authenticated and not guest_name:
        messages.error(request, "Please enter your name to post a comment.")
        return HttpResponseRedirect(f"{redirect_to}?comments=open")

    parent = None
    pid = form.cleaned_data.get("parent_id")
    if pid:
        parent = get_object_or_404(Comment, pk=pid, page_slug=page_slug)

    Comment.objects.create(
        user=request.user if is_authenticated else None,
        guest_name=guest_name if not is_authenticated else "",
        page_slug=page_slug,
        parent=parent,
        body=form.cleaned_data["body"].strip(),
    )
    messages.success(request, "Posted.")
    return HttpResponseRedirect(f"{redirect_to}?comments=open")
