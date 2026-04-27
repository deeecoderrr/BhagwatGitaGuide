import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
import guide_api.views as guide_views
from guide_api.models import (
    AskEvent,
    BillingRecord,
    CommunityPost,
    Conversation,
    EngagementEvent,
    FollowUpEvent,
    GrowthEvent,
    GuestChatIdentity,
    Message,
    NotificationDevice,
    RequestQuotaSettings,
    ResponseFeedback,
    SadhanaDay,
    SadhanaProgram,
    SadhanaStep,
    SavedReflection,
    SharedAnswer,
    SupportTicket,
    UserEngagementProfile,
    UserSubscription,
    Verse,
    WebAudienceProfile,
)
from django.test import Client, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from guide_api.push_reminders import (
    _expo_fields_for_daily_reminder,
    is_expo_push_token,
    is_within_reminder_window,
    run_push_reminders,
    zoneinfo_for_reminder_timezone,
)
from guide_api.services import (
    _build_fallback_guidance,
    _build_query_embedding,
    _is_grounded_response,
    _parse_json_payload,
    _is_professional_ethics_query,
    _is_short_gratitude_like,
    _serialize_conversation_context,
    build_guidance,
    classify_user_intent,
    infer_themes_from_text,
    interpret_query,
    normalize_chat_user_message,
    query_embedding_input_text,
    resolve_guidance_language,
)


@override_settings(
    DEBUG=True,
    OPENAI_API_KEY="",
    DISABLE_ALL_QUOTAS=False,
)
class GuideApiTests(APITestCase):
    def setUp(self):
        guide_views._quota_settings_cache["value"] = (
            guide_views._QUOTA_SETTINGS_UNSET
        )
        guide_views._quota_settings_cache["loaded_at"] = 0.0
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

    def test_starter_prompts_endpoint_returns_prompt_sets(self):
        response = self.client.get("/api/starter-prompts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("starter_prompts", response.data)
        self.assertIn("follow_up_prompts", response.data)
        self.assertGreaterEqual(len(response.data["starter_prompts"]), 1)

    def test_plan_catalog_endpoint_returns_plan_matrix(self):
        response = self.client.get("/api/plans/catalog/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("recommended_currency", response.data)
        self.assertIn("plans", response.data)
        self.assertIn("plus", response.data["plans"])
        self.assertIn("pro", response.data["plans"])

    def test_guest_ask_endpoint_returns_guidance_without_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/guest/ask/",
            {
                "message": "I feel anxious about my career growth.",
                "mode": "simple",
                "language": "en",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("guidance", response.data)
        self.assertIn("guest_id", response.data)
        self.assertIn("guest_quota_snapshot", response.data)

    def test_guest_ask_endpoint_blocks_deep_mode_for_guest_plan(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/guest/ask/",
            {
                "message": "Give me deep insights for this situation.",
                "mode": "deep",
                "language": "en",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "deep_mode_not_included")
        self.assertEqual(response.data["plan"], UserSubscription.PLAN_FREE)

    @override_settings(DISABLE_ALL_QUOTAS=False)
    def test_guest_ask_endpoint_enforces_guest_daily_cap(self):
        self.client.force_authenticate(user=None)
        RequestQuotaSettings.objects.create(
            guest_limit_enabled=True,
            guest_ask_limit=1,
            free_limit_enabled=True,
            free_daily_ask_limit=3,
            free_monthly_ask_limit=100,
            free_deep_mode_enabled=False,
            plus_limit_enabled=False,
            plus_daily_ask_limit=0,
            plus_monthly_ask_limit=200,
            plus_deep_monthly_limit=40,
            pro_limit_enabled=True,
            pro_daily_ask_limit=100,
            pro_monthly_ask_limit=500,
            pro_deep_monthly_limit=180,
        )
        first = self.client.post(
            "/api/guest/ask/",
            {"message": "Need calm", "mode": "simple", "language": "en"},
            format="json",
        )
        second = self.client.post(
            "/api/guest/ask/",
            {"message": "Need calm again", "mode": "simple", "language": "en"},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_guest_history_endpoint_returns_session_transcript(self):
        self.client.force_authenticate(user=None)
        self.client.post(
            "/api/guest/ask/",
            {
                "message": "I feel anxious about my career growth.",
                "mode": "simple",
                "language": "en",
            },
            format="json",
        )
        response = self.client.get("/api/guest/history/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["messages"]), 2)
        self.assertGreaterEqual(len(response.data["recent_questions"]), 1)

    def test_guest_history_reset_clears_messages_and_recent_questions(self):
        self.client.force_authenticate(user=None)
        self.client.post(
            "/api/guest/ask/",
            {"message": "First question", "mode": "simple", "language": "en"},
            format="json",
        )
        reset = self.client.post("/api/guest/history/reset/", {}, format="json")
        self.assertEqual(reset.status_code, status.HTTP_200_OK)
        self.assertEqual(reset.data["messages"], [])
        self.assertEqual(reset.data["recent_questions"], [])
        after = self.client.get("/api/guest/history/")
        self.assertEqual(after.status_code, status.HTTP_200_OK)
        self.assertEqual(after.data["messages"], [])
        self.assertEqual(after.data["recent_questions"], [])

    def test_guest_recent_questions_endpoint_returns_latest_guest_questions(self):
        self.client.force_authenticate(user=None)
        self.client.post(
            "/api/guest/ask/",
            {"message": "Question one", "mode": "simple", "language": "en"},
            format="json",
        )
        self.client.post(
            "/api/guest/ask/",
            {"message": "Question two", "mode": "simple", "language": "en"},
            format="json",
        )
        response = self.client.get("/api/guest/recent-questions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["recent_questions"]), 2)
        self.assertEqual(response.data["recent_questions"][0], "Question two")

    def test_public_seo_index_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'id="nav_language"')
        self.assertContains(response, "Bhagavad Gita Guides For Real Life Problems")
        self.assertContains(response, "bhagavad-gita-for-anxiety")

    def test_privacy_policy_page_loads(self):
        response = self.client.get("/privacy-policy/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Privacy Policy")
        self.assertContains(response, "Mental Health and Medical Disclaimer")
        self.assertContains(response, "contact:")

    def test_robots_txt_exposes_sitemap(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("User-agent: *", body)
        self.assertIn("Sitemap:", body)
        self.assertIn("Disallow: /admin/", body)

    def test_robots_txt_disallows_itr_private_paths_when_itr_enabled(self):
        from django.conf import settings

        if not getattr(settings, "ITR_ENABLED", False):
            self.skipTest("ITR routes not enabled")
        response = self.client.get("/robots.txt")
        body = response.content.decode()
        self.assertIn("Disallow: /itr-computation/documents/", body)

    def test_sitemap_xml_lists_public_routes(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("<urlset", body)
        self.assertIn("/bhagavad-gita-for-anxiety/", body)
        self.assertIn("/bhagavad-gita-for-purpose/", body)
        self.assertIn("/frequently-asked-bhagavad-gita-questions/", body)
        self.assertIn("/daily-bhagavad-gita-verse/", body)
        self.assertIn("/privacy-policy/", body)
        self.assertIn("/api/chat-ui/", body)
        self.assertIn("<lastmod>", body)

    def test_sitemap_xml_includes_itr_marketing_when_enabled(self):
        from django.conf import settings

        if not getattr(settings, "ITR_ENABLED", False):
            self.skipTest("ITR routes not enabled")
        response = self.client.get("/sitemap.xml")
        body = response.content.decode()
        self.assertIn("/itr-computation/", body)
        self.assertIn("/itr-computation/pricing/", body)

    def test_public_seo_topic_page_loads(self):
        response = self.client.get("/bhagavad-gita-for-anxiety/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'id="nav_language"')
        self.assertContains(response, "Bhagavad Gita For Anxiety And Overthinking")
        self.assertContains(response, "Relevant Bhagavad Gita verses")
        self.assertContains(response, "Ask This In The App")

    def test_public_seo_page_tracks_unique_audience(self):
        self.client.force_authenticate(user=None)
        first = self.client.get("/")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertIn("web_audience_id", first.cookies)

        second = self.client.get("/")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(WebAudienceProfile.objects.count(), 1)
        profile = WebAudienceProfile.objects.first()
        self.assertEqual(profile.last_source, WebAudienceProfile.SOURCE_SEO_INDEX)
        self.assertGreaterEqual(profile.visit_count, 2)

    def test_public_seo_tracks_utm_attribution(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(
            "/?utm_source=reddit&utm_medium=post&utm_campaign=launch",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = WebAudienceProfile.objects.first()
        self.assertEqual(profile.first_utm_source, "reddit")
        self.assertEqual(profile.first_utm_medium, "post")
        self.assertEqual(profile.first_utm_campaign, "launch")

    def test_public_seo_topic_ask_cta_uses_get_prefill(self):
        response = self.client.get("/bhagavad-gita-for-anxiety/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(
            response,
            '<form class="cta-form" method="get" action="/api/chat-ui/">',
            html=False,
        )
        self.assertContains(response, 'textarea name="prefill"', html=False)

    def test_chat_ui_prefill_query_renders_in_message_field(self):
        response = self.client.get("/api/chat-ui/?mode=simple&language=en&prefill=anxiety+help")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "anxiety help")

    def test_chat_ui_prefill_logs_seo_handoff_marker(self):
        from unittest.mock import patch

        with patch("guide_api.views.logger.info") as mock_logger_info:
            response = self.client.get(
                "/api/chat-ui/?mode=simple&language=en&prefill=anxiety+help",
                HTTP_REFERER="https://askbhagavadgita.fly.dev/bhagavad-gita-for-anxiety/?language=en",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            any(call.args and call.args[0] == "seo_cta_to_chatui" for call in mock_logger_info.call_args_list),
        )

    def test_public_seo_index_page_switches_to_hindi(self):
        response = self.client.get("/?language=hi")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "एक केंद्रित गाइड चुनें")
        self.assertContains(response, "ऐप खोलें")

    def test_public_seo_topic_page_switches_to_hindi(self):
        response = self.client.get("/bhagavad-gita-for-anxiety/?language=hi")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "चिंता और ओवरथिंकिंग के लिए भगवद गीता")
        self.assertContains(response, "आम स्थितियाँ")

    def test_public_seo_index_includes_canonical_and_json_ld(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, 'application/ld+json')
        self.assertContains(response, 'hreflang="hi"')
        self.assertContains(response, 'name="keywords"')
        self.assertContains(response, "Gita GPT")
        self.assertContains(response, '"@type": "FAQPage"')
        self.assertContains(response, "Most Searched Bhagavad Gita Verses")
        self.assertContains(response, "2.47")
        self.assertContains(response, '"@type": "ItemList"')

    def test_public_seo_topic_includes_canonical_and_json_ld(self):
        response = self.client.get("/bhagavad-gita-for-anxiety/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, 'application/ld+json')
        self.assertContains(response, 'BreadcrumbList')
        self.assertContains(response, 'name="keywords"')

    def test_new_public_seo_topic_page_loads(self):
        response = self.client.get("/bhagavad-gita-for-purpose/?language=hi")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "उद्देश्य और अर्थ के लिए भगवद गीता")
        self.assertContains(response, "प्रासंगिक भगवद गीता श्लोक")

    def test_public_question_archive_page_loads(self):
        response = self.client.get("/frequently-asked-bhagavad-gita-questions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Frequently Asked Bhagavad Gita Questions")
        self.assertContains(response, "What does the Bhagavad Gita say about anxiety?")
        self.assertContains(response, '"@type": "ItemList"')

    def test_public_daily_verse_hub_page_loads(self):
        response = self.client.get("/daily-bhagavad-gita-verse/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Today's Bhagavad Gita Verse")
        self.assertContains(response, "Apply This Verse To My Life")
        self.assertContains(response, '"@type": "ItemList"')

    @override_settings(GOOGLE_SITE_VERIFICATION="token-abc-123")
    def test_public_seo_page_renders_google_verification_meta(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(
            response,
            'name="google-site-verification" content="token-abc-123"',
            html=False,
        )

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

    @patch("guide_api.google_auth.google_id_token.verify_oauth2_token")
    def test_auth_google_creates_user_and_returns_token(self, mock_verify):
        mock_verify.return_value = {
            "sub": "test-subject-001",
            "email": "google_tester@example.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "given_name": "Google",
            "family_name": "Tester",
        }
        with self.settings(GOOGLE_OAUTH_CLIENT_ID="cid.apps.googleusercontent.com"):
            self.client.force_authenticate(user=None)
            response = self.client.post(
                "/api/auth/google/",
                {"id_token": "fake.jwt.token"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "google_test-subject-001")
        self.assertIn("token", response.data)
        saved = get_user_model().objects.get(username="google_test-subject-001")
        self.assertEqual(saved.first_name, "Google")
        self.assertEqual(saved.last_name, "Tester")
        self.assertEqual(saved.email, "google_tester@example.com")

    def test_auth_google_disabled_without_client_id(self):
        self.client.force_authenticate(user=None)
        with self.settings(GOOGLE_OAUTH_CLIENT_ID=""):
            response = self.client.post(
                "/api/auth/google/",
                {"id_token": "x"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_auth_google_conflict_when_email_registered_elsewhere(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="manual-user",
            password="secret-pass-99",
            email="taken@gmail.com",
        )
        with patch(
            "guide_api.google_auth.google_id_token.verify_oauth2_token",
            return_value={
                "sub": "new-google-only",
                "email": "taken@gmail.com",
                "email_verified": True,
                "iss": "https://accounts.google.com",
            },
        ):
            self.client.force_authenticate(user=None)
            with self.settings(GOOGLE_OAUTH_CLIENT_ID="cid.apps.googleusercontent.com"):
                response = self.client.post(
                    "/api/auth/google/",
                    {"id_token": "fake"},
                    format="json",
                )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

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

    def test_auth_plan_update_accepts_plus_plan(self):
        response = self.client.post(
            "/api/auth/plan/",
            {"plan": "plus"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"], "plus")

    def test_auth_profile_patch_updates_user_fields(self):
        response = self.client.patch(
            "/api/auth/profile/",
            {
                "first_name": "Dee",
                "last_name": "Coder",
                "email": "dee@example.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Dee")
        self.assertEqual(self.user.last_name, "Coder")
        self.assertEqual(self.user.email, "dee@example.com")

    def test_auth_change_password_updates_credentials(self):
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": "demo-pass-123",
                "new_password": "fresh-pass-456",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("fresh-pass-456"))

    def test_auth_forgot_password_returns_generic_ok(self):
        self.user.email = "demo@example.com"
        self.user.save(update_fields=["email"])
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/auth/forgot-password/",
            {"email": "demo@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")

    def test_auth_reset_password_confirm_accepts_valid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/auth/reset-password/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password": "newest-pass-789",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newest-pass-789"))

    def test_notifications_preferences_endpoint_get_and_patch(self):
        get_response = self.client.get("/api/notifications/preferences/")
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data.get("reminder_language"), "en")
        patch_response = self.client.patch(
            "/api/notifications/preferences/",
            {
                "reminder_enabled": True,
                "preferred_channel": "push",
                "reminder_language": "hi",
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertTrue(patch_response.data["reminder_enabled"])
        self.assertEqual(patch_response.data.get("reminder_language"), "hi")

    def test_devices_register_and_delete(self):
        create_response = self.client.post(
            "/api/devices/register/",
            {"token": "fcm-token-123", "platform": "android"},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        device_id = create_response.data["id"]
        self.assertTrue(
            NotificationDevice.objects.filter(id=device_id, user=self.user).exists(),
        )
        delete_response = self.client.delete(f"/api/devices/{device_id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_devices_list_returns_active_rows(self):
        self.client.post(
            "/api/devices/register/",
            {"token": "ExponentPushToken[listtest]", "platform": "ios"},
            format="json",
        )
        list_response = self.client.get("/api/devices/")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["platform"], "ios")

    def test_conversations_list_create_messages_and_delete(self):
        create_response = self.client.post(
            "/api/conversations/",
            {"initial_message": "How can I stay calm?"},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        conversation_id = create_response.data["id"]

        list_response = self.client.get("/api/conversations/")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 1)

        messages_response = self.client.get(
            f"/api/conversations/{conversation_id}/messages/",
        )
        self.assertEqual(messages_response.status_code, status.HTTP_200_OK)
        self.assertEqual(messages_response.data["count"], 1)

        delete_response = self.client.delete(f"/api/conversations/{conversation_id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_support_ticket_list_returns_user_tickets(self):
        SupportTicket.objects.create(
            user=self.user,
            requester_id=self.user.username,
            name="Demo User",
            email="demo@example.com",
            issue_type=SupportTicket.ISSUE_ACCOUNT,
            message="Need login help.",
        )
        response = self.client.get("/api/support/tickets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_daily_verse_history_endpoint_returns_rows(self):
        response = self.client.get("/api/daily-verse/history/?days=3&language=en")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["days"], 3)
        self.assertEqual(len(response.data["results"]), 3)

    def test_verse_search_endpoint_returns_matches(self):
        Verse.objects.create(
            chapter=99,
            verse=1,
            translation="Calm mind and self discipline lead to peace.",
            commentary="Focused effort and detachment.",
            themes=["discipline", "calm"],
        )
        response = self.client.get("/api/verses/search/?q=discipline&limit=5")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 1)

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

    def test_resolve_guidance_language_roman_hinglish_with_english_ui(self):
        msg = (
            "mujhe bahut tension hai aur samajh nahi aa raha main kya karun "
            "life mein"
        )
        self.assertEqual(resolve_guidance_language("en", msg), "hinglish")

    def test_resolve_guidance_language_devanagari_with_english_ui_prefers_hi(self):
        msg = "मुझे चिंता है और मैं बहुत सोचता हूँ। गीता क्या कहती है?"
        self.assertEqual(resolve_guidance_language("en", msg), "hi")

    def test_resolve_guidance_language_pure_english_stays_en(self):
        self.assertEqual(
            resolve_guidance_language(
                "en",
                "What does the Bhagavad Gita teach about anxiety?",
            ),
            "en",
        )

    def test_ask_endpoint_reports_response_language_hinglish(self):
        payload = {
            "message": (
                "mujhe gussa bahut jaldi aata hai aur baad mein regret hota hai "
                "gita kya sikhati hai"
            ),
            "mode": "simple",
            "language": "en",
        }
        response = self.client.post("/api/ask/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("response_language"), "hinglish")

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

    @override_settings(DISABLE_ALL_QUOTAS=True, ASK_LIMIT_FREE_DAILY=1)
    def test_ask_endpoint_ignores_limits_when_global_quota_switch_is_off(self):
        payload = {
            "message": "I feel anxious about my career growth.",
            "mode": "simple",
        }
        first = self.client.post("/api/ask/", payload, format="json")
        second = self.client.post("/api/ask/", payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertIsNone(second.data["daily_limit"])
        self.assertIsNone(second.data["remaining_today"])

    def test_quota_settings_lookup_failure_falls_back_to_defaults(self):
        guide_views._quota_settings_cache["value"] = guide_views._QUOTA_SETTINGS_UNSET
        guide_views._quota_settings_cache["loaded_at"] = 0.0

        with patch(
            "guide_api.views.RequestQuotaSettings.objects.first",
            side_effect=RuntimeError("db temporarily unavailable"),
        ):
            self.assertEqual(
                guide_views._plan_daily_limit(UserSubscription.PLAN_FREE),
                3,
            )
            self.assertFalse(
                guide_views._plan_deep_mode_allowed(UserSubscription.PLAN_FREE),
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

    @override_settings(ENABLE_FREE_DEEP_MODE=False)
    def test_ask_endpoint_blocks_deep_mode_for_free_plan(self):
        response = self.client.post(
            "/api/ask/",
            {
                "message": "I want deeper guidance for my anxiety.",
                "mode": "deep",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["error"]["code"], "deep_mode_not_included")

    @override_settings(ENABLE_FREE_DEEP_MODE=False)
    def test_ask_endpoint_plus_deep_succeeds_without_deep_insights_payload(self):
        subscription, _ = UserSubscription.objects.get_or_create(user=self.user)
        subscription.plan = UserSubscription.PLAN_PLUS
        subscription.save(update_fields=["plan"])

        response = self.client.post(
            "/api/ask/",
            {
                "message": "Help me understand my stress deeply.",
                "mode": "deep",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("deep_insights", response.data)

    @override_settings(
        ENABLE_FREE_DEEP_MODE=False,
        ASK_LIMIT_PRO_DEEP_MONTHLY=0,
    )
    def test_ask_endpoint_pro_deep_limit_zero_means_unlimited(self):
        subscription, _ = UserSubscription.objects.get_or_create(user=self.user)
        subscription.plan = UserSubscription.PLAN_PRO
        subscription.save(update_fields=["plan"])

        for _ in range(3):
            response = self.client.post(
                "/api/ask/",
                {
                    "message": "Give me a deep reflection on discipline.",
                    "mode": "deep",
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIsNone(response.data["deep_monthly_limit"])
            self.assertNotIn("deep_insights", response.data)

    def test_auth_me_includes_plan_and_quota_fields(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("plan", response.data)
        self.assertIn("daily_limit", response.data)
        self.assertIn("used_today", response.data)
        self.assertIn("remaining_today", response.data)
        self.assertIn("engagement", response.data)

    def test_auth_me_auto_downgrades_expired_paid_plan(self):
        subscription, _ = UserSubscription.objects.get_or_create(user=self.user)
        subscription.plan = UserSubscription.PLAN_PLUS
        subscription.is_active = True
        subscription.subscription_end_date = timezone.now() - timedelta(days=1)
        subscription.save(
            update_fields=["plan", "is_active", "subscription_end_date"],
        )

        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"], UserSubscription.PLAN_FREE)

        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_FREE)
        self.assertFalse(subscription.is_active)
        self.assertIsNone(subscription.subscription_end_date)

    def test_engagement_me_get_returns_defaults(self):
        response = self.client.get("/api/engagement/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["daily_streak"], 0)
        self.assertEqual(response.data["preferred_channel"], "none")
        self.assertEqual(response.data["timezone"], "UTC")
        self.assertEqual(response.data.get("reminder_language"), "en")

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
        self.assertIn("query_interpretation", response.data)
        self.assertEqual(
            response.data["query_interpretation"]["emotional_state"],
            "anxious",
        )
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

    def test_ask_endpoint_handles_greeting_without_forcing_verses(self):
        response = self.client.post(
            "/api/ask/",
            {
                "message": "hye",
                "mode": "simple",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["retrieved_references"], [])
        self.assertEqual(
            response.data["query_interpretation"]["life_domain"],
            "conversation",
        )
        self.assertIn("Bhagavad Gita", response.data["guidance"])
        self.assertEqual(response.data["actions"], [])
        self.assertEqual(response.data["reflection"], "")
        self.assertEqual(response.data["related_verses"], [])

    def test_ask_endpoint_explains_exact_verse_without_switching_primary_reference(self):
        response = self.client.post(
            "/api/ask/",
            {
                "message": "Explain Bhagavad Gita 2.47 in simple language",
                "mode": "simple",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["intent_type"], "verse_explanation")
        self.assertEqual(response.data["verse_references"][0], "2.47")
        self.assertEqual(response.data["verses"][0]["reference"], "2.47")
        self.assertIn("2.47", response.data["guidance"])
        self.assertEqual(response.data["actions"], [])
        self.assertEqual(response.data["reflection"], "")

    def test_ask_endpoint_general_knowledge_question_does_not_force_actions(self):
        response = self.client.post(
            "/api/ask/",
            {
                "message": "What does the Bhagavad Gita say about karma yoga?",
                "mode": "simple",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["intent_type"], "knowledge_question")
        self.assertEqual(response.data["actions"], [])
        self.assertEqual(response.data["reflection"], "")
        self.assertTrue(response.data["guidance"])

    def test_ask_endpoint_casual_chat_does_not_force_verses(self):
        response = self.client.post(
            "/api/ask/",
            {
                "message": "what can you do?",
                "mode": "simple",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["intent_type"], "casual_chat")
        self.assertEqual(response.data["verses"], [])
        self.assertEqual(response.data["related_verses"], [])
        self.assertEqual(response.data["actions"], [])
        self.assertEqual(response.data["reflection"], "")

    def test_ambiguous_intent_heuristic_personal_help_is_life_guidance(self):
        from guide_api.services import classify_user_intent

        intent = classify_user_intent("help me get divorce from my wife")
        self.assertEqual(intent.intent_type, "life_guidance")

    def test_two_word_help_me_routes_to_life_guidance_for_retrieval(self):
        from guide_api.services import classify_user_intent

        intent = classify_user_intent("help me")
        self.assertEqual(intent.intent_type, "life_guidance")

    def test_heuristic_intent_runs_before_llm_skips_refinement_call(self):
        """Heuristic match must not invoke intent LLM (latency + cost)."""
        from unittest.mock import patch

        from guide_api.services import classify_user_intent

        with patch(
            "guide_api.services._refine_intent_via_llm",
        ) as mock_refine:
            with self.settings(OPENAI_API_KEY="sk-test"):
                intent = classify_user_intent(
                    "help me get divorce from my wife",
                )
        mock_refine.assert_not_called()
        self.assertEqual(intent.intent_type, "life_guidance")

    def test_ambiguous_intent_heuristic_define_without_gita_keywords(self):
        from guide_api.services import classify_user_intent

        intent = classify_user_intent("define sattva in one sentence")
        self.assertEqual(intent.intent_type, "knowledge_question")

    def test_intent_llm_refinement_returns_life_guidance_when_configured(self):
        from unittest.mock import MagicMock, patch

        from guide_api.services import classify_user_intent

        mock_resp = MagicMock()
        mock_resp.output_text = (
            '{"intent_type":"life_guidance","reason":"personal dilemma"}'
        )
        with patch(
            "guide_api.services._openai_client",
        ) as mock_client_factory:
            mock_client = MagicMock()
            mock_client_factory.return_value = mock_client
            mock_client.responses.create.return_value = mock_resp
            with self.settings(
                OPENAI_API_KEY="sk-test",
                DISABLE_INTENT_LLM_REFINEMENT=False,
            ):
                intent = classify_user_intent(
                    "something vague that would fall through heuristics",
                )
        self.assertEqual(intent.intent_type, "life_guidance")

    def test_intent_llm_skipped_by_default_when_ambiguous(self):
        """With DISABLE_INTENT_LLM_REFINEMENT default, vague text stays casual without API."""
        from unittest.mock import patch

        from guide_api.services import classify_user_intent

        with patch("guide_api.services._openai_client") as mock_client_factory:
            mock_client_factory.side_effect = AssertionError("intent LLM should not run")
            with self.settings(OPENAI_API_KEY="sk-test"):
                intent = classify_user_intent(
                    "something vague that would fall through heuristics",
                )
        self.assertEqual(intent.intent_type, "casual_chat")

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

    def test_retrieval_eval_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/eval/retrieval/",
            {"message": "test", "mode": "simple"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

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

    def test_daily_verse_endpoint_returns_quote_and_meaning(self):
        response = self.client.get("/api/daily-verse/?language=en")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("verse", response.data)
        self.assertIn("quote", response.data)
        self.assertIn("meaning", response.data)
        self.assertTrue(response.data["verse"]["reference"])
        self.assertTrue(response.data["quote"])
        self.assertTrue(response.data["meaning"])

    def test_daily_verse_hindi_meaning_skips_short_prefix_sentence(self):
        from unittest.mock import patch

        verse = Verse.objects.create(
            chapter=11,
            verse=55,
            translation="He reaches Me who acts for Me.",
            commentary="",
            themes=["devotion"],
        )
        detail = {
            "english_meaning": "He reaches Me who acts for Me.",
            "slok": (
                "मत्कर्मकृन्मत्परमो मद्भक्तः सङ्गवर्जितः | "
                "निर्वैरः सर्वभूतेषु यः स मामेति पाण्डव ||११-५५||"
            ),
            "hindi_meaning": (
                "।।11.55।। हे पाण्डव! जो पुरुष मेरे लिए ही कर्म करने वाला है, "
                "और मुझे ही परम लक्ष्य मानता है, वह मुझे प्राप्त होता है।"
            ),
            "translation": "He reaches Me who acts for Me.",
        }

        with patch("guide_api.views.get_verse_detail", return_value=detail):
            response = self.client.get("/api/daily-verse/?language=hi")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should include the substantive Hindi meaning, not just 'हे पाण्डव!'
        self.assertIn("जो पुरुष", response.data["meaning"])
        self.assertNotEqual(response.data["meaning"].strip(), "हे पाण्डव!")

    def test_chat_ui_page_loads(self):
        response = self.client.get("/api/chat-ui/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'id="nav_language"')
        self.assertContains(response, "Try a starter prompt")
        self.assertContains(response, "Save Your Journey")
        self.assertContains(response, "Guest mode is temporary")
        self.assertContains(response, "Register")
        self.assertContains(response, "Login")
        self.assertContains(response, "Forgot password?")

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

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID="test-id.apps.googleusercontent.com",
    )
    def test_chat_ui_logout_response_includes_google_sign_in_assets(self):
        """Logout must use ``_render_chat_ui`` so OAuth markup is not dropped."""
        register_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "register",
                "register_username": "oauth-after-logout-user",
                "register_password": "oauth-pass-1234",
            },
        )
        self.assertEqual(register_response.status_code, status.HTTP_200_OK)

        logout_response = self.client.post(
            "/api/chat-ui/",
            data={"action": "logout", "language": "en"},
        )
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertContains(logout_response, "Logged out.")
        self.assertContains(logout_response, "accounts.google.com/gsi/client")
        self.assertContains(logout_response, "data-google-signin-container")
        self.assertContains(logout_response, "Continue with Google")

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

    def test_chat_ui_uses_authenticated_request_user_for_paid_plan_context(self):
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_PLUS,
            is_active=True,
            subscription_end_date=timezone.now() + timedelta(days=30),
        )
        BillingRecord.objects.create(
            user=self.user,
            subscription=subscription,
            plan=UserSubscription.PLAN_PLUS,
            payment_status=BillingRecord.STATUS_VERIFIED,
            tax_treatment=BillingRecord.TAX_DOMESTIC,
            billing_name="Demo User",
            billing_email="demo@example.com",
            billing_country_code="IN",
            billing_country_name="India",
            currency=UserSubscription.CURRENCY_INR,
            amount_minor=19900,
            amount_major=Decimal("199.00"),
            razorpay_order_id="order_paid_chatui",
            razorpay_payment_id="pay_paid_chatui",
        )

        self.client.force_login(self.user)
        response = self.client.get("/api/chat-ui/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context["selected_plan"], UserSubscription.PLAN_PLUS)
        self.assertEqual(
            response.context["quota_snapshot"]["plan"],
            UserSubscription.PLAN_PLUS,
        )
        self.assertEqual(
            response.context["latest_billing_record"].plan,
            UserSubscription.PLAN_PLUS,
        )

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

    def test_chat_ui_hides_action_panels_for_exact_verse_explanation(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "Explain Bhagavad Gita 2.47 in simple language",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.context["response_data"]["show_actions"])
        self.assertFalse(response.context["response_data"]["show_reflection"])
        self.assertContains(response, "Verses Used")

    def test_chat_ui_guest_telemetry_uses_unique_guest_identifier(self):
        self.client.force_authenticate(user=None)
        landing = self.client.get("/api/chat-ui/")
        self.assertEqual(landing.status_code, status.HTTP_200_OK)
        guest_cookie = self.client.cookies.get("chat_ui_guest_id")
        self.assertIsNotNone(guest_cookie)

        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "I feel anxious about my career growth.",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = AskEvent.objects.filter(
            source=AskEvent.SOURCE_CHAT_UI,
            outcome=AskEvent.OUTCOME_SERVED,
        ).latest("created_at")
        self.assertTrue(event.user_id.startswith("guest:"))
        self.assertIn(guest_cookie.value, event.user_id)

    def test_analytics_event_ingest_endpoint_records_growth_event(self):
        self.client.force_authenticate(user=None)
        self.client.get("/api/chat-ui/")
        response = self.client.post(
            "/api/analytics/events/",
            data={
                "event_type": "starter_click",
                "source": "chat_ui",
                "path": "/api/chat-ui/",
                "metadata": {"seed": "career"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            GrowthEvent.objects.filter(
                event_type=GrowthEvent.EVENT_STARTER_CLICK,
                source=GrowthEvent.SOURCE_CHAT_UI,
            ).count(),
            1,
        )

    def test_analytics_summary_requires_staff_and_returns_totals(self):
        non_staff = User.objects.create_user(
            username="non-staff",
            password="pass-12345",
        )
        self.client.force_authenticate(user=non_staff)
        denied = self.client.get("/api/analytics/summary/")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_authenticate(user=self.user)
        self.client.get("/api/chat-ui/")
        self.client.post(
            "/api/analytics/events/",
            data={"event_type": "share_click", "source": "chat_ui"},
            format="json",
        )
        response = self.client.get("/api/analytics/summary/?days=7")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("all_time", response.data)
        self.assertIn("conversion", response.data)
        self.assertIn("daily", response.data)

    def test_chat_ui_guest_ask_handles_internal_failure_gracefully(self):
        from unittest.mock import patch

        self.client.force_authenticate(user=None)
        with patch(
            "guide_api.views.retrieve_verses_with_trace",
            side_effect=RuntimeError("forced failure for logging path"),
        ):
            response = self.client.post(
                "/api/chat-ui/",
                data={
                    "action": "ask",
                    "mode": "simple",
                    "language": "en",
                    "message": "I feel anxious about my career growth.",
                },
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(
            response,
            "We hit a temporary issue while processing your question.",
        )
        self.assertContains(response, "Conversation")
        self.assertNotContains(response, "Get Verse-Based Guidance For Your Problem")
        self.assertContains(response, "I feel anxious about my career growth.")
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(response.context["conversations"], [])
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

    def test_chat_ui_guest_limit_blocks_fourth_question(self):
        self.client.force_authenticate(user=None)
        landing = self.client.get("/api/chat-ui/")
        self.assertEqual(landing.status_code, status.HTTP_200_OK)
        guest_cookie = self.client.cookies["chat_ui_guest_id"].value

        for idx in range(3):
            response = self.client.post(
                "/api/chat-ui/",
                data={
                    "action": "ask",
                    "mode": "simple",
                    "message": f"guest question {idx + 1}",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        blocked = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "guest question 4",
            },
        )
        self.assertEqual(blocked.status_code, status.HTTP_200_OK)
        self.assertContains(blocked, "used all 3 guest questions")
        self.assertContains(blocked, "Sign up or log in")
        identity = GuestChatIdentity.objects.get(guest_id=guest_cookie)
        self.assertEqual(identity.total_asks, 3)

    def test_chat_ui_guest_limit_persists_in_cookie_across_browser_restart(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/chat-ui/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        guest_cookie = self.client.cookies["chat_ui_guest_id"].value

        browser_restart_client = self.client_class()
        browser_restart_client.cookies["chat_ui_guest_id"] = guest_cookie
        reopened = browser_restart_client.get("/api/chat-ui/")
        self.assertEqual(reopened.status_code, status.HTTP_200_OK)
        self.assertEqual(
            reopened.context["guest_quota_snapshot"]["ask_limit"],
            3,
        )

    def test_chat_ui_guest_limit_resets_on_new_day_for_same_browser(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/chat-ui/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        guest_cookie = self.client.cookies["chat_ui_guest_id"].value

        for idx in range(3):
            response = self.client.post(
                "/api/chat-ui/",
                data={
                    "action": "ask",
                    "mode": "simple",
                    "message": f"guest daily reset {idx + 1}",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        identity = GuestChatIdentity.objects.get(guest_id=guest_cookie)
        self.assertEqual(identity.total_asks, 3)
        self.assertEqual(identity.daily_asks_used, 3)

        yesterday = timezone.localdate() - timedelta(days=1)
        identity.daily_asks_date = yesterday
        identity.save(update_fields=["daily_asks_date"])

        reopened = self.client.get("/api/chat-ui/")
        self.assertEqual(reopened.status_code, status.HTTP_200_OK)
        self.assertEqual(
            reopened.context["guest_quota_snapshot"]["asks_used"],
            0,
        )
        self.assertEqual(
            reopened.context["guest_quota_snapshot"]["remaining_asks"],
            3,
        )

        next_day_response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "guest next day question",
            },
        )
        self.assertEqual(next_day_response.status_code, status.HTTP_200_OK)
        identity.refresh_from_db()
        self.assertEqual(identity.total_asks, 4)
        self.assertEqual(identity.daily_asks_used, 1)
        self.assertEqual(identity.daily_asks_date, timezone.localdate())

    def test_chat_ui_guest_limit_can_be_disabled_from_admin_settings(self):
        self.client.force_authenticate(user=None)
        RequestQuotaSettings.objects.create(
            guest_limit_enabled=False,
            guest_ask_limit=1,
        )

        for idx in range(4):
            response = self.client.post(
                "/api/chat-ui/",
                data={
                    "action": "ask",
                    "mode": "simple",
                    "message": f"guest unlimited {idx + 1}",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(DISABLE_ALL_QUOTAS=True)
    def test_chat_ui_guest_limit_is_disabled_by_global_quota_switch(self):
        self.client.force_authenticate(user=None)

        for idx in range(5):
            response = self.client.post(
                "/api/chat-ui/",
                data={
                    "action": "ask",
                    "mode": "simple",
                    "message": f"guest quota off {idx + 1}",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        landing = self.client.get("/api/chat-ui/")
        self.assertFalse(landing.context["guest_quota_snapshot"]["limit_enabled"])
        self.assertIsNone(landing.context["guest_quota_snapshot"]["remaining_asks"])

        blocked = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "simple",
                "message": "guest unlimited 5",
            },
        )
        self.assertEqual(blocked.status_code, status.HTTP_200_OK)
        self.assertNotContains(blocked, "used all")
        self.assertContains(blocked, "Guest questions: Unlimited")

    def test_api_free_limit_can_be_disabled_from_admin_settings(self):
        RequestQuotaSettings.objects.create(
            free_limit_enabled=False,
            free_daily_ask_limit=1,
        )

        payload = {
            "message": "I feel anxious about my career growth.",
            "mode": "simple",
        }
        for _ in range(3):
            response = self.client.post("/api/ask/", payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["plan"], "free")
            self.assertIsNone(response.data["daily_limit"])
            self.assertIsNone(response.data["remaining_today"])

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

    def test_chat_ui_plan_update_accepts_plus_for_existing_username(self):
        self._login_chat_ui()
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "plan",
                "selected_plan": "plus",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Plan updated to plus")

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

    def test_chat_ui_recent_prompts_surface_through_thread_list(self):
        self.client.force_authenticate(user=None)
        for idx in range(1, 4):
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
        self.assertContains(response, "recent question 3")
        self.assertContains(response, "recent question 2")
        self.assertContains(response, "recent question 1")

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

    @override_settings(ENABLE_FREE_DEEP_MODE=False)
    def test_chat_ui_mode_selection_persists_across_threads(self):
        self._login_chat_ui()
        subscription, _ = UserSubscription.objects.get_or_create(
            user=self.user,
        )
        subscription.plan = UserSubscription.PLAN_PLUS
        subscription.save(update_fields=["plan"])

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

    @override_settings(ENABLE_FREE_DEEP_MODE=False)
    def test_chat_ui_guest_deep_mode_is_locked(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "ask",
                "mode": "deep",
                "message": "Give me deep guidance for anxiety.",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Deep mode is available on Plus and Pro plans")
        self.assertEqual(response.context["mode"], "simple")

    def test_chat_ui_shows_inr_only_for_india(self):
        self._login_chat_ui()
        response = self.client.get(
            "/api/chat-ui/?language=en",
            HTTP_CF_IPCOUNTRY="IN",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context["billing_currency"], "INR")
        self.assertContains(response, "Plus - ₹")
        self.assertNotContains(response, "Plus - $")

    def test_chat_ui_shows_usd_only_for_non_india(self):
        self._login_chat_ui()
        response = self.client.get(
            "/api/chat-ui/?language=en",
            HTTP_CF_IPCOUNTRY="US",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context["billing_currency"], "USD")
        self.assertContains(response, "Plus - $")
        self.assertNotContains(response, "Plus - ₹")

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

    def test_support_api_saves_ticket(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/support/",
            {
                "name": "Seeker One",
                "email": "seeker@example.com",
                "issue_type": "payment",
                "message": "My payment succeeded but Pro is not active.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SupportTicket.objects.count(), 1)
        ticket = SupportTicket.objects.first()
        self.assertEqual(ticket.issue_type, SupportTicket.ISSUE_PAYMENT)
        self.assertEqual(ticket.requester_id, "guest")

    def test_chat_ui_support_flow_saves_ticket(self):
        self._login_chat_ui()
        response = self.client.post(
            "/api/chat-ui/",
            data={
                "action": "support",
                "mode": "simple",
                "language": "en",
                "support_name": "Demo User",
                "support_email": "demo@example.com",
                "support_issue_type": "account",
                "support_message": "Please help me recover my account.",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Support request submitted")
        self.assertEqual(SupportTicket.objects.count(), 1)
        ticket = SupportTicket.objects.first()
        self.assertEqual(ticket.issue_type, SupportTicket.ISSUE_ACCOUNT)
        self.assertEqual(ticket.requester_id, "demo-user")

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

        detail_response = self.client.get(f"/api/saved-reflections/{saved_id}/")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["id"], saved_id)
        self.assertEqual(
            detail_response.data["message"],
            "I am anxious about career growth.",
        )

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
        self.assertIn("synthesis", response.data)
        self.assertIn("generation_source", response.data["synthesis"])
        self.assertIn("overview_en", response.data["synthesis"])
        self.assertIn("overview_hi", response.data["synthesis"])

    def test_verse_detail_404_for_invalid_verse(self):
        """Test verse detail returns 404 for non-existent verse."""
        response = self.client.get("/api/verses/99.999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "verse_not_found")

    def test_mantra_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/mantra/",
            {"mood": "calm", "language": "en"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

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

    def test_gita_browse_unauthenticated_get_still_works(self):
        """Browser-style requests without a token must load chapter browse data."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/chapters/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("chapters", response.data)

    def test_gita_browse_token_free_plan_forbidden(self):
        """Token clients on Free cannot use chapter/verse browse APIs."""
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
        UserSubscription.objects.update_or_create(
            user=self.user,
            defaults={"plan": UserSubscription.PLAN_FREE},
        )
        response = self.client.get("/api/chapters/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_gita_browse_token_pro_plan_allowed(self):
        """Token clients with Pro may use chapter browse APIs."""
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
        plan_response = self.client.post(
            "/api/auth/plan/",
            {"plan": "pro"},
            format="json",
        )
        self.assertEqual(plan_response.status_code, status.HTTP_200_OK)
        response = self.client.get("/api/chapters/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("chapters", response.data)

    def test_seo_topic_page_includes_faq_schema(self):
        """FAQPage JSON-LD and visible FAQ items appear on SEO topic pages."""
        response = self.client.get("/bhagavad-gita-for-anxiety/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('"@type": "FAQPage"', content)
        self.assertIn("How does the Bhagavad Gita help with anxiety", content)
        # visible FAQ section rendered for Google rich-result eligibility
        self.assertIn("Frequently Asked Questions", content)
        self.assertIn("<details", content)

    def test_shared_answer_create_returns_share_url(self):
        """POST /api/answers/share/ creates a SharedAnswer and returns share_url."""
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/answers/share/",
            data={
                "question": "How do I deal with fear of failure?",
                "guidance": "The Gita teaches detachment from outcomes.",
                "verse_references": ["2.47", "2.48"],
                "language": "en",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("share_url", response.data)
        self.assertIn("share_id", response.data)
        self.assertTrue(response.data["share_url"].startswith("/share/"))
        self.assertEqual(SharedAnswer.objects.count(), 1)

    def test_shared_answer_page_renders_with_og_meta(self):
        """GET /share/<uuid>/ renders the answer card with OG meta."""
        shared = SharedAnswer.objects.create(
            question="What does the Gita say about anxiety?",
            guidance="Act without attachment to results.",
            verse_references=["2.48"],
            language="en",
        )
        response = self.client.get(f"/share/{shared.share_id}/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('property="og:title"', content)
        self.assertIn('property="og:description"', content)
        self.assertIn("What does the Gita say about anxiety?", content)
        self.assertIn("Act without attachment to results.", content)
        self.assertIn("BG 2.48", content)

    def test_shared_answer_page_404_for_unknown_uuid(self):
        """GET /share/<unknown-uuid>/ returns 404."""
        response = self.client.get(
            "/share/00000000-0000-0000-0000-000000000000/"
        )
        self.assertEqual(response.status_code, 404)

    def test_shared_answer_page_legacy_suffix_redirects_to_canonical(self):
        """GET /share/<uuid>/ok redirects to /share/<uuid>/ for compatibility."""
        shared = SharedAnswer.objects.create(
            question="How can I calm my mind?",
            guidance="Practice steady action and non-attachment.",
            verse_references=["2.48"],
            language="en",
        )
        response = self.client.get(
            f"/share/{shared.share_id}/ok/",
            follow=False,
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], f"/share/{shared.share_id}/")


# Razorpay Payment Integration Tests
# =============================================================================


@override_settings(
    DEBUG=True,
    OPENAI_API_KEY="",
    RAZORPAY_KEY_ID="rzp_test_key_12345",
    RAZORPAY_KEY_SECRET="secret_key_67890",
    RAZORPAY_WEBHOOK_SECRET="webhook_secret_key",
    SUBSCRIPTION_PRICE_PLUS_INR=4900,
    SUBSCRIPTION_PRICE_PLUS_USD=149,
    SUBSCRIPTION_PRICE_PRO_INR=9900,
    SUBSCRIPTION_PRICE_PRO_USD=299,
)
class PaymentIntegrationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="payment-user",
            email="paymentuser@test.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.user)

    def test_create_order_inr_flow(self):
        """Test creating a Razorpay order for INR payment."""
        from unittest.mock import patch, MagicMock

        mock_order_response = {
            "id": "order_test_123abc",
            "entity": "order",
            "amount": 9900,
            "currency": "INR",
            "receipt": "sub_test_receipt",
            "status": "created",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "INR"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_id"], "order_test_123abc")
        self.assertEqual(response.data["amount"], 9900)
        self.assertEqual(response.data["currency"], "INR")
        self.assertEqual(response.data["plan"], UserSubscription.PLAN_PRO)
        self.assertEqual(response.data["key_id"], "rzp_test_key_12345")
        self.assertEqual(response.data["user_email"], "paymentuser@test.com")

        # Verify order was stored in subscription
        subscription = UserSubscription.objects.get(user=self.user)
        self.assertEqual(subscription.razorpay_order_id, "order_test_123abc")
        self.assertEqual(subscription.payment_currency, "INR")
        billing_record = BillingRecord.objects.get(
            razorpay_order_id="order_test_123abc",
        )
        self.assertEqual(billing_record.amount_minor, 9900)
        self.assertEqual(
            billing_record.payment_status,
            BillingRecord.STATUS_CREATED,
        )
        self.assertEqual(
            billing_record.tax_treatment,
            BillingRecord.TAX_DOMESTIC,
        )

    def test_create_order_plus_inr_flow(self):
        """Test creating a Razorpay order for Plus INR payment."""
        from unittest.mock import patch, MagicMock

        mock_order_response = {
            "id": "order_plus_inr",
            "entity": "order",
            "amount": 4900,
            "currency": "INR",
            "status": "created",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "INR", "plan": "plus"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_id"], "order_plus_inr")
        self.assertEqual(response.data["amount"], 4900)
        self.assertEqual(response.data["currency"], "INR")
        self.assertEqual(response.data["plan"], UserSubscription.PLAN_PLUS)

    def test_create_order_usd_flow(self):
        """Test creating a Razorpay order for USD payment."""
        from unittest.mock import patch, MagicMock

        mock_order_response = {
            "id": "order_usd_xyz789",
            "entity": "order",
            "amount": 299,
            "currency": "USD",
            "status": "created",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "USD"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_id"], "order_usd_xyz789")
        self.assertEqual(response.data["amount"], 299)
        self.assertEqual(response.data["currency"], "USD")

        # Verify order was stored in subscription
        subscription = UserSubscription.objects.get(user=self.user)
        self.assertEqual(subscription.razorpay_order_id, "order_usd_xyz789")
        self.assertEqual(subscription.payment_currency, "USD")

    def test_create_order_defaults_to_inr(self):
        """Test creating an order without currency defaults to INR."""
        from unittest.mock import patch, MagicMock

        mock_order_response = {
            "id": "order_default_inr",
            "entity": "order",
            "amount": 9900,
            "currency": "INR",
            "status": "created",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["amount"], 9900)
        self.assertEqual(response.data["currency"], "INR")

    def test_create_order_india_header_forces_inr_even_if_usd_requested(self):
        """India requests are billed in INR regardless of client-requested currency."""
        from unittest.mock import patch, MagicMock

        mock_order_response = {
            "id": "order_in_forced_inr",
            "entity": "order",
            "amount": 9900,
            "currency": "INR",
            "status": "created",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "USD"},
                format="json",
                HTTP_CF_IPCOUNTRY="IN",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currency"], "INR")
        self.assertEqual(response.data["amount"], 9900)

    def test_create_order_non_india_header_forces_usd_even_if_inr_requested(self):
        """Non-India requests are billed in USD regardless of client-requested currency."""
        from unittest.mock import patch, MagicMock

        mock_order_response = {
            "id": "order_us_forced_usd",
            "entity": "order",
            "amount": 299,
            "currency": "USD",
            "status": "created",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "INR"},
                format="json",
                HTTP_CF_IPCOUNTRY="US",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currency"], "USD")
        self.assertEqual(response.data["amount"], 299)
        billing_record = BillingRecord.objects.get(
            razorpay_order_id="order_us_forced_usd",
        )
        self.assertEqual(
            billing_record.tax_treatment,
            BillingRecord.TAX_EXPORT_LUT,
        )
        self.assertTrue(billing_record.is_international)

    def test_create_order_persists_billing_profile_fields(self):
        """Checkout should store one invoice-friendly billing ledger row."""
        from unittest.mock import MagicMock, patch

        mock_order_response = {
            "id": "order_billing_profile",
            "entity": "order",
            "amount": 4900,
            "currency": "INR",
            "status": "created",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {
                    "currency": "INR",
                    "plan": "plus",
                    "billing_name": "Rishi Sharma",
                    "billing_email": "accounts@example.com",
                    "business_name": "Gita Guide Labs",
                    "gstin": "29ABCDE1234F1Z5",
                    "billing_country_code": "IN",
                    "billing_country_name": "India",
                    "billing_state": "Karnataka",
                    "billing_city": "Bengaluru",
                    "billing_postal_code": "560001",
                    "billing_address": "MG Road\nBengaluru",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        billing_record = BillingRecord.objects.get(
            razorpay_order_id="order_billing_profile",
        )
        self.assertEqual(billing_record.billing_name, "Rishi Sharma")
        self.assertEqual(billing_record.billing_email, "accounts@example.com")
        self.assertEqual(billing_record.business_name, "Gita Guide Labs")
        self.assertEqual(billing_record.gstin, "29ABCDE1234F1Z5")
        self.assertEqual(billing_record.billing_state, "Karnataka")
        self.assertEqual(billing_record.billing_city, "Bengaluru")

    def test_create_order_india_locale_overrides_non_india_geo(self):
        """India locale hints (en-IN/hi-IN) should keep INR when geo is inaccurate."""
        from unittest.mock import patch, MagicMock

        mock_order_response = {
            "id": "order_in_locale_override",
            "entity": "order",
            "amount": 9900,
            "currency": "INR",
            "status": "created",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "USD"},
                format="json",
                HTTP_CF_IPCOUNTRY="US",
                HTTP_ACCEPT_LANGUAGE="en-IN,en;q=0.9",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currency"], "INR")
        self.assertEqual(response.data["amount"], 9900)

    def test_create_order_unauthenticated_fails(self):
        """Test order creation fails without authentication."""
        self.client.force_authenticate(user=None)

        from unittest.mock import patch

        with patch("razorpay.Client"):
            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "INR"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)

    def test_create_order_gateway_not_configured_fails(self):
        """Test order creation fails when Razorpay credentials are not set."""
        with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=""):
            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "INR"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("error", response.data)

    def test_verify_payment_with_valid_signature(self):
        """Test verifying payment with valid HMAC signature."""
        import hmac
        import hashlib

        # Setup: Create an order first
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_FREE,
        )
        subscription.razorpay_order_id = "order_test_456def"
        subscription.save()

        # Generate valid signature
        order_id = "order_test_456def"
        payment_id = "pay_test_789ghi"
        key_secret = "secret_key_67890"
        msg = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            key_secret.encode(),
            msg.encode(),
            hashlib.sha256
        ).hexdigest()

        # Verify payment with valid signature
        response = self.client.post(
            "/api/payments/verify/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": generated_signature,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("message", response.data)

        # Verify subscription was activated
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_PRO)
        self.assertTrue(subscription.is_active)
        self.assertIsNotNone(subscription.subscription_end_date)
        billing_record = BillingRecord.objects.get(
            razorpay_order_id=order_id,
        )
        self.assertEqual(
            billing_record.payment_status,
            BillingRecord.STATUS_VERIFIED,
        )
        self.assertEqual(billing_record.razorpay_payment_id, payment_id)
        self.assertIsNotNone(billing_record.verified_at)
        # Should be ~30 days from now
        days_diff = (subscription.subscription_end_date - timezone.now()).days
        self.assertGreaterEqual(days_diff, 29)
        self.assertLessEqual(days_diff, 31)

    def test_verify_payment_plus_plan_from_request(self):
        """Test verifying payment can activate plus plan when selected."""
        import hmac
        import hashlib

        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_FREE,
        )
        subscription.razorpay_order_id = "order_plus_456def"
        subscription.save()

        order_id = "order_plus_456def"
        payment_id = "pay_plus_789ghi"
        key_secret = "secret_key_67890"
        msg = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            key_secret.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()

        response = self.client.post(
            "/api/payments/verify/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": generated_signature,
                "plan": "plus",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_PLUS)
        self.assertTrue(subscription.is_active)

    def test_verify_payment_with_invalid_signature_fails(self):
        """Test payment verification fails with invalid signature."""
        # Setup: Create an order first (with is_active=False to test it doesn't change)
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_FREE,
            is_active=False,
        )
        subscription.razorpay_order_id = "order_test_456def"
        subscription.save()

        # Attempt to verify with wrong signature
        response = self.client.post(
            "/api/payments/verify/",
            {
                "razorpay_order_id": "order_test_456def",
                "razorpay_payment_id": "pay_test_789ghi",
                "razorpay_signature": "wrong_signature_xyz",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

        # Subscription should remain unchanged
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_FREE)
        self.assertFalse(subscription.is_active)

    def test_verify_payment_missing_parameters_fails(self):
        """Test payment verification fails when required parameters are missing."""
        response = self.client.post(
            "/api/payments/verify/",
            {
                "razorpay_order_id": "order_123",
                # Missing payment_id and signature
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_verify_payment_order_id_mismatch_fails(self):
        """Test verification fails when order_id doesn't match subscription."""
        import hmac
        import hashlib

        # Setup: Create an order with a different ID
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_FREE,
        )
        subscription.razorpay_order_id = "order_original_123"
        subscription.save()

        # Generate signature for different order_id
        order_id = "order_wrong_456"
        payment_id = "pay_test_789ghi"
        key_secret = "secret_key_67890"
        msg = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            key_secret.encode(),
            msg.encode(),
            hashlib.sha256
        ).hexdigest()

        # Try to verify with mismatched order_id
        response = self.client.post(
            "/api/payments/verify/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": generated_signature,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_verify_payment_unauthenticated_fails(self):
        """Test payment verification fails without authentication."""
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/payments/verify/",
            {
                "razorpay_order_id": "order_test",
                "razorpay_payment_id": "pay_test",
                "razorpay_signature": "sig_test",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)

    def test_razorpay_webhook_payment_captured_event(self):
        """Test webhook correctly handles payment.captured event."""
        import hmac
        import hashlib
        import json

        # Setup: Create subscription with order_id
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_FREE,
        )
        subscription.razorpay_order_id = "order_webhook_123"
        subscription.save()
        BillingRecord.objects.create(
            user=self.user,
            subscription=subscription,
            plan=UserSubscription.PLAN_PRO,
            payment_status=BillingRecord.STATUS_CREATED,
            tax_treatment=BillingRecord.TAX_EXPORT_LUT,
            is_international=True,
            billing_name="Foreign Customer",
            billing_email="billing@example.com",
            billing_country_code="ZA",
            billing_country_name="South Africa",
            currency="USD",
            amount_minor=299,
            amount_major="2.99",
            razorpay_order_id="order_webhook_123",
        )

        # Create webhook payload
        webhook_body = json.dumps({
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_xyz",
                        "order_id": "order_webhook_123",
                        "status": "captured",
                        "amount": 9900,
                    }
                }
            },
        })

        # Generate valid webhook signature
        webhook_secret = "webhook_secret_key"
        webhook_signature = hmac.new(
            webhook_secret.encode(),
            webhook_body.encode(),
            hashlib.sha256
        ).hexdigest()

        # Remove authentication for webhook
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/payments/webhook/",
            webhook_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=webhook_signature,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify subscription was activated
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_PRO)
        self.assertTrue(subscription.is_active)
        billing_record = BillingRecord.objects.get(
            razorpay_order_id="order_webhook_123",
        )
        self.assertEqual(
            billing_record.payment_status,
            BillingRecord.STATUS_CAPTURED,
        )
        self.assertEqual(billing_record.razorpay_payment_id, "pay_webhook_xyz")
        self.assertIsNotNone(billing_record.paid_at)

    def test_razorpay_webhook_payment_failed_event(self):
        """Test webhook correctly handles payment.failed event."""
        import hmac
        import hashlib
        import json

        # Setup: Create subscription
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_FREE,
        )
        subscription.razorpay_order_id = "order_failed_123"
        subscription.save()
        BillingRecord.objects.create(
            user=self.user,
            subscription=subscription,
            plan=UserSubscription.PLAN_PLUS,
            payment_status=BillingRecord.STATUS_CREATED,
            tax_treatment=BillingRecord.TAX_DOMESTIC,
            billing_name="Indian User",
            billing_email="user@example.com",
            billing_country_code="IN",
            billing_country_name="India",
            currency="INR",
            amount_minor=4900,
            amount_major="49.00",
            razorpay_order_id="order_failed_123",
        )

        # Create webhook payload for failed payment
        webhook_body = json.dumps({
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_failed_xyz",
                        "order_id": "order_failed_123",
                        "status": "failed",
                    }
                }
            },
        })

        # Generate valid webhook signature
        webhook_secret = "webhook_secret_key"
        webhook_signature = hmac.new(
            webhook_secret.encode(),
            webhook_body.encode(),
            hashlib.sha256
        ).hexdigest()

        # Remove authentication for webhook
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/payments/webhook/",
            webhook_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=webhook_signature,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Subscription should remain unchanged
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_FREE)
        billing_record = BillingRecord.objects.get(
            razorpay_order_id="order_failed_123",
        )
        self.assertEqual(
            billing_record.payment_status,
            BillingRecord.STATUS_FAILED,
        )

    def test_payment_status_endpoint_marks_cancelled_without_downgrading_success(self):
        """Client cancellation should be cancelled; captured rows remain captured."""
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_FREE,
        )
        BillingRecord.objects.create(
            user=self.user,
            subscription=subscription,
            plan=UserSubscription.PLAN_PLUS,
            payment_status=BillingRecord.STATUS_CREATED,
            tax_treatment=BillingRecord.TAX_DOMESTIC,
            billing_name="Indian User",
            billing_email="user@example.com",
            billing_country_code="IN",
            billing_country_name="India",
            currency="INR",
            amount_minor=4900,
            amount_major="49.00",
            razorpay_order_id="order_cancel_123",
        )

        cancelled = self.client.post(
            "/api/payments/status/",
            {
                "order_id": "order_cancel_123",
                "status": "cancelled",
                "reason": "checkout_cancelled",
            },
            format="json",
        )
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        row = BillingRecord.objects.get(razorpay_order_id="order_cancel_123")
        self.assertEqual(row.payment_status, BillingRecord.STATUS_CANCELLED)

        row.payment_status = BillingRecord.STATUS_CAPTURED
        row.save(update_fields=["payment_status"])
        second = self.client.post(
            "/api/payments/status/",
            {
                "order_id": "order_cancel_123",
                "status": "cancelled",
                "reason": "late_cancel",
            },
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        row.refresh_from_db()
        self.assertEqual(row.payment_status, BillingRecord.STATUS_CAPTURED)

    def test_razorpay_webhook_invalid_signature_rejected(self):
        """Test webhook request with invalid signature is rejected."""
        import json

        webhook_body = json.dumps({
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test",
                        "order_id": "order_test",
                        "status": "captured",
                    }
                }
            },
        })

        # Remove authentication for webhook
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/payments/webhook/",
            webhook_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="invalid_signature",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_razorpay_webhook_webhook_secret_not_configured_fails(self):
        """Test webhook request fails when webhook secret is not configured."""
        import json

        with override_settings(RAZORPAY_WEBHOOK_SECRET=""):
            webhook_body = json.dumps({"event": "payment.captured"})

            # Remove authentication for webhook
            self.client.force_authenticate(user=None)

            response = self.client.post(
                "/api/payments/webhook/",
                webhook_body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE="any_sig",
            )

            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertIn("error", response.data)

    def test_razorpay_webhook_invalid_json_handled(self):
        """Test webhook gracefully handles invalid JSON."""
        import hmac
        import hashlib

        webhook_body = "not valid json {"
        webhook_secret = "webhook_secret_key"
        webhook_signature = hmac.new(
            webhook_secret.encode(),
            webhook_body.encode(),
            hashlib.sha256
        ).hexdigest()

        # Remove authentication for webhook
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/payments/webhook/",
            webhook_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=webhook_signature,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_subscription_status_free_plan(self):
        """Test subscription status endpoint returns free plan data."""
        # User starts with free plan
        response = self.client.get("/api/subscription/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"], UserSubscription.PLAN_FREE)
        self.assertFalse(response.data["is_pro"])
        self.assertIsNone(response.data["subscription_end_date"])
        self.assertIn("pricing", response.data)
        self.assertEqual(response.data["pricing"]["INR"], 9900)
        self.assertEqual(response.data["pricing"]["USD"], 299)
        self.assertEqual(response.data["pricing"]["plans"]["plus"]["INR"], 4900)
        self.assertEqual(response.data["pricing"]["plans"]["plus"]["USD"], 149)
        self.assertEqual(response.data["pricing"]["plans"]["pro"]["INR"], 9900)
        self.assertEqual(response.data["pricing"]["plans"]["pro"]["USD"], 299)
        self.assertIsNone(response.data["latest_billing_record"])

    def test_subscription_status_pro_plan_active(self):
        """Test subscription status endpoint returns pro plan data when active."""
        # Activate user's pro plan
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_PRO,
            is_active=True,
            subscription_end_date=timezone.now() + timedelta(days=15),
        )

        response = self.client.get("/api/subscription/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"], UserSubscription.PLAN_PRO)
        self.assertTrue(response.data["is_pro"])
        self.assertIsNotNone(response.data["subscription_end_date"])

    def test_subscription_status_includes_latest_billing_record(self):
        """Subscription status should expose the latest billing ledger row."""
        BillingRecord.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_PLUS,
            payment_status=BillingRecord.STATUS_CAPTURED,
            tax_treatment=BillingRecord.TAX_DOMESTIC,
            billing_name="Rishi Sharma",
            billing_email="accounts@example.com",
            billing_country_code="IN",
            billing_country_name="India",
            currency="INR",
            amount_minor=4900,
            amount_major="49.00",
            razorpay_order_id="order_status_latest",
            razorpay_payment_id="pay_status_latest",
        )

        response = self.client.get("/api/subscription/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["latest_billing_record"])
        self.assertEqual(
            response.data["latest_billing_record"]["razorpay_order_id"],
            "order_status_latest",
        )
        self.assertEqual(
            response.data["latest_billing_record"]["payment_status"],
            BillingRecord.STATUS_CAPTURED,
        )

    def test_subscription_status_pro_plan_expired(self):
        """Expired paid subscriptions should auto-downgrade to free."""
        # Create expired pro subscription
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_PRO,
            is_active=True,
            subscription_end_date=timezone.now() - timedelta(days=5),  # Expired
        )

        response = self.client.get("/api/subscription/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"], UserSubscription.PLAN_FREE)
        self.assertFalse(response.data["is_pro"])
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_FREE)
        self.assertFalse(subscription.is_active)
        self.assertIsNone(subscription.subscription_end_date)

    def test_subscription_status_unauthenticated_fails(self):
        """Test subscription status endpoint fails without authentication."""
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/subscription/status/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)

    def test_payment_history_returns_latest_rows(self):
        """Signed-in users should be able to inspect payment ledger history."""
        BillingRecord.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_PLUS,
            payment_status=BillingRecord.STATUS_VERIFIED,
            tax_treatment=BillingRecord.TAX_DOMESTIC,
            billing_name="Demo User",
            billing_email="demo@example.com",
            billing_country_code="IN",
            billing_country_name="India",
            currency="INR",
            amount_minor=4900,
            amount_major="49.00",
            razorpay_order_id="order_history_1",
        )
        BillingRecord.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_PRO,
            payment_status=BillingRecord.STATUS_CAPTURED,
            tax_treatment=BillingRecord.TAX_EXPORT_LUT,
            billing_name="Demo User",
            billing_email="demo@example.com",
            billing_country_code="ZA",
            billing_country_name="South Africa",
            currency="USD",
            amount_minor=299,
            amount_major="2.99",
            razorpay_order_id="order_history_2",
            razorpay_payment_id="pay_history_2",
        )

        response = self.client.get("/api/payments/history/?limit=10&offset=0")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(
            response.data["results"][0]["razorpay_order_id"],
            "order_history_2",
        )
        self.assertEqual(
            response.data["results"][1]["razorpay_order_id"],
            "order_history_1",
        )

    def test_payment_history_requires_authentication(self):
        """Guests should not be able to inspect payment ledger rows."""
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/payments/history/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)

    def test_create_order_includes_user_details_in_response(self):
        """Test create order response includes user name and email."""
        from unittest.mock import patch, MagicMock

        mock_order_response = {
            "id": "order_user_details",
            "entity": "order",
            "amount": 9900,
            "currency": "INR",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "INR"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user_email"], "paymentuser@test.com")
        self.assertEqual(response.data["user_name"], "payment-user")

    def test_payment_endpoints_prefer_chat_ui_session_user_over_stale_request_user(self):
        """Payment/session APIs should follow the visible chat-ui user account."""
        from unittest.mock import patch, MagicMock

        admin_user = User.objects.create_user(
            username="admin",
            password="admin-pass-123",
            email="admin@example.com",
        )
        UserSubscription.objects.create(
            user=admin_user,
            plan=UserSubscription.PLAN_FREE,
        )
        test_subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_PLUS,
            is_active=True,
            subscription_end_date=timezone.now() + timedelta(days=30),
        )

        self.client.force_authenticate(user=admin_user)
        session = self.client.session
        session["chat_ui_auth_username"] = self.user.username
        session.save()

        status_response = self.client.get("/api/subscription/status/")
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data["plan"], UserSubscription.PLAN_PLUS)

        mock_order_response = {
            "id": "order_session_priority",
            "entity": "order",
            "amount": 19900,
            "currency": "INR",
        }
        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            create_response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "INR", "plan": "plus"},
                format="json",
            )

        self.assertEqual(create_response.status_code, status.HTTP_200_OK)
        self.assertEqual(create_response.data["user_email"], self.user.email)
        self.assertEqual(
            create_response.data["user_name"],
            self.user.get_full_name() or self.user.username,
        )
        test_subscription.refresh_from_db()
        self.assertEqual(
            test_subscription.razorpay_order_id,
            mock_order_response["id"],
        )
        self.assertEqual(test_subscription.payment_currency, "INR")
        self.assertFalse(
            UserSubscription.objects.get(user=admin_user).razorpay_order_id,
        )

    def test_payment_flow_end_to_end(self):
        """Test complete payment flow from order creation to subscription activation."""
        import hmac
        import hashlib
        from unittest.mock import patch, MagicMock

        # Step 1: Create order
        mock_order_response = {
            "id": "order_e2e_123",
            "entity": "order",
            "amount": 9900,
            "currency": "INR",
        }

        with patch("razorpay.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.order.create.return_value = mock_order_response

            response = self.client.post(
                "/api/payments/create-order/",
                {"currency": "INR"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order_id = response.data["order_id"]

        # Step 2: Verify subscription was created with order_id
        subscription = UserSubscription.objects.get(user=self.user)
        self.assertEqual(subscription.razorpay_order_id, order_id)
        self.assertEqual(subscription.plan, UserSubscription.PLAN_FREE)

        # Step 3: Simulate user payment and signature verification
        payment_id = "pay_e2e_xyz"
        msg = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            "secret_key_67890".encode(),
            msg.encode(),
            hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            "/api/payments/verify/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": generated_signature,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

        # Step 4: Verify subscription is now pro
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_PRO)
        self.assertTrue(subscription.is_active)

        # Step 5: Check subscription status
        response = self.client.get("/api/subscription/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_pro"])


class GuidanceGroundingTests(TestCase):
    """Unit tests for verse grounding helpers (no OpenAI)."""

    def test_verse_optional_allows_empty_refs_without_numeric_citations(self):
        self.assertTrue(
            _is_grounded_response(
                "Act with truth and steadiness.",
                "Clarity grows when fear does not steer you.",
                [],
                set(),
                verse_optional=True,
            ),
        )

    def test_verse_optional_rejects_numeric_citations_in_prose(self):
        self.assertFalse(
            _is_grounded_response(
                "As 2.47 says, stay steady.",
                "",
                [],
                set(),
                verse_optional=True,
            ),
        )

    def test_professional_ethics_query_detects_lawyer(self):
        self.assertTrue(
            _is_professional_ethics_query(
                "I am a lawyer unsure about representing this client.",
            ),
        )

    def test_professional_ethics_query_detects_laywer_typo(self):
        self.assertTrue(
            _is_professional_ethics_query(
                "I am laywer and conflicted about my case.",
            ),
        )

    def test_what_should_i_do_routes_life_guidance_not_knowledge(self):
        intent = classify_user_intent(
            "i am laywer , i know that the person whose case i am fighting for is "
            "wrong . what should i do",
        )
        self.assertEqual(intent.intent_type, "life_guidance")

    def test_first_person_questions_route_to_life_not_knowledge(self):
        intent = classify_user_intent("Why am I so sad lately?")
        self.assertEqual(intent.intent_type, "life_guidance")

    def test_scriptural_topic_question_stays_knowledge(self):
        intent = classify_user_intent(
            "What does the Bhagavad Gita say about karma yoga?",
        )
        self.assertEqual(intent.intent_type, "knowledge_question")

    def test_normalize_chat_strips_leading_you_i_prefix(self):
        self.assertEqual(
            normalize_chat_user_message(
                "You i am laywer , what should i do",
            ),
            "i am laywer , what should i do",
        )

    def test_professional_ethics_detects_fighting_for_case(self):
        self.assertTrue(
            _is_professional_ethics_query(
                "I am fighting for someone whose case feels wrong to me. What should I do?",
            ),
        )

    def test_professional_ethics_not_triggered_by_counselling_word(self):
        self.assertFalse(
            _is_professional_ethics_query(
                "I am seeking counselling for anxiety and need guidance.",
            ),
        )

    def test_professional_ethics_not_triggered_by_in_my_case_idiom(self):
        self.assertFalse(
            _is_professional_ethics_query(
                "In my case I prefer to study at night; what does the Gita say about discipline?",
            ),
        )

    def test_professional_ethics_not_triggered_by_freelance_clients(self):
        self.assertFalse(
            _is_professional_ethics_query(
                "My clients keep changing requirements at work and I feel drained.",
            ),
        )

    def test_short_gratitude_like_phrase(self):
        self.assertTrue(_is_short_gratitude_like("well thank you everyone"))

    @override_settings(OPENAI_API_KEY="")
    def test_thank_you_message_gets_welcome_not_ethics_fallback(self):
        result = build_guidance("well thank you everyone", verses=[], language="en")
        self.assertIn("welcome", result.guidance.lower())
        self.assertNotIn("legal advice", result.guidance.lower())

    def test_empty_verse_fallback_without_ethics_is_not_principle_only_stub(self):
        result = _build_fallback_guidance(
            "I feel anxious about my exams next week",
            [],
            language="en",
            honor_empty_verse_context=True,
        )
        self.assertNotIn("legal advice", result.guidance.lower())

    def test_integrity_theme_for_professional_ethics_language(self):
        themes = infer_themes_from_text(
            "As a lawyer I face an ethical conflict between loyalty and truth.",
        )
        self.assertIn("integrity", themes)

    def test_interpret_query_maps_integrity_to_life_domain(self):
        q = interpret_query("Court ethics: my client may be lying; what is my dharma?")
        self.assertIn("integrity", q.life_domain.lower())

    def test_query_embedding_text_includes_interpretation(self):
        text = query_embedding_input_text("I feel anxious before every exam.")
        self.assertIn("Life domain:", text)
        self.assertIn("inner stability", text.lower())

    @override_settings(OPENAI_QUERY_EMBEDDING_ENRICHED=False)
    def test_query_embedding_plain_mode_uses_normalized_message_only(self):
        text = query_embedding_input_text("  You i am worried  ")
        self.assertEqual(text, "i am worried")

    @override_settings(
        OPENAI_API_KEY="sk-test-key",
        OPENAI_QUERY_EMBEDDING_CACHE_ENABLED=True,
        OPENAI_QUERY_EMBEDDING_CACHE_TTL_SECONDS=3600,
    )
    def test_query_embedding_cache_reuses_vector_without_second_api_call(self):
        cache.clear()
        fake_emb = [0.25, 0.5, 0.75]
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(embedding=fake_emb)]

        with patch("guide_api.services._openai_client") as mock_client:
            mock_client.return_value.embeddings.create.return_value = mock_resp
            first = _build_query_embedding("same retrieval question")
            second = _build_query_embedding("same retrieval question")
            self.assertEqual(first, fake_emb)
            self.assertEqual(second, fake_emb)
            self.assertEqual(mock_client.return_value.embeddings.create.call_count, 1)

    def test_serialize_conversation_context_respects_char_cap(self):
        class _Msg:
            def __init__(self, role, content):
                self.role = role
                self.content = content

        long_line = "x" * 500
        msgs = [
            _Msg("user", f"old {long_line}"),
            _Msg("assistant", f"mid {long_line}"),
            _Msg("user", "keep this tail"),
        ]
        with override_settings(MAX_CONVERSATION_CONTEXT_TURNS=6, MAX_CONVERSATION_CONTEXT_CHARS=120):
            out = _serialize_conversation_context(msgs)
            self.assertLessEqual(len(out), 120)
            self.assertIn("keep this tail", out)


class ParseJsonPayloadTests(TestCase):
    """Local LLMs often wrap JSON in markdown; parsing must stay tolerant."""

    def test_plain_object(self):
        self.assertEqual(_parse_json_payload('{"a": 1}'), {"a": 1})

    def test_markdown_fence_json(self):
        text = '```json\n{"guidance": "hello", "meaning": "there"}\n```'
        out = _parse_json_payload(text)
        self.assertEqual(out["guidance"], "hello")

    def test_prose_intro_then_fence(self):
        text = 'Sure!\n```json\n{"x": 1, "y": 2}\n```\n'
        self.assertEqual(_parse_json_payload(text)["y"], 2)

    def test_nested_braces_inside_string_value(self):
        text = '{"k": "brace { inside }", "n": 3}'
        self.assertEqual(_parse_json_payload(text)["n"], 3)

    def test_raises_when_no_object(self):
        with self.assertRaises(ValueError):
            _parse_json_payload("no json here")


class CommunityApiTests(APITestCase):
    """Public Path thread posts and replies."""

    def setUp(self):
        user_model = get_user_model()
        self.user_a = user_model.objects.create_user(
            "comm_a",
            "comm_a_pass_12",
        )
        self.user_b = user_model.objects.create_user(
            "comm_b",
            "comm_b_pass_12",
        )
        self.staff = user_model.objects.create_user(
            "comm_staff",
            "comm_st_pass_12",
            is_staff=True,
        )

    def test_community_wall_page_renders(self):
        response = self.client.get("/community/?language=en")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Comments & replies")

    def test_community_list_get_anonymous_empty(self):
        response = self.client.get("/api/community/posts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_community_post_requires_auth(self):
        response = self.client.post(
            "/api/community/posts/",
            {"body": "Hello path"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_community_create_reply_edit_delete_flow(self):
        self.client.force_authenticate(self.user_a)
        root = self.client.post(
            "/api/community/posts/",
            {"body": "Root message"},
            format="json",
        )
        self.assertEqual(root.status_code, status.HTTP_201_CREATED)
        root_id = root.data["id"]

        self.client.force_authenticate(self.user_b)
        reply = self.client.post(
            "/api/community/posts/",
            {"body": "Reply text", "parent_id": root_id},
            format="json",
        )
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)

        deep = self.client.post(
            "/api/community/posts/",
            {"body": "Too deep", "parent_id": reply.data["id"]},
            format="json",
        )
        self.assertEqual(deep.status_code, status.HTTP_400_BAD_REQUEST)

        listing = self.client.get("/api/community/posts/")
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(len(listing.data["results"][0]["replies"]), 1)

        self.client.force_authenticate(self.user_a)
        forbidden = self.client.patch(
            f"/api/community/posts/{reply.data['id']}/",
            {"body": "hijack"},
            format="json",
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.staff)
        ok_edit = self.client.patch(
            f"/api/community/posts/{reply.data['id']}/",
            {"body": "Staff edit"},
            format="json",
        )
        self.assertEqual(ok_edit.status_code, status.HTTP_200_OK)
        self.assertEqual(ok_edit.data["body"], "Staff edit")

        self.client.force_authenticate(self.user_a)
        deleted = self.client.delete(f"/api/community/posts/{root_id}/")
        self.assertEqual(deleted.status_code, status.HTTP_200_OK)

        empty = self.client.get("/api/community/posts/")
        self.assertEqual(empty.data["count"], 0)
        self.assertFalse(
            CommunityPost.objects.filter(
                pk=reply.data["id"],
                deleted_at__isnull=True,
            ).exists(),
        )


class SadhanaApiTests(APITestCase):
    """Guided sadhana REST surface (shared with native clients)."""

    def setUp(self):
        self.program = SadhanaProgram.objects.create(
            slug="elevate-daily",
            title="Elevate Daily",
            description="Warm-up → breath → mantra.",
            duration_days=3,
            is_published=True,
            free_sample_day_number=1,
        )
        day1 = SadhanaDay.objects.create(
            program=self.program,
            day_number=1,
            title="Day 1 — Orientation",
        )
        SadhanaStep.objects.create(
            day=day1,
            sequence=1,
            step_type=SadhanaStep.STEP_MANTRA,
            title="Listen",
            instructions="Sit comfortably.",
        )

    def test_programs_list_public(self):
        response = self.client.get("/api/sadhana/programs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 1)

    def test_free_day_detail_includes_steps(self):
        response = self.client.get(
            "/api/sadhana/programs/elevate-daily/days/1/",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(len(payload["steps"]), 1)

    def test_complete_requires_sign_in(self):
        response = self.client.post(
            "/api/sadhana/programs/elevate-daily/days/1/complete/",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_practice_hub_page_renders(self):
        response = self.client.get("/practice/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Daily Sadhana")


class CourseStudioWebTests(TestCase):
    """Staff-only course preparation UI."""

    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            "course-studio-staff",
            "staff-course@test.example",
            "test-pass-xyz",
            is_staff=True,
        )
        self.normal_user = user_model.objects.create_user(
            "course-studio-user",
            "user-course@test.example",
            "test-pass-xyz",
            is_staff=False,
        )

    def test_anonymous_redirects_to_login(self):
        client = Client()
        response = client.get("/staff/course-studio/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_gets_course_studio(self):
        client = Client()
        client.force_login(self.staff_user)
        response = client.get("/staff/course-studio/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course studio")

    def test_non_staff_forbidden(self):
        client = Client()
        client.force_login(self.normal_user)
        response = client.get("/staff/course-studio/")
        self.assertEqual(response.status_code, 403)


class PushReminderHelpersTests(TestCase):
    def test_zoneinfo_ist_maps_to_kolkata(self):
        tz = zoneinfo_for_reminder_timezone("IST")
        self.assertEqual(str(tz), "Asia/Kolkata")

    def test_is_expo_push_token(self):
        self.assertTrue(is_expo_push_token("ExponentPushToken[abc]"))
        self.assertFalse(is_expo_push_token("fcm-raw"))

    def test_is_within_reminder_window_same_calendar_day(self):
        tz = ZoneInfo("UTC")
        now = datetime(2026, 4, 25, 8, 5, tzinfo=tz)
        self.assertTrue(is_within_reminder_window(now, time(8, 0), 15))
        self.assertFalse(is_within_reminder_window(now, time(9, 0), 15))

    def test_is_within_reminder_window_cross_midnight(self):
        tz = ZoneInfo("UTC")
        now = datetime(2026, 4, 25, 0, 2, tzinfo=tz)
        self.assertTrue(is_within_reminder_window(now, time(23, 50), 15))


class PushReminderRunTests(TestCase):
    def test_send_push_reminders_command_dry_run(self):
        from io import StringIO

        buf = StringIO()
        call_command("send_push_reminders", "--dry-run", stdout=buf)
        out = buf.getvalue()
        self.assertIn("due_users=", out)

    def test_run_push_reminders_dry_run_counts(self):
        user = User.objects.create_user("push-dry", password="x")
        p, _ = UserEngagementProfile.objects.get_or_create(user=user)
        p.reminder_enabled = True
        p.preferred_channel = UserEngagementProfile.CHANNEL_PUSH
        p.reminder_time = time(8, 0)
        p.timezone = "UTC"
        p.save()
        NotificationDevice.objects.create(
            user=user,
            token="ExponentPushToken[dryrun]",
            platform=NotificationDevice.PLATFORM_ANDROID,
        )
        now_utc = datetime(2026, 4, 25, 8, 5, tzinfo=ZoneInfo("UTC"))
        stats = run_push_reminders(dry_run=True, now_utc=now_utc, window_minutes=15)
        self.assertEqual(stats["due_users"], 1)
        self.assertEqual(stats["due_messages"], 1)

    def test_run_push_reminders_skips_already_sent_today(self):
        user = User.objects.create_user("push-skip", password="x")
        p, _ = UserEngagementProfile.objects.get_or_create(user=user)
        p.reminder_enabled = True
        p.preferred_channel = UserEngagementProfile.CHANNEL_PUSH
        p.reminder_time = time(8, 0)
        p.timezone = "UTC"
        p.last_reminder_push_date = date(2026, 4, 25)
        p.save()
        NotificationDevice.objects.create(
            user=user,
            token="ExponentPushToken[skipme]",
            platform=NotificationDevice.PLATFORM_ANDROID,
        )
        now_utc = datetime(2026, 4, 25, 8, 5, tzinfo=ZoneInfo("UTC"))
        stats = run_push_reminders(dry_run=True, now_utc=now_utc, window_minutes=15)
        self.assertEqual(stats["due_users"], 0)

    def test_run_push_reminders_ist_one_minute_after_reminder_due(self):
        """IST maps to Asia/Kolkata; window is [17:40, 17:55) local."""
        user = User.objects.create_user("push-ist", password="x")
        p, _ = UserEngagementProfile.objects.get_or_create(user=user)
        p.reminder_enabled = True
        p.preferred_channel = UserEngagementProfile.CHANNEL_PUSH
        p.reminder_time = time(17, 40)
        p.timezone = "IST"
        p.save()
        NotificationDevice.objects.create(
            user=user,
            token="ExponentPushToken[istdue]",
            platform=NotificationDevice.PLATFORM_ANDROID,
        )
        # 17:41 IST = 12:11 UTC on 2026-04-25 (India has no DST)
        now_utc = datetime(2026, 4, 25, 12, 11, tzinfo=ZoneInfo("UTC"))
        stats = run_push_reminders(dry_run=True, now_utc=now_utc, window_minutes=15)
        self.assertEqual(stats["due_users"], 1)

    def test_run_push_reminders_not_due_one_minute_before_reminder(self):
        """17:39 local for a 17:40 reminder is outside the delivery window."""
        user = User.objects.create_user("push-early", password="x")
        p, _ = UserEngagementProfile.objects.get_or_create(user=user)
        p.reminder_enabled = True
        p.preferred_channel = UserEngagementProfile.CHANNEL_PUSH
        p.reminder_time = time(17, 40)
        p.timezone = "IST"
        p.save()
        NotificationDevice.objects.create(
            user=user,
            token="ExponentPushToken[early]",
            platform=NotificationDevice.PLATFORM_ANDROID,
        )
        now_utc = datetime(2026, 4, 25, 12, 9, tzinfo=ZoneInfo("UTC"))
        stats = run_push_reminders(dry_run=True, now_utc=now_utc, window_minutes=15)
        self.assertEqual(stats["due_users"], 0)

    def test_expo_fields_for_daily_reminder_has_signal_shape(self):
        user = User.objects.create_user("push-fields", password="x")
        p, _ = UserEngagementProfile.objects.get_or_create(user=user)
        p.reminder_language = "en"
        p.save()
        fields = _expo_fields_for_daily_reminder(
            profile=p,
            local_date=date(2026, 4, 25),
        )
        self.assertIn("title", fields)
        self.assertIn("body", fields)
        self.assertGreater(len(fields["title"]), 3)
        self.assertGreater(len(fields["body"]), 3)
        data = fields.get("data") or {}
        self.assertEqual(data.get("type"), "daily_reminder")
        if data.get("verseRef"):
            self.assertRegex(str(data["verseRef"]), r"^\d+\.\d+$")
