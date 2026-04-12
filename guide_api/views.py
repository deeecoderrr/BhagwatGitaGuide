"""HTTP views for chat, retrieval evaluation, and feedback flows."""

from datetime import timedelta
import json
import logging
from random import Random
from types import SimpleNamespace
from urllib.parse import quote_plus
from uuid import uuid4

from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.timesince import timesince
from django.views import View
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView

from guide_api.models import (
    AskEvent,
    Conversation,
    DailyAskUsage,
    EngagementEvent,
    FollowUpEvent,
    GuestChatIdentity,
    Message,
    RequestQuotaSettings,
    ResponseFeedback,
    SavedReflection,
    SupportTicket,
    UserEngagementProfile,
    UserSubscription,
    Verse,
)
from guide_api.serializers import (
    AskRequestSerializer,
    ChapterDetailSerializer,
    ChapterListSerializer,
    CommentarySerializer,
    EngagementProfileUpdateSerializer,
    FollowUpRequestSerializer,
    LoginRequestSerializer,
    MantraRequestSerializer,
    MessageSerializer,
    PlanUpdateRequestSerializer,
    QuoteArtRequestSerializer,
    QuoteArtResponseSerializer,
    RegisterRequestSerializer,
    RetrievalEvalRequestSerializer,
    SavedReflectionCreateSerializer,
    SavedReflectionSerializer,
    SupportRequestSerializer,
    VerseDetailSerializer,
    VerseSerializer,
)
from guide_api.services import (
    build_guidance,
    generate_quote_art_data,
    get_all_chapters,
    get_chapter_detail,
    get_chapter_verses,
    get_featured_quotes,
    get_mantra_for_mood,
    get_quote_art_styles,
    get_verse_detail,
    is_risky_prompt,
    retrieve_hybrid_verses_with_trace,
    retrieve_verses,
    retrieve_semantic_verses_with_trace,
    retrieve_verses_with_trace,
)


logger = logging.getLogger(__name__)


def _run_guidance_flow(
    *,
    user_id: str,
    message: str,
    mode: str,
    language: str = "en",
    conversation_id: int | None = None,
):
    """Run end-to-end ask pipeline and persist conversation messages."""
    if conversation_id:
        conversation = Conversation.objects.filter(
            id=conversation_id,
            user_id=user_id,
        ).first()
    else:
        conversation = None

    if conversation is None:
        conversation = Conversation.objects.create(user_id=user_id)

    Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_USER,
        content=message,
    )

    conversation_messages = list(conversation.messages.order_by("created_at"))
    retrieval = retrieve_verses_with_trace(
        message=message,
        limit=4 if mode == "deep" else 3,
    )
    verses = retrieval.verses
    guidance = build_guidance(
        message,
        verses,
        conversation_messages=conversation_messages,
        language=language,
        query_interpretation=retrieval.query_interpretation,
    )

    Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_ASSISTANT,
        content=guidance.guidance,
    )

    # Update conversation's updated_at timestamp so it appears at top of list
    conversation.save()

    return conversation, verses, guidance, retrieval


SEO_LANDING_PAGES = {
    "anxiety": {
        "slug": "bhagavad-gita-for-anxiety",
        "topic_label": "Anxiety",
        "topic_label_hi": "चिंता",
        "title": "Bhagavad Gita for Anxiety | Verse-Based Guidance for Fear and Overthinking",
        "title_hi": "चिंता के लिए भगवद गीता | भय और ओवरथिंकिंग के लिए श्लोक-आधारित मार्गदर्शन",
        "description": (
            "Find Bhagavad Gita guidance for anxiety, fear, and overthinking with relevant verses, "
            "practical meaning, and a clear next step."
        ),
        "description_hi": (
            "चिंता, भय और ओवरथिंकिंग के लिए प्रासंगिक श्लोक, व्यावहारिक अर्थ और स्पष्ट अगले कदम के साथ "
            "भगवद गीता मार्गदर्शन पाएँ।"
        ),
        "hero_title": "Bhagavad Gita For Anxiety And Overthinking",
        "hero_title_hi": "चिंता और ओवरथिंकिंग के लिए भगवद गीता",
        "hero_body": (
            "If your mind is restless, fearful, or constantly running toward the future, the Gita offers "
            "a calmer way to see the problem. This page helps you start with relevant teachings and then "
            "ask your exact question inside the app."
        ),
        "hero_body_hi": (
            "यदि मन बेचैन है, भय में है, या लगातार भविष्य की ओर भाग रहा है, तो गीता समस्या को देखने का "
            "एक शांत दृष्टिकोण देती है। यह पेज आपको प्रासंगिक शिक्षाओं से शुरुआत करने और फिर ऐप में अपना "
            "सटीक प्रश्न पूछने में मदद करता है।"
        ),
        "problem_points": [
            "future fear and uncertainty",
            "overthinking every outcome",
            "difficulty staying steady in the present",
        ],
        "problem_points_hi": [
            "भविष्य का भय और अनिश्चितता",
            "हर परिणाम के बारे में अधिक सोचना",
            "वर्तमान में स्थिर रहना कठिन होना",
        ],
        "verse_refs": ["2.48", "6.5", "2.14"],
        "starter_question": "I feel anxious about my future and overthink everything. What does the Gita say?",
        "starter_question_hi": "मुझे अपने भविष्य को लेकर चिंता है और मैं हर बात को लेकर बहुत सोचता हूँ। गीता क्या कहती है?",
    },
    "career": {
        "slug": "bhagavad-gita-for-career-confusion",
        "topic_label": "Career Confusion",
        "topic_label_hi": "करियर उलझन",
        "title": "Bhagavad Gita for Career Confusion | Guidance for Work, Purpose, and Direction",
        "title_hi": "करियर उलझन के लिए भगवद गीता | काम, उद्देश्य और दिशा के लिए मार्गदर्शन",
        "description": (
            "Explore Bhagavad Gita guidance for career confusion, uncertainty, and purpose with relevant "
            "verses and a practical next step."
        ),
        "description_hi": (
            "करियर उलझन, अनिश्चितता और उद्देश्य के लिए प्रासंगिक श्लोकों और व्यावहारिक अगले कदम के साथ "
            "भगवद गीता मार्गदर्शन देखें।"
        ),
        "hero_title": "Bhagavad Gita For Career Confusion And Direction",
        "hero_title_hi": "करियर उलझन और दिशा के लिए भगवद गीता",
        "hero_body": (
            "When you feel torn between pressure, purpose, and fear of failure, the Gita can help you "
            "separate sincere action from anxious attachment. Start with these verses, then ask about your own situation."
        ),
        "hero_body_hi": (
            "जब आप दबाव, उद्देश्य और असफलता के भय के बीच उलझे हों, तो गीता आपको ईमानदार कर्म और चिंतित "
            "आसक्ति के बीच अंतर समझने में मदद करती है। इन श्लोकों से शुरुआत करें, फिर अपनी स्थिति पूछें।"
        ),
        "problem_points": [
            "uncertainty about what path to choose",
            "fear of failure or comparison",
            "working hard without inner clarity",
        ],
        "problem_points_hi": [
            "कौन-सा रास्ता चुनें इस पर अनिश्चितता",
            "असफलता या तुलना का भय",
            "भीतर की स्पष्टता के बिना मेहनत करना",
        ],
        "verse_refs": ["2.47", "3.35", "18.47"],
        "starter_question": "I feel confused about my career path and future. What should I do next?",
        "starter_question_hi": "मैं अपने करियर और भविष्य को लेकर उलझन में हूँ। मुझे अगला कदम क्या लेना चाहिए?",
    },
    "relationships": {
        "slug": "bhagavad-gita-for-relationships",
        "topic_label": "Relationships",
        "topic_label_hi": "रिश्ते",
        "title": "Bhagavad Gita for Relationships | Guidance for Anger, Attachment, and Love",
        "title_hi": "रिश्तों के लिए भगवद गीता | क्रोध, आसक्ति और प्रेम के लिए मार्गदर्शन",
        "description": (
            "Get Bhagavad Gita guidance for relationship pain, anger, attachment, and emotional confusion with relevant verses."
        ),
        "description_hi": (
            "रिश्तों के दर्द, क्रोध, आसक्ति और भावनात्मक उलझन के लिए प्रासंगिक श्लोकों सहित भगवद गीता मार्गदर्शन पाएँ।"
        ),
        "hero_title": "Bhagavad Gita For Relationships And Emotional Balance",
        "hero_title_hi": "रिश्तों और भावनात्मक संतुलन के लिए भगवद गीता",
        "hero_body": (
            "Relationships often bring attachment, hurt, anger, and confusion to the surface. The Gita helps "
            "you respond with more clarity, steadiness, and self-mastery instead of impulse."
        ),
        "hero_body_hi": (
            "रिश्ते अक्सर आसक्ति, चोट, क्रोध और उलझन को सतह पर ले आते हैं। गीता आपको आवेग के बजाय "
            "अधिक स्पष्टता, स्थिरता और आत्म-नियंत्रण के साथ प्रतिक्रिया देना सिखाती है।"
        ),
        "problem_points": [
            "anger and reactivity in close relationships",
            "attachment, hurt, and emotional dependence",
            "difficulty responding with calm and clarity",
        ],
        "problem_points_hi": [
            "करीबी रिश्तों में क्रोध और तीखी प्रतिक्रिया",
            "आसक्ति, चोट और भावनात्मक निर्भरता",
            "शांत और स्पष्ट प्रतिक्रिया देने में कठिनाई",
        ],
        "verse_refs": ["2.62", "2.63", "12.13"],
        "starter_question": "I get hurt and angry in relationships. How can I respond better?",
        "starter_question_hi": "रिश्तों में मुझे चोट लगती है और गुस्सा आता है। मैं बेहतर प्रतिक्रिया कैसे दूँ?",
    },
}


def _seo_value(page: dict, key: str, language: str):
    """Return Hindi variant when available, else fallback to default key."""
    if language == "hi":
        return page.get(f"{key}_hi", page.get(key))
    return page.get(key)


def _fetch_curated_verses(reference_list: list[str]) -> list[SimpleNamespace]:
    """Fetch a small stable verse list for SEO landing pages."""
    verses = []
    for ref in reference_list:
        try:
            chapter_text, verse_text = ref.split(".", 1)
            verse = Verse.objects.filter(
                chapter=int(chapter_text),
                verse=int(verse_text),
            ).first()
        except (TypeError, ValueError):
            verse = None

        if verse is None:
            verses.append(
                SimpleNamespace(
                    reference=ref,
                    translation="Relevant Bhagavad Gita guidance for this life challenge.",
                    themes=[],
                )
            )
            continue

        verses.append(
            SimpleNamespace(
                reference=ref,
                translation=verse.translation,
                themes=list(verse.themes or []),
            )
        )
    return verses


def robots_txt_view(request):
    """Serve robots policy with sitemap hint for search engines."""
    base_url = request.build_absolute_uri("/").rstrip("/")
    content = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {base_url}/sitemap.xml",
        ]
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def sitemap_xml_view(request):
    """Serve a minimal sitemap.xml for homepage and SEO topic routes."""
    base_url = request.build_absolute_uri("/").rstrip("/")
    urls = [
        "/",
        "/bhagavad-gita-for-anxiety/",
        "/bhagavad-gita-for-career-confusion/",
        "/bhagavad-gita-for-relationships/",
        "/api/chat-ui/",
    ]
    rows = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">",
    ]
    for path in urls:
        rows.extend(
            [
                "  <url>",
                f"    <loc>{base_url}{path}</loc>",
                "  </url>",
            ]
        )
    rows.append("</urlset>")
    return HttpResponse(
        "\n".join(rows),
        content_type="application/xml; charset=utf-8",
    )


class SeoLandingIndexView(View):
    """Public index for SEO-friendly Bhagavad Gita topic pages."""

    template_name = "guide_api/seo_landing.html"

    def get(self, request):
        language = "hi" if request.GET.get("language") == "hi" else "en"
        path_url = request.build_absolute_uri(request.path)
        canonical_url = (
            f"{path_url}?language=hi"
            if language == "hi"
            else path_url
        )
        alternate_en_url = path_url
        alternate_hi_url = f"{path_url}?language=hi"
        site_url = request.build_absolute_uri("/")
        topics = []
        for key, page in SEO_LANDING_PAGES.items():
            topics.append(
                {
                    "key": key,
                    "topic_label": _seo_value(page, "topic_label", language),
                    "slug": page["slug"],
                    "hero_title": _seo_value(page, "hero_title", language),
                    "description": _seo_value(page, "description", language),
                }
            )
        page_title = (
            "भगवद गीता मार्गदर्शिकाएँ: चिंता, करियर, रिश्ते और जीवन के प्रश्न"
            if language == "hi"
            else "Bhagavad Gita Guides For Anxiety, Career, Relationships, and Real Life Questions"
        )
        meta_description = (
            "चिंता, करियर उलझन, रिश्तों और अन्य जीवन चुनौतियों के लिए केंद्रित भगवद गीता पेज देखें।"
            if language == "hi"
            else (
                "Explore focused Bhagavad Gita landing pages for anxiety, career confusion, relationships, "
                "and other real-life challenges."
            )
        )
        page_heading = (
            "जीवन की वास्तविक समस्याओं के लिए भगवद गीता मार्गदर्शन"
            if language == "hi"
            else "Bhagavad Gita Guides For Real Life Problems"
        )
        page_intro = (
            "नीचे एक केंद्रित मार्गदर्शिका चुनें, प्रासंगिक श्लोक देखें, और फिर व्यक्तिगत उत्तर के लिए ऐप में जाएँ।"
            if language == "hi"
            else (
                "Choose a focused guide below, explore relevant verses, and then continue into the full app "
                "for a personalized answer."
            )
        )
        structured_data = json.dumps(
            [
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "name": "Bhagavad Gita Guide",
                    "url": site_url,
                },
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": page_heading,
                    "description": meta_description,
                    "url": canonical_url,
                    "inLanguage": "hi" if language == "hi" else "en",
                    "hasPart": [
                        {
                            "@type": "WebPage",
                            "name": topic["topic_label"],
                            "url": f"{site_url.rstrip('/')}/{topic['slug']}/",
                        }
                        for topic in topics
                    ],
                },
            ],
            ensure_ascii=False,
        )
        context = {
            "page_title": page_title,
            "meta_description": meta_description,
            "page_heading": page_heading,
            "page_intro": page_intro,
            "topics": topics,
            "language": language,
            "canonical_url": canonical_url,
            "alternate_en_url": alternate_en_url,
            "alternate_hi_url": alternate_hi_url,
            "og_type": "website",
            "structured_data": structured_data,
            "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        }
        return render(request, self.template_name, context)


class SeoLandingTopicView(View):
    """Public SEO topic page that points users into the full chat experience."""

    template_name = "guide_api/seo_landing.html"

    def get(self, request, slug: str):
        language = "hi" if request.GET.get("language") == "hi" else "en"
        path_url = request.build_absolute_uri(request.path)
        canonical_url = (
            f"{path_url}?language=hi"
            if language == "hi"
            else path_url
        )
        alternate_en_url = path_url
        alternate_hi_url = f"{path_url}?language=hi"
        site_url = request.build_absolute_uri("/")
        page = next(
            (item for item in SEO_LANDING_PAGES.values() if item["slug"] == slug),
            None,
        )
        if page is None:
            return JsonResponse({"detail": "Not found."}, status=404)

        starter_question = _seo_value(page, "starter_question", language)
        chat_url = f"/api/chat-ui/?mode=simple&language={language}"
        breadcrumb_title = _seo_value(page, "topic_label", language)
        page_title = _seo_value(page, "title", language)
        meta_description = _seo_value(page, "description", language)
        structured_data = json.dumps(
            [
                {
                    "@context": "https://schema.org",
                    "@type": "WebPage",
                    "name": page_title,
                    "description": meta_description,
                    "url": canonical_url,
                    "inLanguage": "hi" if language == "hi" else "en",
                },
                {
                    "@context": "https://schema.org",
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": 1,
                            "name": "Bhagavad Gita Guide",
                            "item": alternate_en_url.replace(request.path, "/"),
                        },
                        {
                            "@type": "ListItem",
                            "position": 2,
                            "name": breadcrumb_title,
                            "item": canonical_url,
                        },
                    ],
                },
            ],
            ensure_ascii=False,
        )
        context = {
            "page_title": page_title,
            "meta_description": meta_description,
            "page_heading": _seo_value(page, "hero_title", language),
            "page_intro": _seo_value(page, "hero_body", language),
            "topic_label": _seo_value(page, "topic_label", language),
            "problem_points": _seo_value(page, "problem_points", language),
            "featured_verses": _fetch_curated_verses(page["verse_refs"]),
            "starter_question": starter_question,
            "chat_url": chat_url,
            "chat_url_with_prefill": f"{chat_url}&prefill={quote_plus(starter_question)}",
            "other_topics": [
                {
                    "topic_label": _seo_value(item, "topic_label", language),
                    "slug": item["slug"],
                }
                for item in SEO_LANDING_PAGES.values()
                if item["slug"] != slug
            ],
            "language": language,
            "canonical_url": canonical_url,
            "alternate_en_url": alternate_en_url,
            "alternate_hi_url": alternate_hi_url,
            "og_type": "article",
            "structured_data": structured_data,
            "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        }
        return render(request, self.template_name, context)


def _get_user_plan_and_usage(user):
    """Return user subscription record and today's usage counter."""
    subscription, _ = UserSubscription.objects.get_or_create(user=user)
    usage, _ = DailyAskUsage.objects.get_or_create(
        user=user,
        date=timezone.localdate(),
        defaults={"ask_count": 0},
    )
    return subscription, usage


def _request_quota_settings() -> RequestQuotaSettings | None:
    """Return singleton admin quota settings if configured."""
    return RequestQuotaSettings.objects.first()


def _plan_daily_limit(plan: str) -> int | None:
    """Resolve daily ask limit from admin settings, then env defaults."""
    quota_settings = _request_quota_settings()
    if plan == UserSubscription.PLAN_PRO:
        if quota_settings:
            if not quota_settings.pro_limit_enabled:
                return None
            return quota_settings.pro_daily_ask_limit
        return settings.ASK_LIMIT_PRO_DAILY

    if quota_settings:
        if not quota_settings.free_limit_enabled:
            return None
        return quota_settings.free_daily_ask_limit
    return settings.ASK_LIMIT_FREE_DAILY


def _remaining_today(
    *,
    daily_limit: int | None,
    used_today: int,
) -> int | None:
    """Return remaining asks, or None when plan limits are disabled."""
    if daily_limit is None:
        return None
    return max(daily_limit - used_today, 0)


def _log_ask_event(
    *,
    user_id: str,
    source: str,
    mode: str,
    outcome: str,
    response_mode: str = "",
    retrieval_mode: str = "",
    plan: str = "",
) -> None:
    """Persist analytics row for each ask attempt."""
    AskEvent.objects.create(
        user_id=user_id,
        source=source,
        mode=mode,
        outcome=outcome,
        response_mode=response_mode,
        retrieval_mode=retrieval_mode,
        plan=plan,
    )


def _build_contextual_follow_ups(
    *,
    message: str,
    mode: str,
    language: str = "en",
    query_themes: list[str],
) -> list[dict]:
    """Build deterministic, mobile-friendly follow-up prompts."""
    primary_theme = query_themes[0] if query_themes else "life"
    normalized_language = "hi" if language == "hi" else "en"
    label_prefix = primary_theme.replace("_", " ").title()

    if normalized_language == "hi":
        prompts = [
            {
                "label": f"{label_prefix}: 3-स्टेप योजना",
                "prompt": (
                    "अगले 24 घंटों के लिए इस समस्या पर एक व्यावहारिक 3-स्टेप "
                    f"योजना दीजिए: {message}"
                ),
                "intent": "action_plan",
            },
            {
                "label": f"{label_prefix}: गहरा अर्थ",
                "prompt": (
                    "एक मुख्य श्लोक को सरल हिंदी में समझाइए और बताइए कि "
                    "मैं इसे आज कैसे लागू करूं।"
                ),
                "intent": "deeper_meaning",
            },
            {
                "label": "आत्म-चिंतन",
                "prompt": (
                    "इस मार्गदर्शन के आधार पर एक चिंतन प्रश्न और एक "
                    "जर्नलिंग प्रॉम्प्ट पूछिए।"
                ),
                "intent": "self_reflection",
            },
        ]
    else:
        prompts = [
            {
                "label": f"{label_prefix}: 3-step plan",
                "prompt": (
                    "Give me a practical 3-step plan for the next 24 hours "
                    f"for this issue: {message}"
                ),
                "intent": "action_plan",
            },
            {
                "label": f"{label_prefix}: deeper meaning",
                "prompt": (
                    "Explain one key verse in simpler words and how I should "
                    "apply it today."
                ),
                "intent": "deeper_meaning",
            },
            {
                "label": "Self-reflection",
                "prompt": (
                    "Ask me one reflection question and one journaling prompt "
                    "based on this guidance."
                ),
                "intent": "self_reflection",
            },
        ]
    return prompts[: 2 if mode == "simple" else 3]


def _log_follow_up_events(
    *,
    user_id: str,
    source: str,
    event_type: str,
    mode: str,
    follow_ups: list[dict],
) -> None:
    """Persist follow-up shown/clicked analytics events."""
    for follow_up in follow_ups:
        FollowUpEvent.objects.create(
            user_id=user_id,
            source=source,
            event_type=event_type,
            intent=str(follow_up.get("intent", "")),
            prompt=str(follow_up.get("prompt", ""))[:255],
            mode=mode,
        )


def _error_response(
    *,
    message: str,
    status_code: int,
    code: str,
    extra: dict | None = None,
) -> Response:
    """Return stable error envelope while preserving legacy detail field."""
    payload = {
        "error": {
            "code": code,
            "message": message,
        },
        "detail": message,
    }
    if extra:
        payload.update(extra)
    return Response(payload, status=status_code)


def _pagination_params(request) -> tuple[int, int]:
    """Parse mobile-friendly limit/offset with safe defaults."""
    raw_limit = request.query_params.get("limit", "20")
    raw_offset = request.query_params.get("offset", "0")
    limit = int(raw_limit)
    offset = int(raw_offset)
    if limit <= 0:
        limit = 20
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0
    return limit, offset


def _get_engagement_profile(user):
    """Get or create engagement profile for authenticated user."""
    profile, _ = UserEngagementProfile.objects.get_or_create(user=user)
    return profile


def _serialize_engagement_profile(profile) -> dict:
    """Return stable API payload for engagement state."""
    return {
        "daily_streak": profile.daily_streak,
        "last_active_date": (
            profile.last_active_date.isoformat()
            if profile.last_active_date
            else None
        ),
        "reminder_enabled": profile.reminder_enabled,
        "reminder_time": (
            profile.reminder_time.strftime("%H:%M:%S")
            if profile.reminder_time
            else None
        ),
        "timezone": profile.timezone,
        "preferred_channel": profile.preferred_channel,
    }


def _log_engagement_event(*, user, event_type: str, metadata: dict) -> None:
    """Persist engagement analytics events."""
    EngagementEvent.objects.create(
        user=user,
        event_type=event_type,
        metadata=metadata,
    )


def _update_streak_for_today(user):
    """Update daily streak based on user's previous active date."""
    profile = _get_engagement_profile(user)
    today = timezone.localdate()
    previous = profile.last_active_date
    if previous == today:
        return profile
    if previous == (today - timedelta(days=1)):
        profile.daily_streak = max(1, profile.daily_streak + 1)
    else:
        profile.daily_streak = 1
    profile.last_active_date = today
    profile.save(
        update_fields=["daily_streak", "last_active_date", "updated_at"]
    )
    _log_engagement_event(
        user=user,
        event_type=EngagementEvent.EVENT_STREAK_UPDATED,
        metadata={
            "daily_streak": profile.daily_streak,
            "last_active_date": today.isoformat(),
        },
    )
    return profile


class HealthView(APIView):
    """Lightweight readiness endpoint for health checks."""

    def get(self, request):
        """Return service health status payload."""
        return Response({"status": "ok", "service": "gita-guide-api"})


class RegisterView(APIView):
    """Create user account and return API token."""

    def post(self, request):
        """Validate signup input and issue authentication token."""
        serializer = RegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"].strip()
        password = serializer.validated_data["password"]

        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            return _error_response(
                message="Username is already taken.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="username_taken",
            )

        user = user_model.objects.create_user(
            username=username,
            password=password,
        )
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "username": user.username},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """Authenticate existing user and return API token."""

    def post(self, request):
        """Validate credentials and issue existing/new token."""
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        user = authenticate(
            request=request,
            username=username,
            password=password,
        )
        if user is None:
            return _error_response(
                message="Invalid username or password.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_credentials",
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username})


class LogoutView(APIView):
    """Logout by deleting the caller's current token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Invalidate active API token for authenticated user."""
        Token.objects.filter(user=request.user).delete()
        return Response({"status": "logged_out"})


class MeView(APIView):
    """Return current authenticated user identity."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Serve minimal identity payload for client checks."""
        subscription, usage = _get_user_plan_and_usage(request.user)
        engagement = _get_engagement_profile(request.user)
        daily_limit = _plan_daily_limit(subscription.plan)
        return Response(
            {
                "username": request.user.get_username(),
                "plan": subscription.plan,
                "daily_limit": daily_limit,
                "used_today": usage.ask_count,
                "remaining_today": _remaining_today(
                    daily_limit=daily_limit,
                    used_today=usage.ask_count,
                ),
                "engagement": _serialize_engagement_profile(engagement),
            }
        )


class PlanUpdateView(APIView):
    """Mock plan switch endpoint for local quota and paywall testing."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Update current user's plan between free and pro."""
        serializer = PlanUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription, usage = _get_user_plan_and_usage(request.user)
        subscription.plan = serializer.validated_data["plan"]
        subscription.save(update_fields=["plan", "updated_at"])
        daily_limit = _plan_daily_limit(subscription.plan)
        return Response(
            {
                "username": request.user.get_username(),
                "plan": subscription.plan,
                "daily_limit": daily_limit,
                "used_today": usage.ask_count,
                "remaining_today": _remaining_today(
                    daily_limit=daily_limit,
                    used_today=usage.ask_count,
                ),
            }
        )


class EngagementProfileView(APIView):
    """Expose streak and reminder preferences for mobile clients."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return current engagement profile snapshot."""
        profile = _get_engagement_profile(request.user)
        return Response(_serialize_engagement_profile(profile))

    def patch(self, request):
        """Update reminder settings and notification channel."""
        serializer = EngagementProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = _get_engagement_profile(request.user)
        changed = {}
        for field, value in serializer.validated_data.items():
            if getattr(profile, field) != value:
                setattr(profile, field, value)
                if hasattr(value, "isoformat"):
                    changed[field] = value.isoformat()
                else:
                    changed[field] = value
        if changed:
            profile.save(update_fields=[*changed.keys(), "updated_at"])
            _log_engagement_event(
                user=request.user,
                event_type=EngagementEvent.EVENT_REMINDER_PREF_UPDATED,
                metadata={"changed_fields": changed},
            )
        return Response(_serialize_engagement_profile(profile))


class AskView(APIView):
    """Main API endpoint: user prompt -> retrieval + guidance response."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Validate input, apply safety, and return grounded guidance."""
        serializer = AskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if is_risky_prompt(data["message"]):
            _log_ask_event(
                user_id=request.user.get_username(),
                source=AskEvent.SOURCE_API,
                mode=data["mode"],
                outcome=AskEvent.OUTCOME_BLOCKED_SAFETY,
            )
            return _error_response(
                message=(
                    "This app cannot provide crisis or self-harm guidance, "
                    "or medical/legal decisions. Please contact local "
                    "emergency or professional support immediately."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
                code="safety_blocked",
            )

        subscription, usage = _get_user_plan_and_usage(request.user)
        daily_limit = _plan_daily_limit(subscription.plan)
        if daily_limit is not None and usage.ask_count >= daily_limit:
            _log_ask_event(
                user_id=request.user.get_username(),
                source=AskEvent.SOURCE_API,
                mode=data["mode"],
                outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
                plan=subscription.plan,
            )
            return _error_response(
                message=(
                    "Daily ask limit reached for your plan. "
                    "Please upgrade to Pro or try again tomorrow."
                ),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="quota_exceeded",
                extra={
                    "plan": subscription.plan,
                    "daily_limit": daily_limit,
                    "used_today": usage.ask_count,
                    "remaining_today": _remaining_today(
                        daily_limit=daily_limit,
                        used_today=usage.ask_count,
                    ),
                },
            )

        conversation, verses, guidance, retrieval = _run_guidance_flow(
            user_id=request.user.get_username(),
            message=data["message"],
            mode=data["mode"],
            language=data["language"],
            conversation_id=data.get("conversation_id"),
        )
        usage.ask_count += 1
        usage.save(update_fields=["ask_count"])
        engagement = _update_streak_for_today(request.user)
        _log_ask_event(
            user_id=request.user.get_username(),
            source=AskEvent.SOURCE_API,
            mode=data["mode"],
            outcome=AskEvent.OUTCOME_SERVED,
            response_mode=guidance.response_mode,
            retrieval_mode=retrieval.retrieval_mode,
            plan=subscription.plan,
        )

        response_data = {
            "conversation_id": conversation.id,
            "guidance": guidance.guidance,
            "verses": VerseSerializer(verses, many=True).data,
            "meaning": guidance.meaning,
            "actions": guidance.actions,
            "reflection": guidance.reflection,
            "verse_references": [
                f"{verse.chapter}.{verse.verse}" for verse in verses
            ],
            "language": data["language"],
            "plan": subscription.plan,
            "daily_limit": daily_limit,
            "used_today": usage.ask_count,
            "remaining_today": _remaining_today(
                daily_limit=daily_limit,
                used_today=usage.ask_count,
            ),
            "engagement": _serialize_engagement_profile(engagement),
        }
        follow_ups = _build_contextual_follow_ups(
            message=data["message"],
            mode=data["mode"],
            language=data["language"],
            query_themes=retrieval.query_themes,
        )
        response_data["follow_ups"] = follow_ups
        _log_follow_up_events(
            user_id=request.user.get_username(),
            source=FollowUpEvent.SOURCE_API,
            event_type=FollowUpEvent.EVENT_SHOWN,
            mode=data["mode"],
            follow_ups=follow_ups,
        )
        if settings.DEBUG:
            response_data["response_mode"] = guidance.response_mode
            response_data["retrieval_mode"] = retrieval.retrieval_mode
            response_data["retrieved_references"] = [
                verse["reference"] for verse in response_data["verses"]
            ]
            response_data["retrieval_scores"] = retrieval.retrieval_scores
            response_data["query_themes"] = retrieval.query_themes
            response_data["query_interpretation"] = retrieval.query_interpretation
        return Response(response_data)


class FollowUpGenerateView(APIView):
    """Generate contextual continuation prompts for mobile/web clients."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Return deterministic follow-up prompts from query context."""
        serializer = FollowUpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        retrieval = retrieve_verses_with_trace(
            message=data["message"],
            limit=4 if data["mode"] == "deep" else 3,
        )
        follow_ups = _build_contextual_follow_ups(
            message=data["message"],
            mode=data["mode"],
            language=data["language"],
            query_themes=retrieval.query_themes,
        )
        _log_follow_up_events(
            user_id=request.user.get_username(),
            source=FollowUpEvent.SOURCE_API,
            event_type=FollowUpEvent.EVENT_SHOWN,
            mode=data["mode"],
            follow_ups=follow_ups,
        )
        return Response(
            {
                "mode": data["mode"],
                "language": data["language"],
                "query_themes": retrieval.query_themes,
                "follow_ups": follow_ups,
            }
        )


class RetrievalEvalView(APIView):
    """Retrieval debugging endpoint without response generation."""

    @staticmethod
    def _serialize_trace(retrieval):
        """Serialize retrieval result object into API-safe JSON payload."""
        verse_data = VerseSerializer(retrieval.verses, many=True).data
        return {
            "retrieval_mode": retrieval.retrieval_mode,
            "retrieved_references": [
                verse["reference"] for verse in verse_data
            ],
            "retrieval_scores": retrieval.retrieval_scores,
            "query_themes": retrieval.query_themes,
            "query_tokens": retrieval.query_tokens,
            "verses": verse_data,
        }

    def post(self, request):
        """Return retrieval traces or side-by-side benchmark output."""
        serializer = RetrievalEvalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        limit = 4 if data["mode"] == "deep" else 3

        if data["mode"] == "benchmark":
            semantic = retrieve_semantic_verses_with_trace(
                message=data["message"],
                limit=limit,
            )
            hybrid = retrieve_hybrid_verses_with_trace(
                message=data["message"],
                limit=limit,
            )
            return Response(
                {
                    "mode": "benchmark",
                    "semantic": self._serialize_trace(semantic),
                    "hybrid": self._serialize_trace(hybrid),
                }
            )

        retrieval = retrieve_verses_with_trace(
            message=data["message"],
            limit=limit,
        )
        return Response(self._serialize_trace(retrieval))


class DailyVerseView(APIView):
    """Return a deterministic daily verse and short reflection."""

    def get(self, request):
        """Serve one date-seeded verse with language-aware meaning."""
        language = str(request.query_params.get("language", "en")).strip()
        if language not in {"en", "hi"}:
            language = "en"

        queryset = Verse.objects.order_by("chapter", "verse")
        count = queryset.count()
        if count > 0:
            day_seed = timezone.localdate().isoformat()
            verse = queryset[Random(day_seed).randrange(count)]
        else:
            verse = None

        if verse is None:
            verses = retrieve_verses("daily verse", limit=1)
            verse = verses[0]
            detail = get_verse_detail(verse.chapter, verse.verse) or {}
        else:
            detail = get_verse_detail(verse.chapter, verse.verse) or {}

        english_quote = str(detail.get("english_meaning", "")).strip()
        hindi_quote = str(detail.get("slok", "")).strip()
        english_meaning = (
            str(detail.get("translation", "")).strip()
            or verse.translation.strip()
        )
        hindi_meaning = str(detail.get("hindi_meaning", "")).strip()
        commentary = str(verse.commentary or "").strip()
        meaning = (
            hindi_meaning
            if language == "hi" and hindi_meaning
            else commentary or english_meaning
        )
        quote = (
            hindi_quote
            if language == "hi" and hindi_quote
            else english_quote or english_meaning
        )
        reflection = (
            "आज इस श्लोक को अपने एक निर्णय, एक प्रतिक्रिया, और एक कर्म में उतारने का अभ्यास करें।"
            if language == "hi"
            else "Practice applying this verse today in one decision, one reaction, and one concrete action."
        )

        return Response(
            {
                "verse": VerseSerializer(verse).data,
                "quote": quote,
                "meaning": meaning,
                "reflection": reflection,
            }
        )


class ChapterListView(APIView):
    """List all 18 chapters with metadata for browsing screen."""

    def get(self, request):
        """Return all chapters with name, verse count, and translations."""
        chapters = get_all_chapters()
        return Response({"chapters": chapters, "total": len(chapters)})


class ChapterDetailView(APIView):
    """Get full detail for a single chapter including summary."""

    def get(self, request, chapter_number: int):
        """Return chapter metadata, summary, and verse list."""
        chapter = get_chapter_detail(chapter_number)
        if chapter is None:
            return _error_response(
                message=f"Chapter {chapter_number} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="chapter_not_found",
            )

        verses = get_chapter_verses(chapter_number)
        return Response({
            "chapter": chapter,
            "verses": verses,
        })


class VerseDetailView(APIView):
    """Get full detail for a single verse with all commentaries."""

    def get(self, request, chapter: int, verse: int):
        """Return verse with sanskrit, translations, and multi-author commentary."""
        verse_data = get_verse_detail(chapter, verse)
        if verse_data is None:
            return _error_response(
                message=f"Verse {chapter}.{verse} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="verse_not_found",
            )
        return Response(verse_data)


class MantraView(APIView):
    """Generate a mantra/verse recommendation based on mood."""

    def post(self, request):
        """Return a verse as mantra for the requested mood."""
        serializer = MantraRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        mantra = get_mantra_for_mood(
            mood=data["mood"],
            language=data["language"],
        )
        if mantra is None:
            return _error_response(
                message="Could not find a suitable mantra.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="mantra_not_found",
            )
        return Response(mantra)


class QuoteArtStylesView(APIView):
    """List available quote art styles for UI selection."""

    def get(self, request):
        """Return all quote art style options."""
        styles = get_quote_art_styles()
        return Response({"styles": styles})


class QuoteArtView(APIView):
    """Generate shareable quote art data from a Gita verse."""

    def post(self, request):
        """Generate quote art data for mobile rendering."""
        serializer = QuoteArtRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        art_data = generate_quote_art_data(
            verse_reference=data["verse_reference"],
            style=data["style"],
            language=data["language"],
            custom_quote=data.get("custom_quote"),
        )
        if art_data is None:
            return _error_response(
                message="Verse not found or invalid reference format.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="verse_not_found",
            )

        response_serializer = QuoteArtResponseSerializer(data=art_data)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.validated_data)


class FeaturedQuotesView(APIView):
    """Return featured verse quotes for art creation suggestions."""

    def get(self, request):
        """Suggest popular verses for quote art creation."""
        language = request.query_params.get("language", "en")
        limit = int(request.query_params.get("limit", "5"))
        limit = min(max(1, limit), 10)  # Clamp between 1-10

        quotes = get_featured_quotes(language=language, limit=limit)
        return Response({"quotes": quotes})


class ConversationHistoryView(APIView):
    """Fetch most recent conversation timeline for a user."""
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id: str):
        """Return ordered message list for the latest user session."""
        active_user_id = request.user.get_username()
        requested_user_id = active_user_id if user_id == "me" else user_id
        if requested_user_id != active_user_id:
            return _error_response(
                message="You can only access your own conversation history.",
                status_code=status.HTTP_403_FORBIDDEN,
                code="forbidden_user_scope",
            )

        conversation = (
            Conversation.objects.filter(user_id=active_user_id)
            .order_by("-updated_at")
            .first()
        )
        if conversation is None:
            return Response({"user_id": active_user_id, "messages": []})

        messages = MessageSerializer(
            conversation.messages.all(),
            many=True,
        ).data
        return Response(
            {
                "user_id": active_user_id,
                "conversation_id": conversation.id,
                "messages": messages,
            }
        )


class FeedbackView(APIView):
    """Capture and browse user feedback on response quality."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return latest feedback entries for lightweight review."""
        try:
            limit, offset = _pagination_params(request)
        except ValueError:
            return _error_response(
                message="limit and offset must be integers.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_pagination",
            )
        user_id = request.user.get_username()
        base_qs = ResponseFeedback.objects.filter(user_id=user_id)
        entries = base_qs[offset:offset + limit]
        data = [
            {
                "id": entry.id,
                "user_id": entry.user_id,
                "helpful": entry.helpful,
                "mode": entry.mode,
                "response_mode": entry.response_mode,
                "note": entry.note,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]
        total = base_qs.count()
        next_offset = offset + limit if (offset + limit) < total else None
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
                "results": data,
            }
        )

    def post(self, request):
        """Validate and persist one feedback event."""
        user_id = request.user.get_username()
        message = str(request.data.get("message", "")).strip()
        mode = str(request.data.get("mode", "simple")).strip()
        response_mode = (
            str(request.data.get("response_mode", "fallback")).strip()
        )
        helpful = request.data.get("helpful")
        note = str(request.data.get("note", "")).strip()
        conversation_id = request.data.get("conversation_id")

        if helpful in [True, False]:
            parsed_helpful = helpful
        elif str(helpful).lower() in {"true", "1", "yes"}:
            parsed_helpful = True
        elif str(helpful).lower() in {"false", "0", "no"}:
            parsed_helpful = False
        else:
            return _error_response(
                message="helpful must be true or false",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_helpful_value",
            )

        if mode not in {"simple", "deep"}:
            mode = "simple"
        if response_mode not in {"llm", "fallback"}:
            response_mode = "fallback"

        conversation = None
        if conversation_id:
            conversation = Conversation.objects.filter(
                id=conversation_id,
                user_id=user_id,
            ).first()

        entry = ResponseFeedback.objects.create(
            conversation=conversation,
            user_id=user_id,
            message=message,
            mode=mode,
            response_mode=response_mode,
            helpful=parsed_helpful,
            note=note,
        )
        return Response(
            {"id": entry.id, "status": "saved"},
            status=status.HTTP_201_CREATED,
        )


class SupportRequestView(APIView):
    """Capture user support requests for payment/account/product issues."""

    permission_classes = [AllowAny]

    def post(self, request):
        """Validate and persist support ticket from web or mobile clients."""
        serializer = SupportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        auth_user = (
            request.user
            if request.user and request.user.is_authenticated
            else None
        )

        ticket = SupportTicket.objects.create(
            user=auth_user,
            requester_id=(auth_user.get_username() if auth_user else "guest"),
            name=data["name"],
            email=data["email"],
            issue_type=data["issue_type"],
            message=data["message"],
        )
        return Response(
            {
                "id": ticket.id,
                "status": "received",
                "message": (
                    "Support request received. Our team will contact you soon."
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class SavedReflectionListCreateView(APIView):
    """Create and list saved reflections for authenticated users."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return user's saved reflections in reverse chronological order."""
        try:
            limit, offset = _pagination_params(request)
        except ValueError:
            return _error_response(
                message="limit and offset must be integers.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_pagination",
            )
        base_qs = SavedReflection.objects.filter(user=request.user)
        entries = base_qs[offset:offset + limit]
        total = base_qs.count()
        next_offset = offset + limit if (offset + limit) < total else None
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
                "results": SavedReflectionSerializer(entries, many=True).data,
            }
        )

    def post(self, request):
        """Save one reflection/bookmark from ask output payload."""
        serializer = SavedReflectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        conversation = None
        conversation_id = data.get("conversation_id")
        if conversation_id:
            conversation = Conversation.objects.filter(
                id=conversation_id,
                user_id=request.user.get_username(),
            ).first()

        entry = SavedReflection.objects.create(
            user=request.user,
            conversation=conversation,
            message=data["message"],
            guidance=data["guidance"],
            meaning=data.get("meaning", ""),
            actions=data.get("actions", []),
            reflection=data.get("reflection", ""),
            verse_references=data.get("verse_references", []),
            note=data.get("note", ""),
        )
        return Response(
            SavedReflectionSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )


class SavedReflectionDetailView(APIView):
    """Delete one saved reflection owned by current user."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, reflection_id: int):
        """Delete target saved reflection if it belongs to caller."""
        entry = SavedReflection.objects.filter(
            id=reflection_id,
            user=request.user,
        ).first()
        if entry is None:
            return _error_response(
                message="Saved reflection not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                code="saved_reflection_not_found",
            )
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatUIView(View):
    """Simple server-rendered page for manual API testing."""

    template_name = "guide_api/chat_ui.html"
    guest_cookie_name = "chat_ui_guest_id"
    guest_cookie_age = 60 * 60 * 24 * 90

    @staticmethod
    def _guest_limit_settings() -> dict:
        """Resolve guest quota switches and limits from admin settings."""
        quota_settings = _request_quota_settings()
        if quota_settings:
            return {
                "enabled": quota_settings.guest_limit_enabled,
                "limit": quota_settings.guest_ask_limit,
            }
        return {
            "enabled": True,
            "limit": 3,
        }

    def dispatch(self, request, *args, **kwargs):
        """Attach a durable guest identifier so guest caps survive restarts."""
        request.chat_ui_guest_id = ""
        if not self._chat_ui_authenticated_username(request):
            request.chat_ui_guest_id = str(
                request.COOKIES.get(self.guest_cookie_name, ""),
            ).strip() or uuid4().hex
            GuestChatIdentity.objects.get_or_create(
                guest_id=request.chat_ui_guest_id,
            )
        response = super().dispatch(request, *args, **kwargs)
        if request.chat_ui_guest_id:
            response.set_cookie(
                self.guest_cookie_name,
                request.chat_ui_guest_id,
                max_age=self.guest_cookie_age,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )
        return response

    def _render_chat_ui(self, request, context: dict):
        """Render chat UI with guest quota state and debug flag attached when needed."""
        context.setdefault(
            "guest_quota_snapshot",
            (
                self._guest_quota_snapshot(request)
                if not self._chat_ui_authenticated_username(request)
                else None
            ),
        )
        context.setdefault("debug", settings.DEBUG)
        context.setdefault("support_email", settings.SUPPORT_EMAIL)
        context.setdefault(
            "support_name",
            str(request.session.get("chat_ui_auth_username", "")).strip(),
        )
        context.setdefault(
            "support_form_email",
            (
                request.user.email
                if request.user and request.user.is_authenticated
                else ""
            ),
        )
        context.setdefault("support_issue_type", "other")
        context.setdefault("support_message", "")
        return render(request, self.template_name, context)

    def _guest_identity(self, request):
        """Look up the persistent guest row for the current browser."""
        guest_id = str(getattr(request, "chat_ui_guest_id", "")).strip()
        if not guest_id:
            return None
        identity, created = GuestChatIdentity.objects.get_or_create(
            guest_id=guest_id,
        )
        if not created:
            identity.save(update_fields=["last_seen_at"])
        return identity

    def _guest_quota_snapshot(self, request) -> dict | None:
        """Summarize guest chat availability for the current browser."""
        identity = self._guest_identity(request)
        if identity is None:
            return None
        guest_quota = self._guest_limit_settings()
        limit_enabled = guest_quota["enabled"]
        limit = guest_quota["limit"]
        used = identity.total_asks
        return {
            "ask_limit": limit,
            "asks_used": used,
            "remaining_asks": max(limit - used, 0) if limit_enabled else None,
            "limit_reached": (used >= limit) if limit_enabled else False,
            "limit_enabled": limit_enabled,
        }

    def _consume_guest_conversation_slot(self, request) -> dict:
        """Count each guest prompt against the persistent browser cap."""
        identity = self._guest_identity(request)
        if identity is None:
            return {"allowed": True, "snapshot": None}
        guest_quota = self._guest_limit_settings()
        if (
            guest_quota["enabled"]
            and identity.total_asks >= guest_quota["limit"]
        ):
            return {
                "allowed": False,
                "snapshot": self._guest_quota_snapshot(request),
            }
        update_fields = ["last_seen_at", "total_asks"]
        identity.total_asks += 1
        identity.save(update_fields=update_fields)
        return {
            "allowed": True,
            "snapshot": self._guest_quota_snapshot(request),
        }

    def get(self, request):
        """Render empty chat form."""
        authenticated_username = self._chat_ui_authenticated_username(request)
        default_user_id = self._default_user_id(request)
        start_fresh = request.GET.get("new", "").strip() == "1"
        mode = self._chat_ui_mode(request.GET.get("mode", "simple"))
        language = self._chat_ui_language(request.GET.get("language", "en"))
        prefill_message = str(request.GET.get("prefill", "")).strip()
        if prefill_message:
            logger.info(
                "seo_cta_to_chatui",
                extra={
                    "path": request.path,
                    "method": request.method,
                    "is_guest_chat": not bool(authenticated_username),
                    "user_id": default_user_id,
                    "mode": mode,
                    "language": language,
                    "prefill_len": len(prefill_message),
                    "guest_id": str(getattr(request, "chat_ui_guest_id", ""))[:12],
                    "referer": request.META.get("HTTP_REFERER", ""),
                },
            )
        if request.GET.get("fragment", "").strip() == "conversations":
            if not authenticated_username:
                return JsonResponse(
                    {"items": [], "has_more": False, "next_offset": None},
                )
            limit = self._conversation_limit(request.GET.get("limit", "3"))
            offset = self._conversation_offset(request.GET.get("offset", "0"))
            return JsonResponse(
                self._conversation_page(
                    default_user_id,
                    limit=limit,
                    offset=offset,
                ),
            )
        active_conversation = None
        if authenticated_username and not start_fresh:
            active_conversation = self._chat_ui_conversation(
                default_user_id,
                request.GET.get("conversation_id"),
            )
        if not authenticated_username and start_fresh:
            self._clear_guest_conversation(request)
        conversation_page = (
            self._conversation_page(default_user_id, limit=3, offset=0)
            if authenticated_username
            else {"items": [], "has_more": False, "next_offset": None}
        )
        return self._render_chat_ui(
            request,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "",
                "selected_plan": "free",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": (
                    self._saved_reflections_for_user(
                        request,
                        default_user_id,
                    )
                    if authenticated_username
                    else []
                ),
                "active_conversation_id": (
                    active_conversation.id if active_conversation else ""
                ),
                "conversation_messages": (
                    self._conversation_messages(active_conversation)
                    if authenticated_username
                    else self._guest_conversation_messages(request)
                ),
                "conversations": (
                    conversation_page["items"]
                ),
                "conversations_has_more": conversation_page["has_more"],
                "conversations_next_offset": conversation_page["next_offset"],
                "user_id": default_user_id,
                "is_guest_chat": not authenticated_username,
                "mode": mode,
                "language": language,
                "message": prefill_message,
            },
        )

    def post(self, request):
        """Handle ask or feedback submit action from HTML form."""
        authenticated_username = self._chat_ui_authenticated_username(request)
        action = request.POST.get("action", "ask").strip()
        if action == "register":
            return self._handle_register(request)
        if action == "login":
            return self._handle_login(request)
        if action == "logout":
            return self._handle_logout(request)
        if action == "feedback":
            return self._handle_feedback(request)
        if action == "plan":
            return self._handle_plan_update(request)
        if action == "support":
            return self._handle_support_request(request)
        if action == "save":
            return self._handle_save_reflection(request)
        if action == "delete_conversation":
            return self._handle_delete_conversation(request)

        starter_prompts = self._starter_prompts()
        recent_questions = self._recent_questions(request)
        user_id = authenticated_username or "guest"
        active_conversation = (
            self._chat_ui_conversation(
                user_id,
                request.POST.get("conversation_id"),
            )
            if authenticated_username
            else None
        )
        message = request.POST.get("message", "").strip()
        mode = request.POST.get("mode", "simple")
        language = self._chat_ui_language(request.POST.get("language", "en"))
        follow_up_intent = request.POST.get("follow_up_intent", "").strip()

        if mode not in {"simple", "deep"}:
            mode = "simple"

        if not message:
            return self._render_chat_ui(
                request,
                {
                    "response_data": None,
                    "error": "Please enter a message to continue.",
                    "feedback_message": "",
                    "active_conversation_id": (
                        active_conversation.id if active_conversation else ""
                    ),
                    "conversation_messages": (
                        self._conversation_messages(active_conversation)
                        if authenticated_username
                        else self._guest_conversation_messages(request)
                    ),
                    "conversations": (
                        self._conversation_list(user_id)
                        if authenticated_username
                        else []
                    ),
                    "user_id": user_id,
                    "is_guest_chat": not authenticated_username,
                    "mode": mode,
                    "language": language,
                    "message": message,
                    "starter_prompts": starter_prompts,
                    "recent_questions": recent_questions,
                    "follow_up_prompts": [],
                },
            )

        if is_risky_prompt(message):
            _log_ask_event(
                user_id=user_id,
                source=AskEvent.SOURCE_CHAT_UI,
                mode=mode,
                outcome=AskEvent.OUTCOME_BLOCKED_SAFETY,
                plan=UserSubscription.PLAN_FREE,
            )
            return self._render_chat_ui(
                request,
                {
                    "response_data": None,
                    "error": (
                        "This app cannot provide crisis/self-harm or "
                        "medical/legal guidance. Please seek local "
                        "professional support "
                        "immediately."
                    ),
                    "feedback_message": "",
                    "active_conversation_id": (
                        active_conversation.id if active_conversation else ""
                    ),
                    "conversation_messages": (
                        self._conversation_messages(active_conversation)
                        if authenticated_username
                        else self._guest_conversation_messages(request)
                    ),
                    "conversations": (
                        self._conversation_list(user_id)
                        if authenticated_username
                        else []
                    ),
                    "user_id": user_id,
                    "is_guest_chat": not authenticated_username,
                    "mode": mode,
                    "language": language,
                    "message": message,
                    "starter_prompts": starter_prompts,
                    "recent_questions": recent_questions,
                    "follow_up_prompts": [],
                },
            )

        quota = (
            self._resolve_chat_ui_quota(user_id)
            if authenticated_username
            else None
        )
        if (
            quota
            and quota["daily_limit"] is not None
            and quota["usage"].ask_count >= quota["daily_limit"]
        ):
            _log_ask_event(
                user_id=user_id,
                source=AskEvent.SOURCE_CHAT_UI,
                mode=mode,
                outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
                plan=quota["subscription"].plan,
            )
            return self._render_chat_ui(
                request,
                {
                    "response_data": None,
                    "error": (
                        "Daily ask limit reached for this user plan "
                        "in chat UI. "
                        "Switch to Pro or try tomorrow."
                    ),
                    "feedback_message": "",
                    "active_conversation_id": (
                        active_conversation.id if active_conversation else ""
                    ),
                    "conversation_messages": (
                        self._conversation_messages(active_conversation)
                        if authenticated_username
                        else self._guest_conversation_messages(request)
                    ),
                    "conversations": (
                        self._conversation_list(user_id)
                        if authenticated_username
                        else []
                    ),
                    "user_id": user_id,
                    "is_guest_chat": not authenticated_username,
                    "mode": mode,
                    "message": message,
                    "selected_plan": quota["subscription"].plan,
                    "quota_snapshot": {
                        "plan": quota["subscription"].plan,
                        "daily_limit": quota["daily_limit"],
                        "used_today": quota["usage"].ask_count,
                        "remaining_today": 0,
                    },
                    "starter_prompts": starter_prompts,
                    "recent_questions": recent_questions,
                    "follow_up_prompts": [],
                },
            )

        guest_quota_snapshot = None
        if not authenticated_username:
            guest_quota_result = self._consume_guest_conversation_slot(request)
            guest_quota_snapshot = guest_quota_result["snapshot"]
            if not guest_quota_result["allowed"]:
                _log_ask_event(
                    user_id=user_id,
                    source=AskEvent.SOURCE_CHAT_UI,
                    mode=mode,
                    outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
                    plan=UserSubscription.PLAN_FREE,
                )
                return self._render_chat_ui(
                    request,
                    {
                        "response_data": None,
                        "error": (
                            "You have already used all 3 guest questions "
                            "in this browser. Sign up or log in to continue."
                        ),
                        "feedback_message": "",
                        "active_conversation_id": "",
                        "conversation_messages": self._guest_conversation_messages(
                            request,
                        ),
                        "conversations": [],
                        "user_id": user_id,
                        "is_guest_chat": True,
                        "mode": mode,
                        "language": language,
                        "message": message,
                        "starter_prompts": starter_prompts,
                        "recent_questions": recent_questions,
                        "follow_up_prompts": [],
                        "guest_quota_snapshot": guest_quota_snapshot,
                    },
                )

        try:
            if authenticated_username:
                conversation, verses, guidance, retrieval = _run_guidance_flow(
                    user_id=user_id,
                    message=message,
                    mode=mode,
                    language=language,
                    conversation_id=(
                        active_conversation.id if active_conversation else None
                    ),
                )
                conversation_messages = self._conversation_messages(conversation)
                active_conversation_id = conversation.id
                conversation_page = self._conversation_page(
                    user_id,
                    limit=3,
                    offset=0,
                )
                conversations = conversation_page["items"]
            else:
                verses, guidance, retrieval = self._run_guest_guidance_flow(
                    request,
                    message=message,
                    mode=mode,
                    language=language,
                )
                conversation = None
                conversation_messages = self._guest_conversation_messages(request)
                active_conversation_id = ""
                conversations = []
                conversation_page = {
                    "items": [],
                    "has_more": False,
                    "next_offset": None,
                }
        except Exception:
            logger.exception(
                "chat_ui_ask_failed",
                extra={
                    "path": request.path,
                    "method": request.method,
                    "is_guest_chat": not authenticated_username,
                    "user_id": user_id,
                    "mode": mode,
                    "language": language,
                    "message_len": len(message),
                    "has_follow_up_intent": bool(follow_up_intent),
                    "active_conversation_id": (
                        active_conversation.id
                        if (active_conversation and authenticated_username)
                        else ""
                    ),
                    "guest_id": str(getattr(request, "chat_ui_guest_id", ""))[:12],
                    "referer": request.META.get("HTTP_REFERER", ""),
                },
            )
            guest_error_messages = self._guest_conversation_messages(request)
            if not authenticated_username and not guest_error_messages and message:
                guest_error_messages = [
                    {
                        "role": Message.ROLE_USER,
                        "content": message,
                    }
                ]
            return self._render_chat_ui(
                request,
                {
                    "response_data": None,
                    "error": (
                        "We hit a temporary issue while processing your question. "
                        "Please try again."
                    ),
                    "feedback_message": "",
                    "active_conversation_id": (
                        active_conversation.id if active_conversation else ""
                    ),
                    "conversation_messages": (
                        self._conversation_messages(active_conversation)
                        if authenticated_username
                        else guest_error_messages
                    ),
                    "conversations": (
                        self._conversation_list(user_id)
                        if authenticated_username
                        else []
                    ),
                    "user_id": user_id,
                    "is_guest_chat": not authenticated_username,
                    "mode": mode,
                    "language": language,
                    "message": message,
                    "starter_prompts": starter_prompts,
                    "recent_questions": recent_questions,
                    "follow_up_prompts": [],
                    "guest_quota_snapshot": guest_quota_snapshot,
                    "selected_plan": (
                        quota["subscription"].plan if quota else "free"
                    ),
                },
            )
        response_data = {
            "conversation_id": active_conversation_id,
            "guidance": guidance.guidance,
            "verses": VerseSerializer(verses, many=True).data,
            "meaning": guidance.meaning,
            "actions": guidance.actions,
            "reflection": guidance.reflection,
            "verse_references": [
                f"{verse.chapter}.{verse.verse}" for verse in verses
            ],
            "language": language,
        }
        follow_ups = _build_contextual_follow_ups(
            message=message,
            mode=mode,
            language=language,
            query_themes=retrieval.query_themes,
        )
        response_data["follow_ups"] = follow_ups
        _log_follow_up_events(
            user_id=user_id,
            source=FollowUpEvent.SOURCE_CHAT_UI,
            event_type=FollowUpEvent.EVENT_SHOWN,
            mode=mode,
            follow_ups=follow_ups,
        )
        if follow_up_intent:
            _log_follow_up_events(
                user_id=user_id,
                source=FollowUpEvent.SOURCE_CHAT_UI,
                event_type=FollowUpEvent.EVENT_CLICKED,
                mode=mode,
                follow_ups=[
                    {
                        "intent": follow_up_intent,
                        "prompt": message,
                    }
                ],
            )
        if quota:
            quota["usage"].ask_count += 1
            quota["usage"].save(update_fields=["ask_count"])
            response_data["plan"] = quota["subscription"].plan
            response_data["daily_limit"] = quota["daily_limit"]
            response_data["used_today"] = quota["usage"].ask_count
            response_data["remaining_today"] = _remaining_today(
                daily_limit=quota["daily_limit"],
                used_today=quota["usage"].ask_count,
            )
        _log_ask_event(
            user_id=user_id,
            source=AskEvent.SOURCE_CHAT_UI,
            mode=mode,
            outcome=AskEvent.OUTCOME_SERVED,
            response_mode=guidance.response_mode,
            retrieval_mode=retrieval.retrieval_mode,
            plan=(
                quota["subscription"].plan
                if quota
                else UserSubscription.PLAN_FREE
            ),
        )
        if settings.DEBUG:
            response_data["response_mode"] = guidance.response_mode
            response_data["retrieval_mode"] = retrieval.retrieval_mode
            response_data["retrieved_references"] = [
                verse["reference"] for verse in response_data["verses"]
            ]
            response_data["retrieval_scores"] = retrieval.retrieval_scores
            response_data["query_themes"] = retrieval.query_themes

        self._store_recent_question(request, message)
        updated_recent_questions = self._recent_questions(request)

        return self._render_chat_ui(
            request,
            {
                "response_data": response_data,
                "error": "",
                "feedback_message": "",
                "active_conversation_id": active_conversation_id,
                "conversation_messages": conversation_messages,
                "conversations": conversations,
                "conversations_has_more": conversation_page["has_more"],
                "conversations_next_offset": conversation_page["next_offset"],
                "user_id": user_id,
                "is_guest_chat": not authenticated_username,
                "mode": mode,
                "language": language,
                "message": "",  # Clear the input after a successful ask
                "selected_plan": (
                    response_data.get("plan")
                    if response_data.get("plan")
                    else "free"
                ),
                "quota_snapshot": {
                    "plan": response_data.get("plan", "free"),
                    "daily_limit": response_data.get("daily_limit", "N/A"),
                    "used_today": response_data.get("used_today", "N/A"),
                    "remaining_today": response_data.get(
                        "remaining_today",
                        "N/A",
                    ),
                },
                "starter_prompts": starter_prompts,
                "recent_questions": updated_recent_questions,
                "follow_up_prompts": response_data.get("follow_ups", []),
                "saved_reflections": (
                    self._saved_reflections_for_user(
                        request,
                        user_id,
                    )
                    if authenticated_username
                    else []
                ),
                "guest_quota_snapshot": guest_quota_snapshot,
            },
        )

    def _handle_feedback(self, request):
        """Persist feedback submitted via manual chat UI."""
        user_id = self._chat_ui_authenticated_username(request)
        current_language = self._chat_ui_language(
            request.POST.get("language", "en"),
        )
        if not user_id:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "Login is required before saving feedback to your "
                        "account."
                    ),
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "is_guest_chat": True,
                    "mode": request.POST.get("mode", "simple"),
                    "language": current_language,
                    "message": request.POST.get("message", ""),
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "conversation_messages": self._guest_conversation_messages(
                        request,
                    ),
                    "conversations": [],
                },
            )
        message = request.POST.get("message", "").strip()
        mode = request.POST.get("mode", "simple").strip()
        response_mode = request.POST.get("response_mode", "fallback").strip()
        note = request.POST.get("note", "").strip()
        helpful_value = request.POST.get("helpful", "").strip().lower()
        conversation_id = request.POST.get("conversation_id")

        helpful = helpful_value == "true"
        if helpful_value not in {"true", "false"}:
            active_conversation = self._chat_ui_conversation(
                user_id,
                conversation_id,
            )
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Invalid feedback value.",
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": mode,
                    "language": current_language,
                    "message": message,
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "saved_reflections": self._saved_reflections_for_user(
                        request,
                        user_id,
                    ),
                    "active_conversation_id": (
                        active_conversation.id if active_conversation else ""
                    ),
                    "conversation_messages": self._conversation_messages(
                        active_conversation,
                    ),
                    "conversations": self._conversation_list(user_id),
                },
            )

        if mode not in {"simple", "deep"}:
            mode = "simple"
        if response_mode not in {"llm", "fallback"}:
            response_mode = "fallback"

        conversation = None
        if conversation_id:
            conversation = Conversation.objects.filter(
                id=conversation_id,
                user_id=user_id,
            ).first()

        ResponseFeedback.objects.create(
            conversation=conversation,
            user_id=user_id,
            message=message,
            mode=mode,
            response_mode=response_mode,
            helpful=helpful,
            note=note,
        )

        active_conversation = self._chat_ui_conversation(
            user_id,
            conversation_id,
        )
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "Thank you. Your feedback was saved.",
                "user_id": user_id,
                "mode": mode,
                "language": current_language,
                "message": message,
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user_id,
                ),
                "active_conversation_id": (
                    active_conversation.id if active_conversation else ""
                ),
                "conversation_messages": self._conversation_messages(
                    active_conversation,
                ),
                "conversations": self._conversation_list(user_id),
            },
        )

    def _handle_save_reflection(self, request):
        """Save current response into bookmarks for existing usernames."""
        user_id = self._chat_ui_authenticated_username(request)
        current_language = self._chat_ui_language(
            request.POST.get("language", "en"),
        )
        if not user_id:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "Saving reflections requires login so bookmarks stay "
                        "attached to your account."
                    ),
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "is_guest_chat": True,
                    "mode": request.POST.get("mode", "simple"),
                    "language": current_language,
                    "message": request.POST.get("message", ""),
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "saved_reflections": [],
                    "conversation_messages": self._guest_conversation_messages(
                        request,
                    ),
                    "conversations": [],
                },
            )
        user_model = get_user_model()
        user = user_model.objects.filter(username=user_id).first()
        if user is None:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "Saving reflections requires an existing auth user. "
                        "Create/login user first."
                    ),
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": request.POST.get("mode", "simple"),
                    "language": current_language,
                    "message": request.POST.get("message", ""),
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "saved_reflections": [],
                },
            )

        conversation = None
        conversation_id = request.POST.get("conversation_id")
        if conversation_id and str(conversation_id).isdigit():
            conversation = Conversation.objects.filter(
                id=int(conversation_id),
                user_id=user.get_username(),
            ).first()

        actions_raw = request.POST.get("actions", "")
        actions = [
            item.strip() for item in actions_raw.split("|") if item.strip()
        ]
        refs_raw = request.POST.get("verse_references", "")
        verse_references = [
            item.strip() for item in refs_raw.split("|") if item.strip()
        ]

        SavedReflection.objects.create(
            user=user,
            conversation=conversation,
            message=request.POST.get("message", "").strip(),
            guidance=request.POST.get("guidance", "").strip(),
            meaning=request.POST.get("meaning", "").strip(),
            actions=actions,
            reflection=request.POST.get("reflection", "").strip(),
            verse_references=verse_references,
            note=request.POST.get("note", "").strip(),
        )
        active_conversation = self._chat_ui_conversation(
            user_id,
            conversation_id,
        )
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "Reflection saved.",
                "user_id": user_id,
                "mode": request.POST.get("mode", "simple"),
                "language": current_language,
                "message": request.POST.get("message", ""),
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user_id,
                ),
                "active_conversation_id": (
                    active_conversation.id if active_conversation else ""
                ),
                "conversation_messages": self._conversation_messages(
                    active_conversation,
                ),
                "conversations": self._conversation_list(user_id),
            },
        )

    @staticmethod
    def _conversation_limit(raw_value: str) -> int:
        """Parse sidebar page size with a fixed, safe cap."""
        try:
            value = int(str(raw_value).strip())
        except ValueError:
            return 3
        if value <= 0:
            return 3
        return min(value, 10)

    @staticmethod
    def _conversation_offset(raw_value: str) -> int:
        """Parse sidebar offset for incremental loading."""
        try:
            value = int(str(raw_value).strip())
        except ValueError:
            return 0
        return max(value, 0)

    @staticmethod
    def _conversation_page(user_id: str, *, limit: int, offset: int) -> dict:
        """Return one conversation page for sidebar infinite scroll."""
        queryset = (
            Conversation.objects.filter(user_id=user_id)
            .prefetch_related("messages")
            .order_by("-updated_at")
        )
        total = queryset.count()
        rows = list(queryset[offset:offset + limit])
        items = []
        for row in rows:
            messages = list(row.messages.all())
            title = ChatUIView._conversation_title(messages, row.id)
            last_message = messages[-1].content.strip() if messages else ""
            items.append(
                {
                    "id": row.id,
                    "title": title,
                    "preview": ChatUIView._truncate_text(
                        last_message or "No messages yet.",
                        84,
                    ),
                    "message_count": len(messages),
                    "message_count_label": ChatUIView._message_count_label(
                        len(messages),
                    ),
                    "updated_label": ChatUIView._relative_timestamp(
                        row.updated_at,
                    ),
                    "updated_at_display": timezone.localtime(
                        row.updated_at,
                    ).strftime("%d %b %Y, %I:%M %p"),
                }
            )
        has_more = (offset + limit) < total
        return {
            "items": items,
            "has_more": has_more,
            "next_offset": (offset + limit) if has_more else None,
        }

    @staticmethod
    def _saved_reflections_for_user(request, user_id: str) -> list[dict]:
        """Return last saved reflections for a known username."""
        user_model = get_user_model()
        user = user_model.objects.filter(username=user_id).first()
        if user is None:
            return []
        rows = SavedReflection.objects.filter(user=user)[:5]
        return [
            {
                "id": row.id,
                "message": row.message,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    @staticmethod
    def _conversation_messages(conversation) -> list[dict]:
        """Return current conversation as simple role/content rows."""
        if conversation is None:
            return []
        return [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in conversation.messages.all()
        ]

    @staticmethod
    def _chat_ui_conversation(user_id: str, conversation_id=None):
        """Resolve requested conversation or return None for landing page."""
        if conversation_id is None:
            # No conversation_id in URL means show landing page, not latest
            return None
        if str(conversation_id).strip() == "":
            # An explicit blank id means "start a new thread" rather than
            # silently reopening the most recent saved conversation.
            return None
        queryset = (
            Conversation.objects.filter(user_id=user_id)
            .prefetch_related("messages")
            .order_by("-updated_at")
        )
        if conversation_id and str(conversation_id).isdigit():
            conversation = queryset.filter(id=int(conversation_id)).first()
            if conversation is not None:
                return conversation
        return None

    @staticmethod
    def _conversation_list(user_id: str) -> list[dict]:
        """Return first page of conversations for backward-compatible calls."""
        return ChatUIView._conversation_page(
            user_id,
            limit=3,
            offset=0,
        )["items"]

    def _run_guest_guidance_flow(
        self,
        request,
        *,
        message: str,
        mode: str,
        language: str = "en",
    ):
        """Generate a guest-mode answer without persisting any DB history."""
        guest_messages = self._guest_conversation_objects(request)
        conversation_messages = guest_messages + [
            SimpleNamespace(role=Message.ROLE_USER, content=message)
        ]
        retrieval = retrieve_verses_with_trace(
            message=message,
            limit=4 if mode == "deep" else 3,
        )
        verses = retrieval.verses
        guidance = build_guidance(
            message,
            verses,
            conversation_messages=conversation_messages,
            language=language,
            query_interpretation=retrieval.query_interpretation,
        )
        self._append_guest_exchange(
            request,
            user_message=message,
            assistant_message=guidance.guidance,
        )
        return verses, guidance, retrieval

    def _handle_delete_conversation(self, request):
        """Delete a sidebar thread without resetting the whole chat UI."""
        current_mode = self._chat_ui_mode(request.POST.get("mode", "simple"))
        current_language = self._chat_ui_language(
            request.POST.get("language", "en"),
        )
        user_id = self._chat_ui_authenticated_username(request)
        if not user_id:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Guest chats are temporary, so there is no saved history to delete.",
                    "feedback_message": "",
                    "selected_plan": "free",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "saved_reflections": [],
                    "active_conversation_id": "",
                    "conversation_messages": self._guest_conversation_messages(
                        request,
                    ),
                    "conversations": [],
                    "user_id": self._default_user_id(request),
                    "is_guest_chat": True,
                    "mode": current_mode,
                    "language": current_language,
                    "message": "",
                },
            )
        delete_id = request.POST.get("conversation_id", "").strip()
        active_id = request.POST.get("active_conversation_id", "").strip()
        active_conversation = self._chat_ui_conversation(user_id, active_id)

        if not delete_id.isdigit():
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Could not find that conversation to delete.",
                    "feedback_message": "",
                    "selected_plan": "free",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "saved_reflections": self._saved_reflections_for_user(
                        request,
                        user_id,
                    ),
                    "active_conversation_id": (
                        active_conversation.id if active_conversation else ""
                    ),
                    "conversation_messages": self._conversation_messages(
                        active_conversation,
                    ),
                    "conversations": self._conversation_list(user_id),
                    "user_id": user_id,
                    "mode": current_mode,
                    "language": current_language,
                    "message": "",
                },
            )

        conversation = Conversation.objects.filter(
            id=int(delete_id),
            user_id=user_id,
        ).first()
        if conversation is None:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Could not find that conversation to delete.",
                    "feedback_message": "",
                    "selected_plan": "free",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "saved_reflections": self._saved_reflections_for_user(
                        request,
                        user_id,
                    ),
                    "active_conversation_id": (
                        active_conversation.id if active_conversation else ""
                    ),
                    "conversation_messages": self._conversation_messages(
                        active_conversation,
                    ),
                    "conversations": self._conversation_list(user_id),
                    "user_id": user_id,
                    "mode": current_mode,
                    "language": current_language,
                    "message": "",
                },
            )

        was_active = active_id.isdigit() and int(active_id) == conversation.id
        conversation.delete()
        if was_active:
            active_conversation = None

        # Sidebar thread deletion should only change thread state, not wipe
        # out unrelated controls like saved reflections or the plan panel.
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "Conversation deleted.",
                "selected_plan": "free",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user_id,
                ),
                "active_conversation_id": (
                    active_conversation.id if active_conversation else ""
                ),
                "conversation_messages": self._conversation_messages(
                    active_conversation,
                ),
                "conversations": self._conversation_list(user_id),
                "user_id": user_id,
                "is_guest_chat": False,
                "mode": current_mode,
                "language": current_language,
                "message": "",
            },
        )

    @staticmethod
    def _conversation_title(messages: list[Message], conversation_id: int) -> str:
        """Build a stable sidebar label from the first user-authored prompt."""
        for message in messages:
            if message.role == Message.ROLE_USER and message.content:
                return ChatUIView._truncate_text(message.content, 60)
        return f"Conversation {conversation_id}"

    @staticmethod
    def _truncate_text(value: str, limit: int) -> str:
        """Collapse whitespace before trimming for compact UI cards."""
        normalized = " ".join(value.split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 3].rstrip()}..."

    @staticmethod
    def _message_count_label(message_count: int) -> str:
        """Return a singular/plural sidebar count label."""
        suffix = "message" if message_count == 1 else "messages"
        return f"{message_count} {suffix}"

    @staticmethod
    def _relative_timestamp(value) -> str:
        """Return short relative timestamps for conversation cards."""
        now = timezone.now()
        if value >= now - timedelta(seconds=60):
            return "just now"
        return f"{timesince(value, now).split(',')[0]} ago"

    def _resolve_chat_ui_quota(self, user_id: str):
        """Return quota context when chat-ui user maps to a real auth user."""
        user_model = get_user_model()
        user = user_model.objects.filter(username=user_id).first()
        if user is None:
            return None
        subscription, usage = _get_user_plan_and_usage(user)
        return {
            "subscription": subscription,
            "usage": usage,
            "daily_limit": _plan_daily_limit(subscription.plan),
        }

    def _handle_plan_update(self, request):
        """Allow chat-ui testers to switch plan for known usernames."""
        user_id = self._chat_ui_authenticated_username(request)
        current_language = self._chat_ui_language(
            request.POST.get("language", "en"),
        )
        if not user_id:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "Plan updates require login so quota changes apply "
                        "only to your own account."
                    ),
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "is_guest_chat": True,
                    "mode": request.POST.get("mode", "simple"),
                    "language": current_language,
                    "message": request.POST.get("message", ""),
                    "selected_plan": request.POST.get("selected_plan", "free"),
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "conversation_messages": self._guest_conversation_messages(
                        request,
                    ),
                    "conversations": [],
                },
            )
        selected_plan = request.POST.get("selected_plan", "free").strip()
        if selected_plan not in {
            UserSubscription.PLAN_FREE,
            UserSubscription.PLAN_PRO,
        }:
            selected_plan = UserSubscription.PLAN_FREE
        quota = self._resolve_chat_ui_quota(user_id)
        if quota is None:
            active_conversation = self._chat_ui_conversation(user_id)
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": (
                        "Plan update works only for existing auth usernames. "
                        "Create/login user first."
                    ),
                    "feedback_message": "",
                    "user_id": user_id,
                    "mode": request.POST.get("mode", "simple"),
                    "language": current_language,
                    "message": request.POST.get("message", ""),
                    "selected_plan": selected_plan,
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                    "saved_reflections": self._saved_reflections_for_user(
                        request,
                        user_id,
                    ),
                    "active_conversation_id": (
                        active_conversation.id if active_conversation else ""
                    ),
                    "conversation_messages": self._conversation_messages(
                        active_conversation,
                    ),
                    "conversations": self._conversation_list(user_id),
                },
            )

        subscription = quota["subscription"]
        subscription.plan = selected_plan
        subscription.save(update_fields=["plan", "updated_at"])
        refreshed = self._resolve_chat_ui_quota(user_id)
        active_conversation = self._chat_ui_conversation(user_id)
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": f"Plan updated to {selected_plan}.",
                "user_id": user_id,
                "mode": request.POST.get("mode", "simple"),
                "language": current_language,
                "message": request.POST.get("message", ""),
                "selected_plan": selected_plan,
                "quota_snapshot": {
                    "plan": selected_plan,
                    "daily_limit": refreshed["daily_limit"],
                    "used_today": refreshed["usage"].ask_count,
                    "remaining_today": max(
                        refreshed["daily_limit"]
                        - refreshed["usage"].ask_count,
                        0,
                    ),
                },
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user_id,
                ),
                "active_conversation_id": (
                    active_conversation.id if active_conversation else ""
                ),
                "conversation_messages": self._conversation_messages(
                    active_conversation,
                ),
                "conversations": self._conversation_list(user_id),
            },
        )

    def _handle_support_request(self, request):
        """Store support tickets from chat UI and return user confirmation."""
        authenticated_username = self._chat_ui_authenticated_username(request)
        user_id = authenticated_username or "guest"
        current_mode = self._chat_ui_mode(request.POST.get("mode", "simple"))
        current_language = self._chat_ui_language(
            request.POST.get("language", "en"),
        )
        active_conversation = (
            self._chat_ui_conversation(
                user_id,
                request.POST.get("conversation_id"),
            )
            if authenticated_username
            else None
        )
        conversation_page = (
            self._conversation_page(user_id, limit=3, offset=0)
            if authenticated_username
            else {"items": [], "has_more": False, "next_offset": None}
        )

        payload = {
            "name": request.POST.get("support_name", "").strip(),
            "email": request.POST.get("support_email", "").strip(),
            "issue_type": request.POST.get("support_issue_type", "other").strip(),
            "message": request.POST.get("support_message", "").strip(),
        }
        serializer = SupportRequestSerializer(data=payload)
        if serializer.is_valid():
            data = serializer.validated_data
            auth_user = request.user if request.user.is_authenticated else None
            SupportTicket.objects.create(
                user=auth_user,
                requester_id=(
                    auth_user.get_username() if auth_user else user_id
                ),
                name=data["name"],
                email=data["email"],
                issue_type=data["issue_type"],
                message=data["message"],
            )
            feedback_message = (
                "Support request submitted. We will contact you soon."
            )
            error = ""
        else:
            feedback_message = ""
            error = "Please complete all support fields with valid details."

        return self._render_chat_ui(
            request,
            {
                "response_data": None,
                "error": error,
                "feedback_message": feedback_message,
                "selected_plan": "free",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": (
                    self._saved_reflections_for_user(request, user_id)
                    if authenticated_username
                    else []
                ),
                "active_conversation_id": (
                    active_conversation.id if active_conversation else ""
                ),
                "conversation_messages": (
                    self._conversation_messages(active_conversation)
                    if authenticated_username
                    else self._guest_conversation_messages(request)
                ),
                "conversations": conversation_page["items"],
                "conversations_has_more": conversation_page["has_more"],
                "conversations_next_offset": conversation_page["next_offset"],
                "user_id": user_id,
                "is_guest_chat": not authenticated_username,
                "mode": current_mode,
                "language": current_language,
                "message": "",
                "support_issue_type": payload["issue_type"],
                "support_name": payload["name"],
                "support_form_email": payload["email"],
                "support_message": payload["message"],
            },
        )

    def _handle_register(self, request):
        """Register user from chat-ui panel and persist session token."""
        username = str(request.POST.get("register_username", "")).strip()
        password = str(request.POST.get("register_password", "")).strip()
        current_language = self._chat_ui_language(
            request.POST.get("language", "en"),
        )
        if not username or not password:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Please enter username and password to register.",
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "mode": "simple",
                    "language": current_language,
                    "message": "",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )
        if len(password) < 8:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Password must be at least 8 characters.",
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "mode": "simple",
                    "language": current_language,
                    "message": "",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Username is already taken.",
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "mode": "simple",
                    "language": current_language,
                    "message": "",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )
        user = user_model.objects.create_user(
            username=username,
            password=password,
        )
        token, _ = Token.objects.get_or_create(user=user)
        request.session["chat_ui_auth_username"] = user.username
        request.session["chat_ui_auth_token"] = token.key
        self._clear_guest_conversation(request)
        # Hydrate sidebar history immediately after auth so the signed-in user
        # sees their own saved chat list without needing to send a new message.
        active_conversation = self._chat_ui_conversation(user.username)
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": (
                    f"Registered and logged in as {user.username}."
                ),
                "user_id": user.username,
                "is_guest_chat": False,
                "mode": "simple",
                "language": current_language,
                "message": "",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user.username,
                ),
                "active_conversation_id": (
                    active_conversation.id if active_conversation else ""
                ),
                "conversation_messages": self._conversation_messages(
                    active_conversation,
                ),
                "conversations": self._conversation_list(user.username),
            },
        )

    def _handle_login(self, request):
        """Authenticate user from chat-ui and persist auth session values."""
        username = str(request.POST.get("login_username", "")).strip()
        password = str(request.POST.get("login_password", "")).strip()
        current_language = self._chat_ui_language(
            request.POST.get("language", "en"),
        )
        user = authenticate(
            request=request,
            username=username,
            password=password,
        )
        if user is None:
            return render(
                request,
                self.template_name,
                {
                    "response_data": None,
                    "error": "Invalid username or password.",
                    "feedback_message": "",
                    "user_id": self._default_user_id(request),
                    "mode": "simple",
                    "language": current_language,
                    "message": "",
                    "starter_prompts": self._starter_prompts(),
                    "recent_questions": self._recent_questions(request),
                    "follow_up_prompts": [],
                },
            )
        token, _ = Token.objects.get_or_create(user=user)
        request.session["chat_ui_auth_username"] = user.username
        request.session["chat_ui_auth_token"] = token.key
        self._clear_guest_conversation(request)
        # Show the user's existing threads right after login so account
        # ownership feels obvious and they can reopen history immediately.
        active_conversation = self._chat_ui_conversation(user.username)
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": f"Logged in as {user.username}.",
                "user_id": user.username,
                "is_guest_chat": False,
                "mode": "simple",
                "language": current_language,
                "message": "",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": self._saved_reflections_for_user(
                    request,
                    user.username,
                ),
                "active_conversation_id": (
                    active_conversation.id if active_conversation else ""
                ),
                "conversation_messages": self._conversation_messages(
                    active_conversation,
                ),
                "conversations": self._conversation_list(user.username),
            },
        )

    def _handle_logout(self, request):
        """Logout chat-ui user by clearing stored session token."""
        current_language = self._chat_ui_language(
            request.POST.get("language", "en"),
        )
        token_key = request.session.get("chat_ui_auth_token")
        if token_key:
            Token.objects.filter(key=token_key).delete()
        request.session.pop("chat_ui_auth_username", None)
        request.session.pop("chat_ui_auth_token", None)
        self._clear_guest_conversation(request)
        return render(
            request,
            self.template_name,
            {
                "response_data": None,
                "error": "",
                "feedback_message": "Logged out.",
                "user_id": "guest",
                "is_guest_chat": True,
                "mode": "simple",
                "language": current_language,
                "message": "",
                "starter_prompts": self._starter_prompts(),
                "recent_questions": self._recent_questions(request),
                "follow_up_prompts": [],
                "saved_reflections": [],
                "conversation_messages": [],
                "conversations": [],
            },
        )

    @staticmethod
    def _default_user_id(request) -> str:
        """Resolve default chat-ui user from session fallback."""
        return str(request.session.get("chat_ui_auth_username", "guest"))

    @staticmethod
    def _chat_ui_mode(value: str) -> str:
        """Normalize chat-ui mode so sidebar selection is globally stable."""
        return value if value in {"simple", "deep"} else "simple"

    @staticmethod
    def _chat_ui_language(value: str) -> str:
        """Normalize chat-ui language selector to supported values."""
        return value if value in {"en", "hi"} else "en"

    @staticmethod
    def _chat_ui_authenticated_username(request) -> str:
        """Return the logged-in chat-ui username, or blank for guest mode."""
        return str(request.session.get("chat_ui_auth_username", "")).strip()

    @staticmethod
    def _guest_conversation_messages(request) -> list[dict]:
        """Return the temporary guest transcript stored only in session."""
        return list(request.session.get("chat_ui_guest_messages", []))

    @staticmethod
    def _guest_conversation_objects(request) -> list[SimpleNamespace]:
        """Convert guest transcript dicts into prompt-friendly message objects."""
        return [
            SimpleNamespace(
                role=item.get("role", ""),
                content=item.get("content", ""),
            )
            for item in request.session.get("chat_ui_guest_messages", [])
        ]

    @staticmethod
    def _append_guest_exchange(
        request,
        *,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Persist only a short-lived guest transcript in the browser session."""
        guest_messages = list(request.session.get("chat_ui_guest_messages", []))
        timestamp = timezone.now().isoformat()
        guest_messages.extend(
            [
                {
                    "role": Message.ROLE_USER,
                    "content": user_message,
                    "created_at": timestamp,
                },
                {
                    "role": Message.ROLE_ASSISTANT,
                    "content": assistant_message,
                    "created_at": timestamp,
                },
            ]
        )
        request.session["chat_ui_guest_messages"] = guest_messages[-12:]
        request.session.modified = True

    @staticmethod
    def _clear_guest_conversation(request) -> None:
        """Drop the temporary guest transcript from the current session."""
        request.session.pop("chat_ui_guest_messages", None)

    @staticmethod
    def _starter_prompts() -> list[str]:
        """Return curated first-question prompts for quick onboarding."""
        return [
            "I feel anxious about my career growth and future. What should I do?",
            "I get angry quickly in relationships. How can I respond with more control?",
            "I feel stuck and directionless. How do I find purpose and direction?",
            "I procrastinate and lose discipline. What daily practice should I start?",
        ]

    @staticmethod
    def _follow_up_prompts() -> list[str]:
        """Return actionable follow-up prompts shown after each response."""
        return [
            "Give me a 3-step plan for today based on these verses.",
            "Explain one verse in simpler words for my situation.",
            "Ask me one reflection question to continue this conversation.",
        ]

    @staticmethod
    def _recent_questions(request) -> list[str]:
        """Read the latest chat-ui questions from session state."""
        items = request.session.get("chat_ui_recent_questions", [])
        if isinstance(items, list):
            return [str(item) for item in items[:3]]
        return []

    @staticmethod
    def _store_recent_question(request, message: str) -> None:
        """Store most recent unique questions for one-click reuse."""
        message = message.strip()
        if not message:
            return
        existing = request.session.get("chat_ui_recent_questions", [])
        if not isinstance(existing, list):
            existing = []
        updated = [message] + [item for item in existing if item != message]
        request.session["chat_ui_recent_questions"] = updated[:3]


# =============================================================================
# Payment Views - Razorpay Integration
# =============================================================================


def _get_user_from_session(request):
    """Get authenticated user from session token (for chat-ui auth)."""
    # In DRF APIView, access session from the underlying Django request
    session = getattr(request, 'session', None)
    if session is None:
        session = getattr(request, '_request', request).session

    # First try by username (more reliable)
    username = session.get("chat_ui_auth_username")
    if username:
        User = get_user_model()
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            pass

    # Fallback to token
        return None


class CsrfExemptSessionAuth(SessionAuthentication):
    """Session auth without CSRF enforcement for API calls."""
    def enforce_csrf(self, request):
        return  # Skip CSRF check - we handle it differently


class CreateOrderView(APIView):
    """Create a Razorpay order for subscription payment."""

    permission_classes = [AllowAny]
    authentication_classes = [CsrfExemptSessionAuth]

    def post(self, request) -> Response:
        import razorpay

        # Get user - first try DRF auth, then session lookup
        user = None
        if request.user and request.user.is_authenticated:
            user = request.user
        else:
            user = _get_user_from_session(request)

        if not user:
            return Response(
                {"error": "Please log in to subscribe"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        key_id = settings.RAZORPAY_KEY_ID
        key_secret = settings.RAZORPAY_KEY_SECRET

        if not key_id or not key_secret:
            return Response(
                {"error": "Payment gateway not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Determine currency based on request or default to INR
        currency = request.data.get("currency", "INR").upper()
        if currency == "INR":
            amount = settings.SUBSCRIPTION_PRICE_INR
        else:
            currency = "USD"
            amount = settings.SUBSCRIPTION_PRICE_USD

        client = razorpay.Client(auth=(key_id, key_secret))

        try:
            order_data = {
                "amount": amount,
                "currency": currency,
                "receipt": f"sub_{user.id}_{timezone.now().timestamp()}",
                "notes": {
                    "user_id": str(user.id),
                    "plan": UserSubscription.PLAN_PRO,
                },
            }
            order = client.order.create(data=order_data)

            # Store order_id in subscription record
            subscription, _ = UserSubscription.objects.get_or_create(
                user=user,
                defaults={"plan": UserSubscription.PLAN_FREE},
            )
            subscription.razorpay_order_id = order["id"]
            subscription.payment_currency = currency
            subscription.save()

            return Response({
                "order_id": order["id"],
                "amount": amount,
                "currency": currency,
                "key_id": key_id,
                "user_email": user.email,
                "user_name": user.get_full_name() or user.username,
            })

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyPaymentView(APIView):
    """Verify Razorpay payment signature and activate subscription."""

    permission_classes = [AllowAny]
    authentication_classes = [CsrfExemptSessionAuth]

    def post(self, request) -> Response:
        import hmac
        import hashlib

        # Get user - first try DRF auth, then session lookup
        user = None
        if request.user and request.user.is_authenticated:
            user = request.user
        else:
            user = _get_user_from_session(request)

        if not user:
            return Response(
                {"error": "Please log in to verify payment"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        key_id = settings.RAZORPAY_KEY_ID
        key_secret = settings.RAZORPAY_KEY_SECRET

        if not key_id or not key_secret:
            return Response(
                {"error": "Payment gateway not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        razorpay_order_id = request.data.get("razorpay_order_id")
        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_signature = request.data.get("razorpay_signature")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response(
                {"error": "Missing payment verification parameters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify signature
        msg = f"{razorpay_order_id}|{razorpay_payment_id}"
        generated_signature = hmac.new(
            key_secret.encode(),
            msg.encode(),
            hashlib.sha256
        ).hexdigest()

        if generated_signature != razorpay_signature:
            return Response(
                {"error": "Invalid payment signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Activate subscription
        try:
            subscription = UserSubscription.objects.get(user=user)
            if subscription.razorpay_order_id != razorpay_order_id:
                return Response(
                    {"error": "Order ID mismatch"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            subscription.plan = UserSubscription.PLAN_PRO
            subscription.is_active = True
            subscription.subscription_end_date = timezone.now() + timedelta(days=30)
            subscription.save()

            return Response({
                "success": True,
                "message": "Subscription activated successfully",
                "plan": subscription.plan,
                "valid_until": subscription.subscription_end_date.isoformat(),
            })

        except UserSubscription.DoesNotExist:
            return Response(
                {"error": "Subscription not found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class RazorpayWebhookView(APIView):
    """Handle Razorpay webhook callbacks for payment events."""

    # Webhooks don't use normal authentication
    permission_classes = []
    authentication_classes = []

    def post(self, request) -> Response:
        import hmac
        import hashlib
        import json

        webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

        if not webhook_secret:
            return Response(
                {"error": "Webhook not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Verify webhook signature
        webhook_signature = request.headers.get("X-Razorpay-Signature", "")
        webhook_body = request.body.decode()

        expected_signature = hmac.new(
            webhook_secret.encode(),
            webhook_body.encode(),
            hashlib.sha256
        ).hexdigest()

        if expected_signature != webhook_signature:
            return Response(
                {"error": "Invalid webhook signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Process webhook event
        try:
            payload = json.loads(webhook_body)
            event = payload.get("event")

            if event == "payment.captured":
                payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
                order_id = payment_entity.get("order_id")

                if order_id:
                    try:
                        subscription = UserSubscription.objects.get(razorpay_order_id=order_id)
                        subscription.plan = UserSubscription.PLAN_PRO
                        subscription.is_active = True
                        subscription.subscription_end_date = timezone.now() + timedelta(days=30)
                        subscription.save()
                    except UserSubscription.DoesNotExist:
                        pass  # Order not found, ignore

            elif event == "payment.failed":
                # Log failed payment for monitoring
                pass

            return Response({"status": "ok"})

        except json.JSONDecodeError:
            return Response(
                {"error": "Invalid JSON"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class SubscriptionStatusView(APIView):
    """Get current user's subscription status."""

    permission_classes = [AllowAny]
    authentication_classes = [CsrfExemptSessionAuth]

    def get(self, request) -> Response:
        # Get user - first try DRF auth, then session lookup
        user = None
        if request.user and request.user.is_authenticated:
            user = request.user
        else:
            user = _get_user_from_session(request)

        if not user:
            return Response(
                {"error": "Please log in to view subscription status"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        subscription, created = UserSubscription.objects.get_or_create(
            user=user,
            defaults={"plan": UserSubscription.PLAN_FREE},
        )

        is_pro = (
            subscription.plan == UserSubscription.PLAN_PRO
            and subscription.is_active
            and (
                subscription.subscription_end_date is None
                or subscription.subscription_end_date > timezone.now()
            )
        )

        return Response({
            "plan": subscription.plan,
            "is_active": subscription.is_active,
            "is_pro": is_pro,
            "subscription_end_date": (
                subscription.subscription_end_date.isoformat()
                if subscription.subscription_end_date
                else None
            ),
            "pricing": {
                "INR": settings.SUBSCRIPTION_PRICE_INR,
                "USD": settings.SUBSCRIPTION_PRICE_USD,
            },
        })
