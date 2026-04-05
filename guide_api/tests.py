import json
from datetime import timedelta
from tempfile import NamedTemporaryFile

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from guide_api.models import (
    AskEvent,
    EngagementEvent,
    FollowUpEvent,
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
            {"semantic", "hybrid", "hybrid_fallback"},
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

    def test_chat_ui_renders_structured_response_sections(self):
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "user_id": "demo-user",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Guidance")
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

    def test_chat_ui_plan_update_for_existing_username(self):
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "plan",
                "user_id": "demo-user",
                "selected_plan": "pro",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Plan updated to pro")

    @override_settings(ASK_LIMIT_FREE_DAILY=1)
    def test_chat_ui_enforces_quota_for_existing_username(self):
        first = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "user_id": "demo-user",
                "mode": "simple",
                "message": "I feel anxious about career growth.",
            },
        )
        second = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "user_id": "demo-user",
                "mode": "simple",
                "message": "I feel anxious about career growth.",
            },
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertContains(second, "Daily ask limit reached")

    def test_chat_ui_tracks_recent_questions_up_to_three(self):
        for idx in range(1, 5):
            self.client.post(
                "/api/chat-ui/",
                data={
                    "action": "ask",
                    "user_id": "demo-user",
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
        ask_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "user_id": "demo-user",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(ask_response.status_code, status.HTTP_200_OK)
        self.assertEqual(ResponseFeedback.objects.count(), 0)

        feedback_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "feedback",
                "user_id": "demo-user",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
                "helpful": "true",
                "response_mode": "fallback",
                "conversation_id": "1",
                "note": "Useful",
            },
        )
        self.assertEqual(feedback_response.status_code, status.HTTP_200_OK)
        self.assertEqual(ResponseFeedback.objects.count(), 1)

    def test_chat_ui_save_reflection_flow(self):
        ask_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "user_id": "demo-user",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(ask_response.status_code, status.HTTP_200_OK)

        save_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "save",
                "user_id": "demo-user",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
                "conversation_id": "1",
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
