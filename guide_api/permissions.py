"""DRF permission classes for guide_api."""

from rest_framework.permissions import BasePermission

from guide_api.models import UserSubscription


class GitaBrowseAPIPermission(BasePermission):
    """Gate token-based access for data-heavy JSON routes.

    Used for chapter/verse browse and quote-art JSON endpoints. Browser
    clients use same-origin ``fetch`` without an ``Authorization`` header, so
    ``request.auth`` is unset and access is allowed for anonymous and session
    users.

    Clients that send ``Authorization: Token …`` must have Plus or Pro;
    Free-plan token calls are rejected to limit external API abuse.
    """

    message = (
        "This endpoint requires a Plus or Pro plan when using "
        "API token authentication."
    )

    def has_permission(self, request, view):
        if request.auth is None:
            return True
        subscription, _ = UserSubscription.objects.get_or_create(
            user=request.user,
            defaults={"plan": UserSubscription.PLAN_FREE},
        )
        return subscription.plan in {
            UserSubscription.PLAN_PLUS,
            UserSubscription.PLAN_PRO,
        }
