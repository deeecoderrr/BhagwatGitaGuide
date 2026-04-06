import json
from datetime import timedelta
from tempfile import NamedTemporaryFile

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from guide_api.models import (
    AskEvent,
    Conversation,
    EngagementEvent,
    FollowUpEvent,
    Message,
    ResponseFeedback,
    SavedReflection,
    UserEngagementProfile,
    UserSubscription,
)
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase


@override_settings(DEBUG=True, OPENAI_API_KEY="")
class GuideApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo-user",
            password="demo-pass-123",
        )
        self.client.force_authenticate(user=self.user)

    def _login_chat_ui(self, username="demo-user", password="demo-pass-123"):
        """Authenticate the manual chat UI with a browser session."""
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "login",
                "login_username": username,
                "login_password": password,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def test_health_endpoint(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")

    def test_health_endpoint_v1_alias_works(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")

    def test_auth_register_creates_user_and_token(self):
        self.client.force_authenticate(user=None)
        payload = {
            "username": "new-user",
            "password": "new-pass-123",
        }
        response = self.client.post(
            "/api/auth/register/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["username"], "new-user")

    def test_auth_login_returns_token_and_me_works(self):
        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            "/api/auth/login/",
            {
                "username": "demo-user",
                "password": "demo-pass-123",
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        token = login_response.data["token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        me_response = self.client.get("/api/auth/me/")
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["username"], "demo-user")

    def test_auth_logout_invalidates_token(self):
        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            "/api/auth/login/",
            {
                "username": "demo-user",
                "password": "demo-pass-123",
            },
            format="json",
        )
        token = login_response.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

        logout_response = self.client.post(
            "/api/auth/logout/",
            {},
            format="json",
        )
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        me_response = self.client.get("/api/auth/me/")
        self.assertIn(
            me_response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_auth_plan_update_switches_plan(self):
        response = self.client.post(
            "/api/auth/plan/",
            {"plan": "pro"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"], "pro")

    def test_ask_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)
        payload = {
            "message": "I feel anxious about my career growth.",
            "mode": "simple",
        }
        response = self.client.post("/api/ask/", payload, format="json")
        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    @override_settings(ASK_LIMIT_FREE_DAILY=2)
    def test_ask_endpoint_enforces_free_plan_daily_limit(self):
        payload = {
            "message": "I feel anxious about my career growth.",
            "mode": "simple",
        }
        first = self.client.post("/api/ask/", payload, format="json")
        second = self.client.post("/api/ask/", payload, format="json")
        third = self.client.post("/api/ask/", payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(third.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(third.data["plan"], "free")
        self.assertEqual(
            AskEvent.objects.filter(
                source=AskEvent.SOURCE_API,
                outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
            ).count(),
            1,
        )

    @override_settings(ASK_LIMIT_FREE_DAILY=2, ASK_LIMIT_PRO_DAILY=5)
    def test_ask_endpoint_pro_plan_gets_higher_daily_limit(self):
        subscription, _ = UserSubscription.objects.get_or_create(
            user=self.user,
        )
        subscription.plan = UserSubscription.PLAN_PRO
        subscription.save(update_fields=["plan"])
        payload = {
            "message": "I feel anxious about my career growth.",
            "mode": "simple",
        }

        for _ in range(3):
            response = self.client.post("/api/ask/", payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["plan"], "pro")

    def test_auth_me_includes_plan_and_quota_fields(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("plan", response.data)
        self.assertIn("daily_limit", response.data)
        self.assertIn("used_today", response.data)
        self.assertIn("remaining_today", response.data)
        self.assertIn("engagement", response.data)

    def test_engagement_me_get_returns_defaults(self):
        response = self.client.get("/api/engagement/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["daily_streak"], 0)
        self.assertEqual(response.data["preferred_channel"], "none")
        self.assertEqual(response.data["timezone"], "UTC")

    def test_engagement_me_patch_updates_preferences(self):
        response = self.client.patch(
            "/api/engagement/me/",
            {
                "reminder_enabled": True,
                "reminder_time": "08:30:00",
                "preferred_channel": "push",
                "timezone": "Asia/Kolkata",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["reminder_enabled"])
        self.assertEqual(response.data["preferred_channel"], "push")
        self.assertEqual(response.data["timezone"], "Asia/Kolkata")
        self.assertEqual(
            EngagementEvent.objects.filter(
                event_type=EngagementEvent.EVENT_REMINDER_PREF_UPDATED,
            ).count(),
            1,
        )

    def test_ask_endpoint_creates_response(self):
        payload = {
            "message": "I feel anxious about my career growth.",
            "mode": "simple",
        }
        response = self.client.post("/api/ask/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("guidance", response.data)
        self.assertTrue(len(response.data["verses"]) >= 1)
        self.assertIn("response_mode", response.data)
        self.assertIn(response.data["response_mode"], {"llm", "fallback"})
        self.assertIn(
            response.data["retrieval_mode"],
            {"semantic", "hybrid", "hybrid_fallback", "curated_fallback"},
        )
        self.assertIn("retrieval_scores", response.data)
        self.assertIn("retrieved_references", response.data)
        self.assertIn("follow_ups", response.data)
        self.assertIn("engagement", response.data)
        self.assertEqual(response.data["engagement"]["daily_streak"], 1)
        self.assertTrue(len(response.data["follow_ups"]) >= 2)
        self.assertEqual(
            AskEvent.objects.filter(
                source=AskEvent.SOURCE_API,
                outcome=AskEvent.OUTCOME_SERVED,
            ).count(),
            1,
        )

    def test_ask_endpoint_supports_hindi_language(self):
        response = self.client.post(
            "/api/ask/",
            {
                "message": "मुझे करियर को लेकर चिंता हो रही है।",
                "mode": "simple",
                "language": "hi",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["language"], "hi")
        self.assertTrue(
            any("\u0900" <= ch <= "\u097F" for ch in response.data["guidance"])
        )
        self.assertEqual(
            FollowUpEvent.objects.filter(
                source=FollowUpEvent.SOURCE_API,
                event_type=FollowUpEvent.EVENT_SHOWN,
            ).count(),
            len(response.data["follow_ups"]),
        )

    def test_follow_ups_endpoint_returns_contextual_prompts(self):
        response = self.client.post(
            "/api/follow-ups/",
            {
                "message": "I feel anxious about my career growth.",
                "mode": "simple",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("follow_ups", response.data)
        self.assertTrue(len(response.data["follow_ups"]) >= 2)
        first = response.data["follow_ups"][0]
        self.assertIn("label", first)
        self.assertIn("prompt", first)
        self.assertIn("intent", first)

    def test_ask_endpoint_increments_streak_from_previous_day(self):
        profile = UserEngagementProfile.objects.create(
            user=self.user,
            daily_streak=2,
            last_active_date=timezone.localdate() - timedelta(days=1),
        )
        response = self.client.post(
            "/api/ask/",
            {
                "message": "I feel anxious about my career growth.",
                "mode": "simple",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.daily_streak, 3)

    def test_ask_endpoint_blocks_risky_prompt(self):
        payload = {
            "message": "Should I stop medication today?",
            "mode": "simple",
        }
        response = self.client.post("/api/ask/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "safety_blocked")
        self.assertEqual(
            AskEvent.objects.filter(
                source=AskEvent.SOURCE_API,
                outcome=AskEvent.OUTCOME_BLOCKED_SAFETY,
            ).count(),
            1,
        )

    def test_retrieval_eval_endpoint_returns_trace(self):
        payload = {
            "message": "I get angry quickly with my family",
            "mode": "simple",
        }
        response = self.client.post(
            "/api/eval/retrieval/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("retrieval_mode", response.data)
        self.assertIn("retrieval_scores", response.data)
        self.assertIn("retrieved_references", response.data)
        self.assertIn("query_themes", response.data)
        self.assertIn("query_tokens", response.data)

    def test_retrieval_eval_benchmark_returns_both_modes(self):
        payload = {
            "message": "I am anxious about career growth and performance",
            "mode": "benchmark",
        }
        response = self.client.post(
            "/api/eval/retrieval/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "benchmark")
        self.assertIn("semantic", response.data)
        self.assertIn("hybrid", response.data)
        self.assertIn("retrieval_mode", response.data["semantic"])
        self.assertIn("retrieval_mode", response.data["hybrid"])

    def test_chat_ui_page_loads(self):
        response = self.client.get("/api/chat-ui/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Try a starter prompt")
        self.assertContains(response, "Account")
        self.assertContains(response, "Register")
        self.assertContains(response, "Login")

    def test_chat_ui_register_and_logout_flow(self):
        register_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "register",
                "register_username": "ui-user",
                "register_password": "ui-pass-123",
            },
        )
        self.assertEqual(register_response.status_code, status.HTTP_200_OK)
        self.assertContains(
            register_response,
            "Registered and logged in as ui-user",
        )

        logout_response = self.client.post(
            "/api/chat-ui/",
            data={"action": "logout"},
        )
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertContains(logout_response, "Logged out.")

    def test_chat_ui_login_immediately_loads_users_own_conversation_list(self):
        other_user = User.objects.create_user(
            username="other-user",
            password="other-pass-123",
        )
        other_conversation = Conversation.objects.create(
            user_id=other_user.username,
        )
        Message.objects.create(
            conversation=other_conversation,
            role=Message.ROLE_USER,
            content="Other user's thread",
        )
        own_conversation = Conversation.objects.create(user_id=self.user.username)
        Message.objects.create(
            conversation=own_conversation,
            role=Message.ROLE_USER,
            content="My saved thread",
        )

        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "login",
                "login_username": "demo-user",
                "login_password": "demo-pass-123",
            },
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertContains(login_response, "Logged in as demo-user.")
        self.assertEqual(len(login_response.context["conversations"]), 1)
        self.assertEqual(
            login_response.context["conversations"][0]["title"],
            "My saved thread",
        )
        self.assertContains(login_response, "Conversations")
        self.assertNotContains(login_response, "Other user's thread")

    def test_chat_ui_renders_structured_response_sections(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Meaning")
        self.assertContains(response, "Actions")
        self.assertContains(response, "Reflection")
        self.assertContains(response, "Verses Used")
        self.assertContains(response, "Continue the conversation")
        self.assertEqual(
            AskEvent.objects.filter(
                source=AskEvent.SOURCE_CHAT_UI,
                outcome=AskEvent.OUTCOME_SERVED,
            ).count(),
            1,
        )
        self.assertContains(response, "Conversation")
        self.assertContains(response, "You")
        self.assertContains(response, "Guide")
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(response.context["conversations"], [])
        self.assertContains(response, "Temporary guest reply")
        # Composer is now at the bottom with "Send" button
        self.assertContains(response, "Send")

    def test_chat_ui_continues_existing_conversation_when_id_is_posted(self):
        self._login_chat_ui()
        first = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        conversation_id = first.context["response_data"]["conversation_id"]

        second = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "conversation_id": str(conversation_id),
                "message": "Give me one step for today.",
            },
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertContains(second, "Give me one step for today.")
        self.assertEqual(
            len(second.context["conversation_messages"]),
            4,
        )

    def test_chat_ui_new_query_resets_visible_conversation(self):
        self.client.force_authenticate(user=None)
        self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )

        reset = self.client.get("/api/chat-ui/?new=1")
        self.assertEqual(reset.status_code, status.HTTP_200_OK)
        self.assertEqual(reset.context["active_conversation_id"], "")
        self.assertEqual(reset.context["conversation_messages"], [])
        self.assertNotContains(reset, "Start New</a>")
        self.assertEqual(len(reset.context["conversations"]), 0)

    def test_chat_ui_guest_chat_stays_temporary_in_session(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(response.context["active_conversation_id"], "")
        self.assertContains(response, "Guest chat is temporary")

    def test_chat_ui_new_conversation_creates_separate_thread(self):
        self._login_chat_ui()
        first = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        first_conversation_id = first.context["response_data"]["conversation_id"]

        second = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "conversation_id": "",
                "message": "I get angry quickly in relationships.",
            },
        )
        second_conversation_id = second.context["response_data"]["conversation_id"]

        self.assertNotEqual(first_conversation_id, second_conversation_id)
        self.assertContains(second, "Conversations")
        self.assertEqual(len(second.context["conversations"]), 2)
        self.assertContains(second, "Updated just now")

    def test_chat_ui_sidebar_shows_thread_metadata(self):
        self._login_chat_ui()
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conversation = response.context["conversations"][0]
        self.assertEqual(
            conversation["title"],
            "I feel anxious about my career growth.",
        )
        self.assertEqual(conversation["message_count_label"], "2 messages")
        self.assertContains(response, "Updated just now")
        self.assertContains(response, "Delete")

    def test_chat_ui_can_open_specific_older_conversation(self):
        self._login_chat_ui()
        first = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        first_conversation_id = first.context["response_data"]["conversation_id"]

        self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "conversation_id": "",
                "message": "I feel stuck and directionless.",
            },
        )

        response = self.client.get(
            f"/api/chat-ui/?conversation_id={first_conversation_id}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.context["active_conversation_id"],
            first_conversation_id,
        )
        self.assertContains(response, "I feel anxious about my career growth.")

    def test_chat_ui_can_delete_active_conversation(self):
        self._login_chat_ui()
        created = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        conversation_id = created.context["response_data"]["conversation_id"]

        deleted = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "delete_conversation",
                "conversation_id": str(conversation_id),
                "active_conversation_id": str(conversation_id),
            },
        )
        self.assertEqual(deleted.status_code, status.HTTP_200_OK)
        self.assertContains(deleted, "Conversation deleted.")
        self.assertEqual(deleted.context["active_conversation_id"], "")
        self.assertEqual(deleted.context["conversation_messages"], [])
        self.assertEqual(len(deleted.context["conversations"]), 0)

    def test_chat_ui_plan_update_for_existing_username(self):
        self._login_chat_ui()
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "plan",
                "selected_plan": "pro",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Plan updated to pro")

    @override_settings(ASK_LIMIT_FREE_DAILY=1)
    def test_chat_ui_enforces_quota_for_existing_username(self):
        self._login_chat_ui()
        first = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about career growth.",
            },
        )
        second = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about career growth.",
            },
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertContains(second, "Daily ask limit reached")

    def test_chat_ui_tracks_recent_questions_up_to_three(self):
        self.client.force_authenticate(user=None)
        for idx in range(1, 5):
            self.client.post(
                "/api/chat-ui/",
                data={
                    "action": "ask",
                    "mode": "simple",
                    "message": f"recent question {idx}",
                },
            )
        response = self.client.get("/api/chat-ui/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Recent questions")
        self.assertContains(response, "recent question 4")
        self.assertContains(response, "recent question 3")
        self.assertContains(response, "recent question 2")

    def test_chat_ui_logged_in_user_only_sees_own_history(self):
        other_user = User.objects.create_user(
            username="other-user",
            password="other-pass-123",
        )
        other_conversation = Conversation.objects.create(
            user_id=other_user.username,
        )
        Message.objects.create(
            conversation=other_conversation,
            role=Message.ROLE_USER,
            content="Other user's thread",
        )
        own_conversation = Conversation.objects.create(user_id=self.user.username)
        Message.objects.create(
            conversation=own_conversation,
            role=Message.ROLE_USER,
            content="My own thread",
        )

        self._login_chat_ui()
        response = self.client.get("/api/chat-ui/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [item["title"] for item in response.context["conversations"]]
        self.assertIn("My own thread", titles)
        self.assertNotIn("Other user's thread", titles)

    def test_chat_ui_mode_selection_persists_across_threads(self):
        self._login_chat_ui()
        selected = self.client.get("/api/chat-ui/?mode=deep")
        self.assertEqual(selected.status_code, status.HTTP_200_OK)
        self.assertEqual(selected.context["mode"], "deep")

        asked = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "deep",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(asked.status_code, status.HTTP_200_OK)
        self.assertEqual(asked.context["mode"], "deep")
        conversation_id = asked.context["response_data"]["conversation_id"]

        reopened = self.client.get(
            f"/api/chat-ui/?conversation_id={conversation_id}&mode=deep",
        )
        self.assertEqual(reopened.status_code, status.HTTP_200_OK)
        self.assertEqual(reopened.context["mode"], "deep")

    def test_chat_ui_language_selection_persists_across_threads(self):
        self._login_chat_ui()
        selected = self.client.get("/api/chat-ui/?language=hi")
        self.assertEqual(selected.status_code, status.HTTP_200_OK)
        self.assertEqual(selected.context["language"], "hi")

        asked = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "language": "hi",
                "message": "मुझे चिंता हो रही है।",
            },
        )
        self.assertEqual(asked.status_code, status.HTTP_200_OK)
        self.assertEqual(asked.context["language"], "hi")
        self.assertEqual(asked.context["response_data"]["language"], "hi")

    def test_chat_ui_language_switch_keeps_conversation_sidebar(self):
        self._login_chat_ui()
        self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "language": "en",
                "message": "I feel anxious.",
            },
        )
        switched = self.client.get("/api/chat-ui/?language=hi")
        self.assertEqual(switched.status_code, status.HTTP_200_OK)
        self.assertEqual(switched.context["language"], "hi")
        self.assertTrue(len(switched.context["conversations"]) >= 1)

    def test_feedback_api_saves_entry(self):
        payload = {
            "message": "This helped me think clearly.",
            "mode": "simple",
            "response_mode": "llm",
            "helpful": True,
            "note": "Clear and practical",
        }
        response = self.client.post("/api/feedback/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ResponseFeedback.objects.count(), 1)

    def test_feedback_list_supports_limit_offset(self):
        for idx in range(3):
            self.client.post(
                "/api/feedback/",
                {
                    "message": f"feedback {idx}",
                    "mode": "simple",
                    "response_mode": "fallback",
                    "helpful": True,
                },
                format="json",
            )
        response = self.client.get("/api/feedback/?limit=2&offset=1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["limit"], 2)
        self.assertEqual(response.data["offset"], 1)
        self.assertEqual(len(response.data["results"]), 2)

    def test_saved_reflections_api_create_list_delete(self):
        create_response = self.client.post(
            "/api/saved-reflections/",
            {
                "message": "I am anxious about career growth.",
                "guidance": "Do your duty without attachment.",
                "meaning": "Focus on effort.",
                "actions": ["Work consistently", "Let go of outcome anxiety"],
                "reflection": "What can I control today?",
                "verse_references": ["2.47", "3.19"],
                "note": "Daily reminder",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        saved_id = create_response.data["id"]

        list_response = self.client.get("/api/saved-reflections/")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(list_response.data["results"][0]["id"], saved_id)

        delete_response = self.client.delete(
            f"/api/saved-reflections/{saved_id}/"
        )
        self.assertEqual(
            delete_response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertEqual(SavedReflection.objects.count(), 0)

    def test_saved_reflections_supports_limit_offset(self):
        for idx in range(3):
            self.client.post(
                "/api/saved-reflections/",
                {
                    "message": f"saved {idx}",
                    "guidance": "do your duty",
                },
                format="json",
            )
        response = self.client.get("/api/saved-reflections/?limit=2&offset=1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["limit"], 2)
        self.assertEqual(response.data["offset"], 1)
        self.assertEqual(len(response.data["results"]), 2)

    def test_saved_reflections_delete_blocks_other_user(self):
        entry = SavedReflection.objects.create(
            user=self.user,
            message="Saved one",
            guidance="Guidance",
        )
        other_user = User.objects.create_user(
            username="other-user",
            password="other-pass-123",
        )
        self.client.force_authenticate(user=other_user)
        response = self.client.delete(f"/api/saved-reflections/{entry.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error"]["code"],
            "saved_reflection_not_found",
        )

    def test_chat_ui_feedback_flow(self):
        self._login_chat_ui()
        ask_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(ask_response.status_code, status.HTTP_200_OK)
        self.assertEqual(ResponseFeedback.objects.count(), 0)
        conversation_id = ask_response.context["response_data"]["conversation_id"]

        feedback_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "feedback",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
                "helpful": "true",
                "response_mode": "fallback",
                "conversation_id": str(conversation_id),
                "note": "Useful",
            },
        )
        self.assertEqual(feedback_response.status_code, status.HTTP_200_OK)
        self.assertEqual(ResponseFeedback.objects.count(), 1)

    def test_chat_ui_save_reflection_flow(self):
        self._login_chat_ui()
        ask_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(ask_response.status_code, status.HTTP_200_OK)
        conversation_id = ask_response.context["response_data"]["conversation_id"]

        save_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "save",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
                "conversation_id": str(conversation_id),
                "guidance": "Do your duty without attachment.",
                "meaning": "Focus on effort.",
                "actions": "Work consistently|Let go of outcome anxiety",
                "reflection": "What can I control today?",
                "verse_references": "2.47|3.19",
                "note": "Saved from chat ui",
            },
        )
        self.assertEqual(save_response.status_code, status.HTTP_200_OK)
        self.assertContains(save_response, "Reflection saved.")
        self.assertEqual(SavedReflection.objects.count(), 1)

    def test_ask_endpoint_returns_anger_relevant_verses(self):
        payload = {
            "message": "I get angry quickly with my family.",
            "mode": "simple",
        }
        response = self.client.post("/api/ask/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        themes = [
            theme
            for verse in response.data["verses"]
            for theme in verse["themes"]
        ]
        self.assertIn("anger", themes)

    def test_history_endpoint_blocks_other_user_access(self):
        self.client.post(
            "/api/ask/",
            {
                "message": "I am feeling uncertain in my work.",
                "mode": "simple",
            },
            format="json",
        )
        response = self.client.get("/api/history/another-user/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_import_gita_command_upserts_rows(self):
        dataset = [
            {
                "chapter": 1,
                "verse": 1,
                "translation": "First translation",
                "commentary": "first commentary",
                "themes": ["context"],
            },
            {
                "chapter": 1,
                "verse": 1,
                "translation": "Updated translation",
                "commentary": "updated commentary",
                "themes": ["updated"],
            },
            {
                "chapter": 1,
                "verse": 2,
                "translation": "Second translation",
                "themes": ["focus"],
            },
        ]
        with NamedTemporaryFile(mode="w+", suffix=".json") as temp_file:
            json.dump(dataset, temp_file)
            temp_file.flush()
            call_command("import_gita", file=temp_file.name)

        from guide_api.models import Verse

        self.assertEqual(Verse.objects.filter(chapter=1).count(), 2)
        updated = Verse.objects.get(chapter=1, verse=1)
        self.assertEqual(updated.translation, "Updated translation")

    def test_import_gita_command_strict_mode_raises_on_invalid_row(self):
        dataset = [
            {"chapter": 1, "verse": 1, "translation": "ok"},
            {"chapter": "x", "verse": 2, "translation": "invalid"},
        ]
        with NamedTemporaryFile(mode="w+", suffix=".json") as temp_file:
            json.dump(dataset, temp_file)
            temp_file.flush()
            with self.assertRaises(CommandError):
                call_command("import_gita", file=temp_file.name, strict=True)

    def test_tag_gita_themes_command_updates_themes(self):
        from guide_api.models import Verse

        verse = Verse.objects.create(
            chapter=9,
            verse=1,
            translation="I feel anxiety and fear in my job and family life.",
            commentary="Stay disciplined and reduce anger.",
            themes=[],
        )
        call_command("tag_gita_themes")
        verse.refresh_from_db()
        self.assertIn("anxiety", verse.themes)
        self.assertIn("career", verse.themes)
        self.assertIn("relationships", verse.themes)

    def test_tag_gita_themes_dry_run_does_not_write(self):
        from guide_api.models import Verse

        verse = Verse.objects.create(
            chapter=9,
            verse=2,
            translation="Anxiety and overthinking reduce focus.",
            commentary="",
            themes=[],
        )
        call_command("tag_gita_themes", dry_run=True)
        verse.refresh_from_db()
        self.assertEqual(verse.themes, [])

    def test_embed_gita_verses_requires_openai_key(self):
        with self.assertRaises(CommandError):
            call_command("embed_gita_verses")

    def test_eval_retrieval_command_reports_summary(self):
        from guide_api.models import Verse

        Verse.objects.create(
            chapter=99,
            verse=1,
            translation="xyzzylife token for eval hit",
            commentary="",
            themes=["purpose"],
        )
        dataset = [
            {
                "prompt": "xyzzylife token for eval hit",
                "expected_references": ["99.1"],
            },
            {
                "prompt": "xyzzylife token for eval hit",
                "expected_references": ["1.999"],
            },
        ]
        with NamedTemporaryFile(mode="w+", suffix=".json") as temp_file:
            json.dump(dataset, temp_file)
            temp_file.flush()
            from io import StringIO

            out = StringIO()
            call_command(
                "eval_retrieval",
                file=temp_file.name,
                mode="hybrid",
                stdout=out,
            )
            result = out.getvalue()

        self.assertIn("Retrieval eval complete.", result)
        self.assertIn("cases=2", result)
        self.assertIn("hits=1", result)
        self.assertIn("misses=1", result)

    def test_eval_retrieval_command_strict_raises_on_miss(self):
        dataset = [
            {
                "prompt": "career anxiety",
                "expected_references": ["1.999"],
            },
        ]
        with NamedTemporaryFile(mode="w+", suffix=".json") as temp_file:
            json.dump(dataset, temp_file)
            temp_file.flush()
            with self.assertRaises(CommandError):
                call_command(
                    "eval_retrieval",
                    file=temp_file.name,
                    mode="hybrid",
                    strict=True,
                )

    def test_eval_retrieval_command_reports_miss_clusters(self):
        dataset = [
            {
                "prompt": "I feel anxious about my career growth",
                "expected_references": ["1.999"],
            },
        ]
        with NamedTemporaryFile(mode="w+", suffix=".json") as temp_file:
            json.dump(dataset, temp_file)
            temp_file.flush()
            from io import StringIO

            out = StringIO()
            call_command(
                "eval_retrieval",
                file=temp_file.name,
                mode="hybrid",
                report_misses=True,
                stdout=out,
            )
            result = out.getvalue()

        self.assertIn("Miss report:", result)
        self.assertIn("themes:", result)
        self.assertIn("top_missing_refs:", result)

    def test_chapters_list_returns_chapters(self):
        """Test chapter listing endpoint returns all chapters."""
        response = self.client.get("/api/chapters/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("chapters", response.data)
        self.assertIn("total", response.data)
        # Should have 18 chapters if data is loaded
        if response.data["total"] > 0:
            first = response.data["chapters"][0]
            self.assertIn("chapter_number", first)
            self.assertIn("name", first)
            self.assertIn("verses_count", first)

    def test_chapter_detail_returns_chapter_and_verses(self):
        """Test chapter detail endpoint returns chapter info and verse list."""
        response = self.client.get("/api/chapters/2/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("chapter", response.data)
        self.assertIn("verses", response.data)

    def test_chapter_detail_404_for_invalid_chapter(self):
        """Test chapter detail returns 404 for non-existent chapter."""
        response = self.client.get("/api/chapters/99/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "chapter_not_found")

    def test_verse_detail_returns_full_verse_data(self):
        """Test verse detail endpoint returns all verse information."""
        # Ensure verse exists
        from guide_api.models import Verse
        verse, _ = Verse.objects.get_or_create(
            chapter=2,
            verse=47,
            defaults={
                "translation": "Focus on action, not results.",
                "commentary": "Key verse on karma yoga.",
                "themes": ["discipline", "purpose"],
            },
        )
        response = self.client.get("/api/verses/2.47/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["reference"], "2.47")
        self.assertEqual(response.data["chapter"], 2)
        self.assertEqual(response.data["verse"], 47)
        self.assertIn("translation", response.data)
        self.assertIn("commentaries", response.data)

    def test_verse_detail_404_for_invalid_verse(self):
        """Test verse detail returns 404 for non-existent verse."""
        response = self.client.get("/api/verses/99.999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "verse_not_found")

    def test_mantra_endpoint_returns_verse_for_mood(self):
        """Test mantra endpoint returns appropriate verse."""
        # Create all verses that might be selected for 'calm' mood
        from guide_api.models import Verse
        for ref in ["2.48", "2.70", "6.35", "12.15"]:
            ch, v = ref.split(".")
            Verse.objects.get_or_create(
                chapter=int(ch),
                verse=int(v),
                defaults={
                    "translation": "Be steadfast in yoga.",
                    "commentary": "Equanimity teaching.",
                    "themes": ["calm", "discipline"],
                },
            )
        response = self.client.post(
            "/api/mantra/",
            {"mood": "calm", "language": "en"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("reference", response.data)
        self.assertIn("mood", response.data)
        self.assertIn("meaning", response.data)
        self.assertEqual(response.data["mood"], "calm")

    def test_mantra_endpoint_supports_hindi(self):
        """Test mantra endpoint returns Hindi content when requested."""
        from guide_api.models import Verse
        # Create all verses that might be selected for 'peace' mood
        for ref in ["2.66", "2.71", "5.29", "12.12"]:
            ch, v = ref.split(".")
            Verse.objects.get_or_create(
                chapter=int(ch),
                verse=int(v),
                defaults={
                    "translation": "Be steadfast in yoga.",
                    "commentary": "Peace teaching.",
                    "themes": ["peace"],
                },
            )
        response = self.client.post(
            "/api/mantra/",
            {"mood": "peace", "language": "hi"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["language"], "hi")

    def test_chapters_v1_alias_works(self):
        """Test chapter listing works via /api/v1/ alias."""
        response = self.client.get("/api/v1/chapters/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("chapters", response.data)
