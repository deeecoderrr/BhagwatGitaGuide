"""API route table for guide endpoints."""

from django.urls import path

from guide_api.views import (
    AnalyticsEventIngestView,
    AnalyticsSummaryView,
    AskView,
    ChatUIView,
    ChapterDetailView,
    ChapterListView,
    ConversationHistoryView,
    CreateOrderView,
    DailyVerseView,
    EngagementProfileView,
    FeaturedQuotesView,
    FeedbackView,
    FollowUpGenerateView,
    HealthView,
    LoginView,
    LogoutView,
    MantraView,
    MeView,
    PlanUpdateView,
    QuoteArtStylesView,
    QuoteArtView,
    RazorpayWebhookView,
    RegisterView,
    RetrievalEvalView,
    SavedReflectionDetailView,
    SavedReflectionListCreateView,
    SupportRequestView,
    SubscriptionStatusView,
    VerifyPaymentView,
    VerseDetailView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/plan/", PlanUpdateView.as_view(), name="auth-plan"),
    path(
        "engagement/me/",
        EngagementProfileView.as_view(),
        name="engagement-me",
    ),
    path("ask/", AskView.as_view(), name="ask"),
    path("follow-ups/", FollowUpGenerateView.as_view(), name="follow-ups"),
    path(
        "analytics/events/",
        AnalyticsEventIngestView.as_view(),
        name="analytics-events",
    ),
    path(
        "analytics/summary/",
        AnalyticsSummaryView.as_view(),
        name="analytics-summary",
    ),
    path("mantra/", MantraView.as_view(), name="mantra"),
    # Quote art generation
    path("quote-art/styles/", QuoteArtStylesView.as_view(), name="quote-art-styles"),
    path("quote-art/generate/", QuoteArtView.as_view(), name="quote-art-generate"),
    path("quote-art/featured/", FeaturedQuotesView.as_view(), name="quote-art-featured"),
    path(
        "eval/retrieval/",
        RetrievalEvalView.as_view(),
        name="eval-retrieval",
    ),
    path("daily-verse/", DailyVerseView.as_view(), name="daily-verse"),
    # Chapter and verse browsing
    path("chapters/", ChapterListView.as_view(), name="chapters"),
    path(
        "chapters/<int:chapter_number>/",
        ChapterDetailView.as_view(),
        name="chapter-detail",
    ),
    path(
        "verses/<int:chapter>.<int:verse>/",
        VerseDetailView.as_view(),
        name="verse-detail",
    ),
    path("history/me/", ConversationHistoryView.as_view(), {"user_id": "me"}),
    path(
        "history/<str:user_id>/",
        ConversationHistoryView.as_view(),
        name="history",
    ),
    path("feedback/", FeedbackView.as_view(), name="feedback"),
    path("support/", SupportRequestView.as_view(), name="support"),
    path(
        "saved-reflections/",
        SavedReflectionListCreateView.as_view(),
        name="saved-reflections",
    ),
    path(
        "saved-reflections/<int:reflection_id>/",
        SavedReflectionDetailView.as_view(),
        name="saved-reflection-detail",
    ),
    path("chat-ui/", ChatUIView.as_view(), name="chat-ui"),
    # Payment / Subscription endpoints
    path("payments/create-order/", CreateOrderView.as_view(), name="create-order"),
    path("payments/verify/", VerifyPaymentView.as_view(), name="verify-payment"),
    path("payments/webhook/", RazorpayWebhookView.as_view(), name="razorpay-webhook"),
    path("subscription/status/", SubscriptionStatusView.as_view(), name="subscription-status"),
]
