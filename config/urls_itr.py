"""ITR Summary Generator routes, mounted under ITR_URL_PREFIX (e.g. /itr-computation/).

Auth uses root /accounts/ (see config.urls) so login is shared with the rest of the site.
"""
from django.urls import include, path

urlpatterns = [
    path("billing/", include("apps.billing.urls")),
    path("documents/", include("apps.documents.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("exports/", include("apps.exports.urls")),
    path("comments/", include("apps.comments.urls")),
    path("", include("apps.marketing.urls")),
]
