"""Public website routes for SEO landing pages."""

from django.urls import path

from guide_api.views import (
    SEO_LANDING_PAGES,
    SharedAnswerPageView,
    SeoLandingIndexView,
    SeoQuestionArchiveView,
    SeoLandingTopicView,
    robots_txt_view,
    sitemap_xml_view,
)


urlpatterns = [
    path("robots.txt", robots_txt_view, name="robots-txt"),
    path("sitemap.xml", sitemap_xml_view, name="sitemap-xml"),
    path(
        "share/<uuid:share_id>/<str:legacy_suffix>/",
        SharedAnswerPageView.as_view(),
        name="shared-answer-legacy",
    ),
    path(
        "share/<uuid:share_id>/",
        SharedAnswerPageView.as_view(),
        name="shared-answer",
    ),
    path("", SeoLandingIndexView.as_view(), name="seo-index"),
    path(
        "frequently-asked-bhagavad-gita-questions/",
        SeoQuestionArchiveView.as_view(),
        name="seo-question-archive",
    ),
]

urlpatterns += [
    path(
        f"{page['slug']}/",
        SeoLandingTopicView.as_view(),
        {"slug": page["slug"]},
        name=f"seo-{page['slug']}",
    )
    for page in SEO_LANDING_PAGES.values()
]
