"""Public website routes for SEO landing pages."""

from django.urls import path

from guide_api.sadhana_views import PracticeHubView
from guide_api.staff_views import CourseStudioView, AdminAnalyticsDashboardView, BadAnswerReviewQueueView
from guide_api.views import (
    CommunityWallView,
    DeleteAccountPageView,
    PrivacyPolicyPageView,
    SEO_LANDING_PAGES,
    SharedAnswerPageView,
    SeoDailyVerseHubView,
    SeoLandingIndexView,
    SeoQuestionArchiveView,
    SeoLandingTopicView,
    robots_txt_view,
    sitemap_xml_view,
    ResetPasswordPageView,
)


urlpatterns = [
    path(
        "reset-password/",
        ResetPasswordPageView.as_view(),
        name="reset-password-page",
    ),
    path(
        "staff/course-studio/",
        CourseStudioView.as_view(),
        name="staff-course-studio",
    ),
    path(
        "staff/analytics/",
        AdminAnalyticsDashboardView.as_view(),
        name="staff-analytics",
    ),
    path(
        "staff/feedback/review-queue/",
        BadAnswerReviewQueueView.as_view(),
        name="staff-feedback-review-queue",
    ),
    path(
        "practice/",
        PracticeHubView.as_view(),
        name="practice-hub",
    ),
    path(
        "community/",
        CommunityWallView.as_view(),
        name="community-wall",
    ),
    path(
        "privacy-policy/",
        PrivacyPolicyPageView.as_view(),
        name="privacy-policy",
    ),
    path(
        "privacy/",
        PrivacyPolicyPageView.as_view(),
        name="privacy-policy-short",
    ),
    path(
        "delete-account/",
        DeleteAccountPageView.as_view(),
        name="delete-account",
    ),
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
    path(
        "daily-bhagavad-gita-verse/",
        SeoDailyVerseHubView.as_view(),
        name="seo-daily-verse-hub",
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
