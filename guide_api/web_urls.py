"""Public website routes for SEO landing pages."""

from django.urls import path

from guide_api.sadhana_views import PracticeHubView
from guide_api.staff_views import CourseStudioView, AdminAnalyticsDashboardView, BadAnswerReviewQueueView
from guide_api.views import (
    AccountPageView,
    ChapterDetailPageView,
    CommunityWallView,
    DeleteAccountPageView,
    GratitudePageView,
    InsightsPageView,
    JapaPageView,
    MeditationPageView,
    MoodPageView,
    NotificationsPageView,
    PlansPageView,
    PrivacyPolicyPageView,
    QuoteArtPageView,
    ReadGitaPageView,
    ReadJourneyPageView,
    SadhanaPageView,
    SavedReflectionsPageView,
    SEO_LANDING_PAGES,
    SharedAnswerPageView,
    SeoDailyVerseHubView,
    SeoLandingIndexView,
    SeoQuestionArchiveView,
    SeoLandingTopicView,
    SupportPageView,
    TodayPageView,
    VerseDetailPageView,
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
    path("insights/", InsightsPageView.as_view(), name="insights"),
    path("japa/", JapaPageView.as_view(), name="japa"),
    path("plans/", PlansPageView.as_view(), name="plans"),
    path("account/", AccountPageView.as_view(), name="account"),
    path("saved-reflections/", SavedReflectionsPageView.as_view(), name="saved-reflections"),
    path("quote-art/", QuoteArtPageView.as_view(), name="quote-art"),
    path("sadhana/", SadhanaPageView.as_view(), name="sadhana"),
    path("read-gita/", ReadGitaPageView.as_view(), name="read-gita"),
    # New feature pages
    path("today/", TodayPageView.as_view(), name="today"),
    path("read-journey/", ReadJourneyPageView.as_view(), name="read-journey"),
    path("read/chapter/<int:chapter_number>/", ChapterDetailPageView.as_view(), name="chapter-detail"),
    path("read/<int:chapter_number>.<int:verse_number>/", VerseDetailPageView.as_view(), name="verse-detail"),
    path("mood/", MoodPageView.as_view(), name="mood"),
    path("gratitude/", GratitudePageView.as_view(), name="gratitude"),
    path("meditation/", MeditationPageView.as_view(), name="meditation"),
    path("support/", SupportPageView.as_view(), name="support"),
    path("notifications/", NotificationsPageView.as_view(), name="notifications"),
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
