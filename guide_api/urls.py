"""API route table for guide endpoints."""

from django.urls import path

from guide_api.views import (
    AskView,
    ChatUIView,
    ConversationHistoryView,
    DailyVerseView,
    EngagementProfileView,
    FeedbackView,
    FollowUpGenerateView,
    HealthView,
    LoginView,
    LogoutView,
    MeView,
    PlanUpdateView,
    RegisterView,
    RetrievalEvalView,
    SavedReflectionDetailView,
    SavedReflectionListCreateView,
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
        "eval/retrieval/",
        RetrievalEvalView.as_view(),
        name="eval-retrieval",
    ),
    path("daily-verse/", DailyVerseView.as_view(), name="daily-verse"),
    path("history/me/", ConversationHistoryView.as_view(), {"user_id": "me"}),
    path(
        "history/<str:user_id>/",
        ConversationHistoryView.as_view(),
        name="history",
    ),
    path("feedback/", FeedbackView.as_view(), name="feedback"),
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
]
