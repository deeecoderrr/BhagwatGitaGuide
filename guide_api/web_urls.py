"""Public website routes for SEO landing pages."""

from django.urls import path

from guide_api.views import SeoLandingIndexView, SeoLandingTopicView


urlpatterns = [
    path("", SeoLandingIndexView.as_view(), name="seo-index"),
    path(
        "bhagavad-gita-for-anxiety/",
        SeoLandingTopicView.as_view(),
        {"slug": "bhagavad-gita-for-anxiety"},
        name="seo-anxiety",
    ),
    path(
        "bhagavad-gita-for-career-confusion/",
        SeoLandingTopicView.as_view(),
        {"slug": "bhagavad-gita-for-career-confusion"},
        name="seo-career",
    ),
    path(
        "bhagavad-gita-for-relationships/",
        SeoLandingTopicView.as_view(),
        {"slug": "bhagavad-gita-for-relationships"},
        name="seo-relationships",
    ),
]
