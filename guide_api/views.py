"""HTTP views for chat, retrieval evaluation, and feedback flows."""

from datetime import date, timedelta
import json
import logging
import re
import time
from decimal import Decimal
from random import Random
from types import SimpleNamespace
from urllib.parse import quote_plus
from uuid import uuid4

from django.contrib.auth import (
    authenticate,
    get_user_model,
    login as auth_login,
    logout as auth_logout,
)
from django.conf import settings
from django.db.models import Sum
from django.http import HttpResponse, HttpResponsePermanentRedirect, JsonResponse
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
    BillingRecord,
    Conversation,
    DailyAskUsage,
    EngagementEvent,
    FollowUpEvent,
    GrowthEvent,
    GuestChatIdentity,
    Message,
    RequestQuotaSettings,
    ResponseFeedback,
    SavedReflection,
    SharedAnswer,
    SupportTicket,
    UserEngagementProfile,
    UserSubscription,
    Verse,
    WebAudienceProfile,
)
from guide_api.serializers import (
    AnalyticsEventIngestSerializer,
    AnalyticsSummaryRequestSerializer,
    AskRequestSerializer,
    BillingRecordSerializer,
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
    SharedAnswerCreateSerializer,
    SupportRequestSerializer,
    VerseDetailSerializer,
    VerseSerializer,
)
from guide_api.services import (
    build_chapter_explanation,
    build_guidance,
    build_verse_explanation,
    classify_user_intent,
    ensure_seed_verses,
    empty_retrieval_result,
    _fetch_verses_by_references,
    get_related_verses,
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
    refine_verses_for_guidance,
    normalize_chat_user_message,
    resolve_guidance_language,
)


logger = logging.getLogger(__name__)
_QUOTA_SETTINGS_UNSET = object()
_QUOTA_SETTINGS_CACHE_TTL_SECONDS = 60
_quota_settings_cache: dict[str, object] = {
    "value": _QUOTA_SETTINGS_UNSET,
    "loaded_at": 0.0,
}

WEB_AUDIENCE_COOKIE_NAME = "web_audience_id"
WEB_AUDIENCE_COOKIE_AGE = 60 * 60 * 24 * 365

COUNTRY_CODE_TO_NAME = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
    "ZA": "South Africa",
    "AE": "United Arab Emirates",
    "SG": "Singapore",
    "AU": "Australia",
    "CA": "Canada",
}


def _related_verses_payload_for_response(
    *,
    guidance,
    message: str,
    verses: list,
) -> list[dict]:
    """Related exploration verses: LLM-filtered refs when set, else heuristic."""
    if not getattr(guidance, "show_related_verses", True) or not verses:
        return []
    custom = getattr(guidance, "related_verses_refs", None)
    if custom is not None:
        rows = _fetch_verses_by_references(custom)
        return [
            {
                "reference": f"{v.chapter}.{v.verse}",
                "translation": v.translation,
                "themes": v.themes,
            }
            for v in rows
        ]
    return [
        {
            "reference": f"{v.chapter}.{v.verse}",
            "translation": v.translation,
            "themes": v.themes,
        }
        for v in get_related_verses(
            message=message,
            seed_verses=verses,
            limit=6,
        )
    ]


def _resolve_web_audience_id(request) -> str:
    """Resolve stable audience identifier for auth users and guests."""
    if request.user and request.user.is_authenticated:
        return f"user:{request.user.id}"

    cookie_value = str(
        request.COOKIES.get(WEB_AUDIENCE_COOKIE_NAME, ""),
    ).strip()
    if cookie_value:
        return cookie_value[:64]

    audience_id = f"guest:{uuid4().hex}"
    request.web_audience_cookie_to_set = audience_id
    return audience_id


def _track_web_visit(request, *, source: str) -> str:
    """Persist a visit heartbeat for growth analytics."""
    audience_id = _resolve_web_audience_id(request)
    utm_source = str(request.GET.get("utm_source", "")).strip()[:64]
    utm_medium = str(request.GET.get("utm_medium", "")).strip()[:64]
    utm_campaign = str(request.GET.get("utm_campaign", "")).strip()[:64]
    profile, _ = WebAudienceProfile.objects.get_or_create(
        audience_id=audience_id,
        defaults={
            "is_authenticated": bool(
                request.user and request.user.is_authenticated
            ),
            "first_source": source,
            "last_source": source,
            "visit_count": 0,
            "last_path": request.path[:255],
            "first_utm_source": utm_source,
            "first_utm_medium": utm_medium,
            "first_utm_campaign": utm_campaign,
        },
    )

    profile.visit_count += 1
    if not profile.first_source:
        profile.first_source = source
    profile.last_source = source
    profile.last_path = request.path[:255]
    if not profile.first_utm_source and utm_source:
        profile.first_utm_source = utm_source
    if not profile.first_utm_medium and utm_medium:
        profile.first_utm_medium = utm_medium
    if not profile.first_utm_campaign and utm_campaign:
        profile.first_utm_campaign = utm_campaign
    profile.last_utm_source = utm_source
    profile.last_utm_medium = utm_medium
    profile.last_utm_campaign = utm_campaign
    if request.user and request.user.is_authenticated:
        profile.is_authenticated = True
    profile.save(
        update_fields=[
            "visit_count",
            "first_source",
            "last_source",
            "last_path",
            "is_authenticated",
            "first_utm_source",
            "first_utm_medium",
            "first_utm_campaign",
            "last_utm_source",
            "last_utm_medium",
            "last_utm_campaign",
            "last_seen_at",
        ]
    )
    GrowthEvent.objects.create(
        audience_id=audience_id,
        event_type=GrowthEvent.EVENT_LANDING_VIEW,
        source=source,
        path=request.path[:255],
        metadata={
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
        },
    )
    return audience_id


def _clean_billing_text(value, *, max_length: int) -> str:
    """Normalize billing text fields for storage and export."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_length]


def _clean_billing_multiline(value, *, max_length: int) -> str:
    """Keep billing address readable while trimming noisy whitespace."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_length]


def _default_country_name(country_code: str) -> str:
    """Map ISO-ish country code to a readable country label when possible."""
    return COUNTRY_CODE_TO_NAME.get(country_code.upper(), "")


def _billing_country_defaults(
    request,
    *,
    requested_currency: str = "",
) -> tuple[str, str]:
    """Infer a best-effort billing country for prefill/fallback behavior."""
    country_code = str(_request_country_code(request) or "").strip().upper()
    if not country_code:
        currency = _billing_currency_for_request(
            request,
            requested_currency=requested_currency,
        )
        country_code = "IN" if currency == UserSubscription.CURRENCY_INR else ""
    return country_code[:2], _default_country_name(country_code)


def _collect_billing_profile(request, *, user) -> dict:
    """Build a normalized invoice profile from checkout payload + user context."""
    data = request.data if hasattr(request, "data") else {}
    default_country_code, default_country_name = _billing_country_defaults(
        request,
        requested_currency=data.get("currency", ""),
    )
    default_name = ""
    default_email = ""
    if user:
        default_name = user.get_full_name() or user.username or ""
        default_email = user.email or ""

    country_code = _clean_billing_text(
        data.get("billing_country_code") or default_country_code,
        max_length=2,
    ).upper()
    country_name = _clean_billing_text(
        data.get("billing_country_name") or _default_country_name(country_code),
        max_length=80,
    )
    if not country_name and default_country_name:
        country_name = default_country_name

    billing_name = _clean_billing_text(
        data.get("billing_name") or default_name,
        max_length=120,
    )
    billing_email = _clean_billing_text(
        data.get("billing_email") or default_email,
        max_length=254,
    )

    tax_treatment = BillingRecord.TAX_EXPORT_LUT
    if country_code == "IN":
        tax_treatment = BillingRecord.TAX_DOMESTIC
    elif not country_code and not country_name:
        tax_treatment = BillingRecord.TAX_UNKNOWN

    return {
        "billing_name": billing_name,
        "billing_email": billing_email,
        "business_name": _clean_billing_text(
            data.get("business_name"),
            max_length=160,
        ),
        "gstin": _clean_billing_text(data.get("gstin"), max_length=20).upper(),
        "billing_country_code": country_code,
        "billing_country_name": country_name,
        "billing_state": _clean_billing_text(
            data.get("billing_state"),
            max_length=80,
        ),
        "billing_city": _clean_billing_text(
            data.get("billing_city"),
            max_length=80,
        ),
        "billing_postal_code": _clean_billing_text(
            data.get("billing_postal_code"),
            max_length=20,
        ),
        "billing_address": _clean_billing_multiline(
            data.get("billing_address"),
            max_length=600,
        ),
        "tax_treatment": tax_treatment,
        "is_international": bool(country_code and country_code != "IN"),
    }


def _minor_to_major(amount_minor: int, currency: str) -> Decimal:
    """Convert smallest-unit amount into a two-decimal export value."""
    return Decimal(amount_minor or 0) / Decimal("100")


def _upsert_billing_record(
    *,
    user,
    subscription,
    order_id: str,
    plan: str,
    currency: str,
    amount_minor: int,
    billing_profile: dict,
    payment_status: str,
    raw_order_payload: dict | None = None,
    raw_payment_payload: dict | None = None,
    payment_id: str = "",
    payment_method: str = "",
    verified_at=None,
    paid_at=None,
):
    """Maintain one export-friendly billing row per Razorpay order."""
    defaults = {
        "user": user,
        "subscription": subscription,
        "plan": plan,
        "currency": (currency or "").upper()[:3],
        "amount_minor": int(amount_minor or 0),
        "amount_major": _minor_to_major(amount_minor, currency or ""),
        "payment_status": payment_status,
        "razorpay_payment_id": str(payment_id or "")[:64],
        "payment_method": str(payment_method or "")[:40],
        "verified_at": verified_at,
        "paid_at": paid_at,
        "raw_order_payload": raw_order_payload or {},
        "raw_payment_payload": raw_payment_payload or {},
        "metadata": {
            "invoice_basis": "billing_record",
            "source": "razorpay_checkout",
        },
        **(billing_profile or {}),
    }
    record, created = BillingRecord.objects.update_or_create(
        razorpay_order_id=order_id,
        defaults=defaults,
    )
    if not created:
        metadata = record.metadata or {}
        metadata.setdefault("invoice_basis", "billing_record")
        metadata.setdefault("source", "razorpay_checkout")
        if payment_status == BillingRecord.STATUS_CAPTURED:
            metadata["last_capture_sync"] = timezone.now().isoformat()
        record.metadata = metadata
        record.save(update_fields=["metadata", "updated_at"])
    return record


def _log_growth_event(
    *,
    request,
    event_type: str,
    source: str,
    path: str = "",
    metadata: dict | None = None,
) -> None:
    """Persist a single growth funnel event for analytics."""
    audience_id = _resolve_web_audience_id(request)
    GrowthEvent.objects.create(
        audience_id=audience_id,
        event_type=event_type,
        source=source,
        path=(path or request.path)[:255],
        metadata=metadata or {},
    )


def _attach_web_audience_cookie(request, response) -> None:
    """Set audience cookie once for guests so revisit attribution is stable."""
    audience_id = str(
        getattr(request, "web_audience_cookie_to_set", ""),
    ).strip()
    if not audience_id:
        return
    response.set_cookie(
        WEB_AUDIENCE_COOKIE_NAME,
        audience_id,
        max_age=WEB_AUDIENCE_COOKIE_AGE,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )


def _run_guidance_flow(
    *,
    user_id: str,
    message: str,
    mode: str,
    language: str = "en",
    conversation_id: int | None = None,
    plan: str = UserSubscription.PLAN_FREE,
):
    """Run end-to-end ask pipeline and persist conversation messages."""
    message = normalize_chat_user_message(str(message or "").strip())
    language = resolve_guidance_language(language, message)
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
    intent = classify_user_intent(message, mode=mode)
    if intent.intent_type == "verse_explanation" and intent.explicit_references:
        ensure_seed_verses()
        primary_ref = intent.explicit_references[0]
        parsed = tuple(int(part) for part in primary_ref.split(".", 1))
        verse = Verse.objects.filter(
            chapter=parsed[0],
            verse=parsed[1],
        ).first()
        if verse is not None:
            verses = [verse]
            support_verses = [verse, *get_related_verses(message=message, seed_verses=[verse], limit=4)]
            retrieval = empty_retrieval_result(
                intent=intent,
                query_interpretation={
                    **intent.as_dict(),
                    "life_domain": "exact verse explanation",
                    "match_strictness": "exact_reference",
                    "confidence": 0.99,
                },
                retrieval_mode="direct_reference",
            )
            guidance = build_verse_explanation(
                message=message,
                verse=verse,
                support_verses=support_verses,
                language=language,
                mode=mode,
                conversation_messages=conversation_messages,
                max_output_tokens=_plan_max_output_tokens(plan),
                intent=intent,
            )
        else:
            verses = []
            retrieval = empty_retrieval_result(
                intent=intent,
                query_interpretation={
                    **intent.as_dict(),
                    "life_domain": "missing verse reference",
                    "match_strictness": "exact_reference",
                    "confidence": 0.25,
                },
                retrieval_mode="direct_reference_missing",
            )
            guidance = build_guidance(
                message,
                verses,
                conversation_messages=conversation_messages,
                language=language,
                query_interpretation=retrieval.query_interpretation,
                mode=mode,
                max_output_tokens=_plan_max_output_tokens(plan),
                intent_analysis=intent.as_dict(),
            )
    elif intent.intent_type == "chapter_explanation" and intent.chapter_number:
        verses = []
        retrieval = empty_retrieval_result(
            intent=intent,
            query_interpretation={
                **intent.as_dict(),
                "life_domain": "chapter explanation",
                "match_strictness": "direct",
                "confidence": 0.95,
            },
            retrieval_mode="direct_chapter",
        )
        guidance = build_chapter_explanation(
            message=message,
            chapter_number=intent.chapter_number,
            language=language,
        )
    elif intent.intent_type in {"greeting", "casual_chat"}:
        verses = []
        retrieval = empty_retrieval_result(
            intent=intent,
            query_interpretation={
                **intent.as_dict(),
                "life_domain": "conversation",
                "match_strictness": "none",
                "confidence": 0.9,
            },
            retrieval_mode="none",
        )
        guidance = build_guidance(
            message,
            verses,
            conversation_messages=conversation_messages,
            language=language,
            query_interpretation=retrieval.query_interpretation,
            mode=mode,
            max_output_tokens=_plan_max_output_tokens(plan),
            intent_analysis=intent.as_dict(),
        )
    else:
        retrieval = retrieve_verses_with_trace(
            message=message,
            limit=_plan_max_context_verses(plan, mode),
        )
        verses = refine_verses_for_guidance(message, retrieval.verses)
        guidance = build_guidance(
            message,
            verses,
            conversation_messages=conversation_messages,
            language=language,
            query_interpretation=retrieval.query_interpretation,
            mode=mode,
            max_output_tokens=_plan_max_output_tokens(plan),
            intent_analysis=intent.as_dict(),
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
            "एक शांत दृष्टिकोण देती है। आम स्थितियाँ: भय, अनिश्चितता, और अधिक सोचना। यह पेज आपको प्रासंगिक "
            "शिक्षाओं से शुरुआत करने और फिर ऐप में अपना सटीक प्रश्न पूछने में मदद करता है।"
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
        "faq": [
            {
                "question": "How does the Bhagavad Gita help with anxiety and overthinking?",
                "answer": (
                    "The Bhagavad Gita teaches that anxiety arises from attachment to outcomes. "
                    "In Chapter 2 verse 48, Krishna instructs Arjuna to act with steadiness and release the "
                    "results. This principle — performing your duty without obsessing over what will happen — "
                    "directly quiets the restless mind. The Gita also distinguishes between what is within "
                    "your control (your action) and what is not (the outcome), which is the same insight "
                    "modern cognitive therapy builds on."
                ),
            },
            {
                "question": "Which Bhagavad Gita verses address fear and a restless mind?",
                "answer": (
                    "Three verses are most cited. Chapter 2.14 teaches that discomfort and pleasure are "
                    "impermanent — the wise endure both with equanimity. Chapter 2.48 instructs performing "
                    "one's duty with a steady, balanced mind, free from attachment to results. Chapter 6.5 "
                    "reminds the seeker to lift themselves using their own inner strength. Together these form "
                    "a complete framework for moving from fearful overthinking to grounded, present-moment action."
                ),
            },
            {
                "question": "What does Lord Krishna say about a restless mind in the Bhagavad Gita?",
                "answer": (
                    "In Chapter 6, Arjuna himself tells Krishna that the mind is restless, turbulent, and hard "
                    "to control — as difficult to tame as the wind. Krishna acknowledges this and responds that "
                    "while the mind is indeed difficult to control, it can be trained through practice (abhyasa) "
                    "and non-attachment (vairagya). Regular inner practice — whether meditation, self-inquiry, "
                    "or mindful action — gradually stills the restless mind."
                ),
            },
        ],
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
        "faq": [
            {
                "question": "Does the Bhagavad Gita offer guidance for career confusion and uncertainty?",
                "answer": (
                    "Yes. Chapter 2 verse 47 — 'You have the right to your actions, not to the fruits of "
                    "your actions' — is directly relevant to career decisions. The Gita encourages aligning "
                    "your work with your natural strengths and deeper purpose (svadharma) rather than "
                    "choosing based purely on external rewards or comparison. Chapters 3 and 18 both "
                    "emphasize that sincere, duty-driven action leads to a steadier and more fulfilling "
                    "career than anxious, outcome-chasing work."
                ),
            },
            {
                "question": "Which Bhagavad Gita verses help when you feel lost or purposeless at work?",
                "answer": (
                    "Chapter 3 verse 35 says it is better to perform your own dharma imperfectly than "
                    "another's perfectly. Chapter 18 verse 47 echoes the same: your own path, however "
                    "ordinary, carries more meaning than an impressive path that does not belong to you. "
                    "Chapter 2 verse 47 reinforces this with the teaching on action without attachment. "
                    "These three form the core scriptural basis for finding and trusting one's own "
                    "vocational calling."
                ),
            },
            {
                "question": "What does the Bhagavad Gita say about the fear of failure in career?",
                "answer": (
                    "The Gita frames the fear of failure as rooted in identifying with outcomes rather "
                    "than with the act of sincere effort. In Chapter 2 verse 48, Krishna instructs Arjuna "
                    "to establish himself in equanimity and then act. When action is rooted in integrity "
                    "and clarity of purpose, failure becomes information rather than identity. The fear "
                    "naturally diminishes because the seeker no longer defines themselves by the result."
                ),
            },
        ],
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
        "faq": [
            {
                "question": "How does the Bhagavad Gita help with relationship conflict and anger?",
                "answer": (
                    "In Chapter 2 verses 62-63, Krishna traces the exact chain from desire to destruction: "
                    "dwelling on objects of desire creates attachment, attachment creates desire, desire when "
                    "blocked creates anger, and anger clouds judgment. The Gita's remedy is awareness at the "
                    "earliest link in this chain — recognizing the seed before it grows into reactivity. "
                    "Chapter 12 then describes the model of a person who bears no ill-will and responds "
                    "with genuine goodwill, free from ego and possessiveness."
                ),
            },
            {
                "question": "Which Bhagavad Gita verses talk about attachment and emotional pain in relationships?",
                "answer": (
                    "Chapter 2 verse 62 (desire leads to anger), Chapter 2 verse 63 (anger leads to delusion), "
                    "and Chapter 12 verse 13 (the devoted person has no ill-will toward any creature) are most "
                    "frequently cited. The broader framework of non-attachment (vairagya) across Chapters 2, 3, "
                    "and 12 points to a core insight: much relational pain comes from expecting others to "
                    "conform to our desires. Releasing that grip — not withdrawing love, but releasing "
                    "control — is the Gita's path through."
                ),
            },
            {
                "question": "What is Krishna's teaching on unconditional love and compassion?",
                "answer": (
                    "Chapter 12 verse 13 describes the ideal: one who has no ill-will toward any creature, "
                    "who is friendly and compassionate, free from possessiveness and ego, even-minded in pain "
                    "and pleasure. This is not emotional detachment but emotional clarity — loving and caring "
                    "deeply without the grasping quality of attachment. Krishna's teaching on bhakti "
                    "(loving devotion) throughout Chapter 12 shows that the highest love is offered "
                    "freely, without conditions or the expectation of return."
                ),
            },
        ],
    },
    "fear_of_failure": {
        "slug": "bhagavad-gita-for-fear-of-failure",
        "topic_label": "Fear of Failure",
        "topic_label_hi": "असफलता का भय",
        "title": "Bhagavad Gita for Fear of Failure | Guidance for Results, Courage, and Steady Action",
        "title_hi": "असफलता के भय के लिए भगवद गीता | परिणाम, साहस और स्थिर कर्म के लिए मार्गदर्शन",
        "description": (
            "Find Bhagavad Gita guidance for fear of failure, pressure, and self-doubt with relevant verses and practical meaning."
        ),
        "description_hi": (
            "असफलता के भय, दबाव और आत्म-संदेह के लिए प्रासंगिक श्लोकों और व्यावहारिक अर्थ के साथ भगवद गीता मार्गदर्शन पाएँ।"
        ),
        "hero_title": "Bhagavad Gita For Fear Of Failure",
        "hero_title_hi": "असफलता के भय के लिए भगवद गीता",
        "hero_body": (
            "When the mind becomes trapped in 'what if I fail?', the Gita shifts attention from imagined defeat "
            "to sincere action. These verses help you work with more courage and less paralysis."
        ),
        "hero_body_hi": (
            "जब मन 'अगर मैं असफल हो गया तो?' में फँस जाता है, तब गीता कल्पित हार से ध्यान हटाकर ईमानदार कर्म पर लाती है। "
            "ये श्लोक अधिक साहस और कम जड़ता के साथ काम करने में मदद करते हैं।"
        ),
        "problem_points": [
            "avoiding action because the result feels scary",
            "self-worth tied too closely to success",
            "pressure, comparison, and paralysis",
        ],
        "problem_points_hi": [
            "परिणाम के डर से कर्म टालना",
            "सफलता से आत्म-मूल्य को जोड़ देना",
            "दबाव, तुलना और जड़ता",
        ],
        "verse_refs": ["2.47", "2.48", "18.66"],
        "starter_question": "I am afraid of failing and that fear is stopping me from acting. What does the Gita teach?",
        "starter_question_hi": "मुझे असफलता का बहुत भय है और वही मुझे कदम उठाने से रोक रहा है। गीता क्या सिखाती है?",
        "faq": [
            {
                "question": "What does the Bhagavad Gita say about the fear of failure?",
                "answer": (
                    "The Gita repeatedly turns the seeker away from obsession with outcomes and toward right action. "
                    "Chapter 2 verse 47 is central here: your responsibility is action, not guaranteed success. "
                    "That insight weakens fear because identity is no longer fused with the result."
                ),
            },
            {
                "question": "Which Bhagavad Gita verse helps when fear stops you from trying?",
                "answer": (
                    "Chapter 2 verse 48 is especially relevant because Krishna asks Arjuna to act from equanimity, "
                    "not from panic. When effort is rooted in steadiness rather than fear, action becomes possible again."
                ),
            },
        ],
    },
    "purpose": {
        "slug": "bhagavad-gita-for-purpose",
        "topic_label": "Purpose",
        "topic_label_hi": "उद्देश्य",
        "title": "Bhagavad Gita for Purpose | Guidance for Meaning, Dharma, and Direction",
        "title_hi": "उद्देश्य के लिए भगवद गीता | अर्थ, धर्म और दिशा के लिए मार्गदर्शन",
        "description": (
            "Explore Bhagavad Gita guidance for purpose, meaning, and dharma with verses that help you find direction."
        ),
        "description_hi": (
            "अर्थ, उद्देश्य और धर्म के लिए दिशा देने वाले श्लोकों के साथ भगवद गीता मार्गदर्शन देखें।"
        ),
        "hero_title": "Bhagavad Gita For Purpose And Meaning",
        "hero_title_hi": "उद्देश्य और अर्थ के लिए भगवद गीता",
        "hero_body": (
            "When life feels directionless, the Gita does not offer a motivational slogan. It asks deeper questions "
            "about dharma, nature, duty, and what kind of life is truly yours to live."
        ),
        "hero_body_hi": (
            "जब जीवन दिशाहीन लगे, गीता केवल प्रेरक वाक्य नहीं देती। वह धर्म, स्वभाव, कर्तव्य और उस जीवन के बारे में "
            "गहरे प्रश्न पूछती है जो वास्तव में आपका अपना है।"
        ),
        "problem_points": [
            "feeling directionless despite effort",
            "wanting meaning beyond external success",
            "confusion about your true path",
        ],
        "problem_points_hi": [
            "प्रयास के बावजूद दिशाहीनता महसूस होना",
            "बाहरी सफलता से आगे अर्थ की तलाश",
            "अपने सच्चे मार्ग को लेकर उलझन",
        ],
        "verse_refs": ["3.35", "18.47", "18.46"],
        "starter_question": "I feel lost and purposeless. How can the Bhagavad Gita help me find direction?",
        "starter_question_hi": "मैं खोया हुआ और उद्देश्यहीन महसूस करता हूँ। भगवद गीता मुझे दिशा कैसे दे सकती है?",
        "faq": [
            {
                "question": "Does the Bhagavad Gita help people find purpose?",
                "answer": (
                    "Yes. The Gita frames purpose in terms of dharma, nature, and sincere action rather than public image. "
                    "Its guidance is not to copy someone else's path, but to discover and live your own."
                ),
            },
            {
                "question": "Which Bhagavad Gita verses are most useful for purpose and meaning?",
                "answer": (
                    "Chapter 3 verse 35 and Chapter 18 verse 47 are foundational because they emphasize one's own dharma. "
                    "Chapter 18 verse 46 adds that your work can become a path of worship when aligned with truth and sincerity."
                ),
            },
        ],
    },
    "discipline": {
        "slug": "bhagavad-gita-for-discipline",
        "topic_label": "Discipline",
        "topic_label_hi": "अनुशासन",
        "title": "Bhagavad Gita for Discipline | Guidance for Consistency, Self Control, and Practice",
        "title_hi": "अनुशासन के लिए भगवद गीता | निरंतरता, आत्म-नियंत्रण और अभ्यास के लिए मार्गदर्शन",
        "description": (
            "Get Bhagavad Gita guidance for discipline, consistency, and self-control with verses for practice and inner mastery."
        ),
        "description_hi": (
            "अनुशासन, निरंतरता और आत्म-नियंत्रण के लिए अभ्यास और आंतरिक mastery वाले श्लोकों सहित भगवद गीता मार्गदर्शन पाएँ।"
        ),
        "hero_title": "Bhagavad Gita For Discipline And Self-Mastery",
        "hero_title_hi": "अनुशासन और आत्म-नियंत्रण के लिए भगवद गीता",
        "hero_body": (
            "The Gita treats discipline as inner governance, not punishment. These verses help when you want consistency, "
            "better habits, and the strength to stop undermining yourself."
        ),
        "hero_body_hi": (
            "गीता अनुशासन को दंड नहीं, बल्कि भीतर के शासन के रूप में देखती है। ये श्लोक तब मदद करते हैं जब आप निरंतरता, "
            "बेहतर आदतें और स्वयं को कमज़ोर करने की प्रवृत्ति से ऊपर उठना चाहते हैं।"
        ),
        "problem_points": [
            "starting strong but not staying consistent",
            "fighting distraction and lack of self-control",
            "wanting stronger habits and inner order",
        ],
        "problem_points_hi": [
            "शुरू तो करना पर निरंतर न रह पाना",
            "विचलन और आत्म-नियंत्रण की कमी से संघर्ष",
            "मजबूत आदतें और भीतर का अनुशासन चाहना",
        ],
        "verse_refs": ["6.5", "6.26", "3.30"],
        "starter_question": "I keep losing discipline and slipping back into bad habits. What does the Gita say?",
        "starter_question_hi": "मैं बार-बार अनुशासन खो देता हूँ और बुरी आदतों में लौट जाता हूँ। गीता क्या कहती है?",
        "faq": [
            {
                "question": "Which Bhagavad Gita verse helps with self-discipline?",
                "answer": (
                    "Chapter 6 verse 5 is central because it tells the seeker to raise themselves by themselves. "
                    "It frames discipline as inner responsibility rather than external pressure."
                ),
            },
            {
                "question": "What does Krishna teach about controlling the mind?",
                "answer": (
                    "Chapter 6 explains that the mind wanders, but it can be repeatedly brought back through practice and detachment. "
                    "That makes discipline a returning process, not a perfection test."
                ),
            },
        ],
    },
    "stress": {
        "slug": "bhagavad-gita-for-stress",
        "topic_label": "Stress",
        "topic_label_hi": "तनाव",
        "title": "Bhagavad Gita for Stress | Guidance for Calm, Pressure, and Mental Balance",
        "title_hi": "तनाव के लिए भगवद गीता | शांति, दबाव और मानसिक संतुलन के लिए मार्गदर्शन",
        "description": (
            "Find Bhagavad Gita guidance for stress, mental pressure, and overload with calming verses and practical insight."
        ),
        "description_hi": (
            "तनाव, मानसिक दबाव और अधिक बोझ के लिए शांत करने वाले श्लोकों और व्यावहारिक अंतर्दृष्टि के साथ भगवद गीता मार्गदर्शन पाएँ।"
        ),
        "hero_title": "Bhagavad Gita For Stress And Mental Pressure",
        "hero_title_hi": "तनाव और मानसिक दबाव के लिए भगवद गीता",
        "hero_body": (
            "Stress often comes from carrying too much mentally at once. The Gita helps you return to steadiness, "
            "right effort, and a calmer relationship with pressure."
        ),
        "hero_body_hi": (
            "तनाव अक्सर मन में बहुत कुछ एक साथ उठाने से आता है। गीता आपको स्थिरता, उचित प्रयास और दबाव के साथ शांत संबंध में लौटने में मदद करती है।"
        ),
        "problem_points": [
            "constant pressure and mental overload",
            "difficulty calming down after stressful days",
            "feeling drained by expectations and urgency",
        ],
        "problem_points_hi": [
            "लगातार दबाव और मानसिक बोझ",
            "तनावपूर्ण दिनों के बाद शांत न हो पाना",
            "अपेक्षाओं और जल्दबाज़ी से थक जाना",
        ],
        "verse_refs": ["2.48", "6.17", "2.14"],
        "starter_question": "I feel mentally stressed and overloaded all the time. Which Gita teaching can help?",
        "starter_question_hi": "मैं हर समय मानसिक तनाव और बोझ महसूस करता हूँ। गीता की कौन-सी शिक्षा मदद कर सकती है?",
        "faq": [
            {
                "question": "Can the Bhagavad Gita help with stress and pressure?",
                "answer": (
                    "Yes. The Gita repeatedly teaches equanimity, moderation, and right relationship to action. "
                    "These teachings reduce the internal friction that turns work and difficulty into chronic stress."
                ),
            },
            {
                "question": "Which verse is best for stress?",
                "answer": (
                    "Chapter 2 verse 48 is one of the strongest because it asks for balanced action under pressure. "
                    "Chapter 6 verse 17 also emphasizes moderation, which is essential for sustainable calm."
                ),
            },
        ],
    },
    "anger": {
        "slug": "bhagavad-gita-for-anger",
        "topic_label": "Anger",
        "topic_label_hi": "क्रोध",
        "title": "Bhagavad Gita for Anger | Guidance for Reactivity, Hurt, and Emotional Control",
        "title_hi": "क्रोध के लिए भगवद गीता | प्रतिक्रिया, चोट और भावनात्मक नियंत्रण के लिए मार्गदर्शन",
        "description": (
            "Get Bhagavad Gita guidance for anger, reactivity, and emotional control with relevant verses and practical meaning."
        ),
        "description_hi": (
            "क्रोध, तीखी प्रतिक्रिया और भावनात्मक नियंत्रण के लिए प्रासंगिक श्लोकों और व्यावहारिक अर्थ के साथ भगवद गीता मार्गदर्शन पाएँ।"
        ),
        "hero_title": "Bhagavad Gita For Anger And Reactivity",
        "hero_title_hi": "क्रोध और तीखी प्रतिक्रिया के लिए भगवद गीता",
        "hero_body": (
            "The Gita gives one of the clearest analyses of anger anywhere: how desire becomes attachment, "
            "attachment becomes anger, and anger clouds wisdom. These verses help you interrupt that chain."
        ),
        "hero_body_hi": (
            "गीता क्रोध का सबसे स्पष्ट विश्लेषण देती है: कैसे इच्छा आसक्ति बनती है, आसक्ति क्रोध में बदलती है और "
            "क्रोध बुद्धि को ढक देता है। ये श्लोक उस श्रृंखला को तोड़ने में मदद करते हैं।"
        ),
        "problem_points": [
            "snapping quickly in conflict",
            "carrying hurt that turns into anger",
            "wanting more emotional control",
        ],
        "problem_points_hi": [
            "विवाद में जल्दी भड़क जाना",
            "चोट को भीतर लेकर क्रोध में बदल देना",
            "अधिक भावनात्मक नियंत्रण चाहना",
        ],
        "verse_refs": ["2.62", "2.63", "12.13"],
        "starter_question": "I get angry quickly and regret my reactions. What does the Gita teach?",
        "starter_question_hi": "मुझे जल्दी गुस्सा आ जाता है और बाद में अपनी प्रतिक्रियाओं पर पछतावा होता है। गीता क्या सिखाती है?",
        "faq": [
            {
                "question": "What does the Bhagavad Gita say about anger?",
                "answer": (
                    "Chapter 2 verses 62-63 lay out the chain clearly: attachment leads to desire, blocked desire leads to anger, "
                    "and anger leads to delusion and loss of wisdom. The teaching is diagnostic and practical at the same time."
                ),
            },
            {
                "question": "How can the Gita help me respond with less anger?",
                "answer": (
                    "The Gita asks you to catch the process earlier, before anger becomes speech or action. "
                    "By reducing attachment and practicing inner steadiness, reactions become more conscious."
                ),
            },
        ],
    },
}


def _seo_value(page: dict, key: str, language: str):
    """Return Hindi variant when available, else fallback to default key."""
    if language == "hi":
        return page.get(f"{key}_hi", page.get(key))
    return page.get(key)


def _fetch_curated_verses(reference_list: list[str]) -> list[SimpleNamespace]:
    """Fetch a small stable verse list for SEO landing pages."""
    ensure_seed_verses()
    verses = []
    for ref in reference_list:
        chapter_num: int | None = None
        verse_num: int | None = None
        try:
            chapter_text, verse_text = ref.split(".", 1)
            chapter_num = int(chapter_text)
            verse_num = int(verse_text)
            verse = Verse.objects.filter(
                chapter=chapter_num,
                verse=verse_num,
            ).first()
        except (TypeError, ValueError):
            verse = None

        if verse is None:
            placeholder = (
                "Relevant Bhagavad Gita guidance for this life challenge."
            )
            verses.append(
                SimpleNamespace(
                    reference=ref,
                    chapter=chapter_num or 0,
                    verse=verse_num or 0,
                    translation=placeholder,
                    text=placeholder,
                    themes=[],
                )
            )
            continue

        verses.append(
            SimpleNamespace(
                reference=ref,
                chapter=verse.chapter,
                verse=verse.verse,
                translation=verse.translation,
                text=verse.translation,
                themes=list(verse.themes or []),
            )
        )
    return verses


SEO_INTENT_KEYWORDS_EN = (
    "Bhagavad Gita AI, Gita GPT, Gita AI, Ask Gita, Ask Bhagavad Gita, "
    "Bhagavad Gita chatbot, Krishna guidance, Bhagavad Gita guidance for life questions"
)
SEO_INTENT_KEYWORDS_HI = (
    "भगवद गीता एआई, गीता जीपीटी, गीता एआई, आस्क गीता, भगवद गीता मार्गदर्शन, "
    "कृष्ण मार्गदर्शन, जीवन के प्रश्नों के लिए भगवद गीता"
)

SEO_INDEX_FAQ_EN = [
    {
        "question": "Is this a Bhagavad Gita AI or Gita GPT style app?",
        "answer": (
            "Yes. Ask Bhagavad Gita is a Bhagavad Gita AI experience that many users would also describe "
            "as a Gita GPT or Ask Gita tool. You can ask a life question in plain English or Hindi, see "
            "relevant Bhagavad Gita verses, and get a simpler modern explanation connected to your situation."
        ),
    },
    {
        "question": "What can I ask in this Ask Gita app?",
        "answer": (
            "You can ask about anxiety, overthinking, career confusion, relationship pain, discipline, "
            "fear, purpose, or other real-life problems. The app tries to retrieve relevant Bhagavad Gita "
            "verses, explain the teaching in simple language, and suggest a practical next step."
        ),
    },
    {
        "question": "How is this different from just reading the Bhagavad Gita directly?",
        "answer": (
            "Reading the scripture directly is invaluable, but many people need help finding where to start. "
            "This tool works like a guided Bhagavad Gita search and reflection layer: it narrows to relevant "
            "verses, summarizes their meaning, and helps you continue into the full app for a personal question."
        ),
    },
]
SEO_INDEX_FAQ_HI = [
    {
        "question": "क्या यह भगवद गीता एआई या गीता जीपीटी जैसा ऐप है?",
        "answer": (
            "हाँ। Ask Bhagavad Gita एक भगवद गीता एआई अनुभव है जिसे कई लोग गीता जीपीटी या Ask Gita "
            "टूल जैसा मानेंगे। आप अंग्रेज़ी या हिंदी में जीवन का प्रश्न पूछ सकते हैं, प्रासंगिक श्लोक देख "
            "सकते हैं और अपनी स्थिति से जुड़ा सरल आधुनिक अर्थ पा सकते हैं।"
        ),
    },
    {
        "question": "इस Ask Gita ऐप में मैं क्या पूछ सकता हूँ?",
        "answer": (
            "आप चिंता, ओवरथिंकिंग, करियर उलझन, रिश्तों की परेशानी, अनुशासन, भय, उद्देश्य या अन्य "
            "जीवन समस्याओं के बारे में पूछ सकते हैं। ऐप प्रासंगिक भगवद गीता श्लोक खोजने, सरल भाषा में "
            "अर्थ समझाने और व्यावहारिक अगले कदम देने की कोशिश करता है।"
        ),
    },
    {
        "question": "यह केवल भगवद गीता पढ़ने से कैसे अलग है?",
        "answer": (
            "गीता को सीधे पढ़ना अमूल्य है, लेकिन कई लोगों को यह समझने में मदद चाहिए कि शुरुआत कहाँ से करें। "
            "यह टूल एक निर्देशित भगवद गीता खोज और चिंतन परत की तरह काम करता है: यह प्रासंगिक श्लोकों तक "
            "ले जाता है, उनका सार बताता है, और फिर आपको पूरे ऐप में व्यक्तिगत प्रश्न पूछने देता है।"
        ),
    },
]

POPULAR_VERSE_SPOTLIGHTS = [
    {
        "reference": "2.47",
        "label": "Karmanye vadhikaraste",
        "label_hi": "कर्मण्येवाधिकारस्ते",
        "search_intent": "duty, fear of failure, work without attachment",
        "search_intent_hi": "कर्तव्य, असफलता का भय, फल की आसक्ति के बिना कर्म",
        "summary": (
            "This is one of the most searched Bhagavad Gita verses because it helps people deal with career pressure, "
            "performance anxiety, and over-attachment to outcomes."
        ),
        "summary_hi": (
            "यह सबसे अधिक खोजे जाने वाले श्लोकों में से एक है क्योंकि यह करियर दबाव, प्रदर्शन की चिंता और "
            "परिणामों की आसक्ति से जूझ रहे लोगों की मदद करता है।"
        ),
        "prefill": "Explain Bhagavad Gita 2.47 in simple language and apply it to my current situation.",
        "prefill_hi": "भगवद गीता 2.47 को सरल भाषा में समझाइए और मेरी वर्तमान स्थिति पर लागू कीजिए।",
    },
    {
        "reference": "2.48",
        "label": "Yogastha kuru karmani",
        "label_hi": "योगस्थः कुरु कर्माणि",
        "search_intent": "stress, equanimity, performance pressure",
        "search_intent_hi": "तनाव, समत्व, प्रदर्शन का दबाव",
        "summary": (
            "People search this verse when they want calm action under pressure. It connects directly to stress, "
            "anxiety, and staying steady in difficult situations."
        ),
        "summary_hi": (
            "लोग इस श्लोक को तब खोजते हैं जब वे दबाव में शांत कर्म करना चाहते हैं। यह सीधे तनाव, चिंता और "
            "कठिन परिस्थितियों में स्थिर रहने से जुड़ता है।"
        ),
        "prefill": "Explain Bhagavad Gita 2.48 for stress and staying calm under pressure.",
        "prefill_hi": "तनाव और दबाव में शांत रहने के लिए भगवद गीता 2.48 समझाइए।",
    },
    {
        "reference": "4.7",
        "label": "Yada yada hi dharmasya",
        "label_hi": "यदा यदा हि धर्मस्य",
        "search_intent": "famous verse, Krishna, dharma, hope in hard times",
        "search_intent_hi": "प्रसिद्ध श्लोक, कृष्ण, धर्म, कठिन समय में आशा",
        "summary": (
            "This is one of the most famous verses from the Gita and often searched by people looking for Krishna's "
            "promise of restoration when life feels chaotic or morally confusing."
        ),
        "summary_hi": (
            "यह गीता के सबसे प्रसिद्ध श्लोकों में से एक है और अक्सर उन लोगों द्वारा खोजा जाता है जो जीवन के "
            "अव्यवस्थित या नैतिक रूप से उलझे समय में कृष्ण के आश्वासन को समझना चाहते हैं।"
        ),
        "prefill": "Explain Bhagavad Gita 4.7 and what it means in modern life.",
        "prefill_hi": "भगवद गीता 4.7 का अर्थ और आधुनिक जीवन में उसका मतलब समझाइए।",
    },
    {
        "reference": "6.5",
        "label": "Uddhared atmanatmanam",
        "label_hi": "उद्धरेदात्मनाऽत्मानम्",
        "search_intent": "self discipline, self growth, inner strength",
        "search_intent_hi": "आत्म-अनुशासन, आत्म-विकास, आंतरिक शक्ति",
        "summary": (
            "This verse draws people searching for self-improvement, discipline, and confidence because it frames "
            "the self as both the obstacle and the path to upliftment."
        ),
        "summary_hi": (
            "यह श्लोक आत्म-सुधार, अनुशासन और आत्मविश्वास खोजने वाले लोगों को आकर्षित करता है क्योंकि यह बताता है "
            "कि मनुष्य स्वयं ही बाधा भी हो सकता है और उत्थान का साधन भी।"
        ),
        "prefill": "Explain Bhagavad Gita 6.5 for self-discipline and personal growth.",
        "prefill_hi": "आत्म-अनुशासन और व्यक्तिगत विकास के लिए भगवद गीता 6.5 समझाइए।",
    },
    {
        "reference": "18.66",
        "label": "Sarva dharman parityajya",
        "label_hi": "सर्वधर्मान्परित्यज्य",
        "search_intent": "surrender, faith, fear, ultimate teaching",
        "search_intent_hi": "समर्पण, श्रद्धा, भय, अंतिम शिक्षा",
        "summary": (
            "One of the most discussed closing verses in the Gita. People search it during fear, guilt, or major "
            "life decisions when they want Krishna's deepest assurance."
        ),
        "summary_hi": (
            "यह गीता के अंतिम और सबसे चर्चित श्लोकों में से एक है। लोग इसे भय, अपराधबोध या बड़े जीवन-निर्णयों के "
            "समय खोजते हैं जब वे कृष्ण का सबसे गहरा आश्वासन समझना चाहते हैं।"
        ),
        "prefill": "Explain Bhagavad Gita 18.66 and how surrender applies to my life right now.",
        "prefill_hi": "भगवद गीता 18.66 समझाइए और बताइए कि समर्पण अभी मेरे जीवन में कैसे लागू होता है।",
    },
]

QUESTION_ARCHIVE_GROUPS_EN = [
    {
        "title": "Anxiety and Overthinking",
        "questions": [
            "What does the Bhagavad Gita say about anxiety?",
            "Which Gita verse helps with overthinking?",
            "How can I stop worrying about the future according to Krishna?",
        ],
    },
    {
        "title": "Career and Purpose",
        "questions": [
            "Which Bhagavad Gita verse helps with career confusion?",
            "What does the Gita say about purpose and dharma?",
            "How do I work without fear of failure according to the Gita?",
        ],
    },
    {
        "title": "Relationships and Anger",
        "questions": [
            "What does the Bhagavad Gita say about anger in relationships?",
            "Which Gita verses help with attachment and heartbreak?",
            "How can I respond calmly when I feel hurt?",
        ],
    },
    {
        "title": "Discipline and Self Growth",
        "questions": [
            "Which Bhagavad Gita verse helps with self-discipline?",
            "What does Krishna say about controlling the mind?",
            "How can I stop procrastinating according to the Gita?",
        ],
    },
]

QUESTION_ARCHIVE_GROUPS_HI = [
    {
        "title": "चिंता और ओवरथिंकिंग",
        "questions": [
            "भगवद गीता चिंता के बारे में क्या कहती है?",
            "ओवरथिंकिंग के लिए कौन-सा गीता श्लोक मदद करता है?",
            "कृष्ण के अनुसार मैं भविष्य की चिंता कैसे छोड़ूँ?",
        ],
    },
    {
        "title": "करियर और उद्देश्य",
        "questions": [
            "करियर उलझन के लिए कौन-सा भगवद गीता श्लोक मदद करता है?",
            "गीता उद्देश्य और धर्म के बारे में क्या कहती है?",
            "गीता के अनुसार मैं असफलता के भय के बिना कैसे काम करूँ?",
        ],
    },
    {
        "title": "रिश्ते और क्रोध",
        "questions": [
            "रिश्तों में क्रोध के बारे में भगवद गीता क्या कहती है?",
            "आसक्ति और दिल टूटने के लिए कौन-से गीता श्लोक मदद करते हैं?",
            "जब मुझे चोट लगे तो मैं शांत प्रतिक्रिया कैसे दूँ?",
        ],
    },
    {
        "title": "अनुशासन और आत्म-विकास",
        "questions": [
            "आत्म-अनुशासन के लिए कौन-सा भगवद गीता श्लोक मदद करता है?",
            "मन को नियंत्रित करने के बारे में कृष्ण क्या कहते हैं?",
            "गीता के अनुसार मैं टालमटोल कैसे छोड़ूँ?",
        ],
    },
]


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
    urls = ["/"] + [
        f"/{page['slug']}/"
        for page in SEO_LANDING_PAGES.values()
    ] + [
        "/frequently-asked-bhagavad-gita-questions/",
        "/daily-bhagavad-gita-verse/",
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
        popular_verse_cards = [
            {
                "reference": item["reference"],
                "label": _seo_value(item, "label", language),
                "search_intent": _seo_value(item, "search_intent", language),
                "summary": _seo_value(item, "summary", language),
                "chat_url_with_prefill": (
                    f"/api/chat-ui/?mode=simple&language={language}"
                    f"&prefill={quote_plus(_seo_value(item, 'prefill', language))}"
                ),
            }
            for item in POPULAR_VERSE_SPOTLIGHTS
        ]
        faq_items = SEO_INDEX_FAQ_HI if language == "hi" else SEO_INDEX_FAQ_EN
        page_title = (
            "भगवद गीता एआई और गीता जीपीटी मार्गदर्शिकाएँ | चिंता, करियर, रिश्ते और जीवन के प्रश्न"
            if language == "hi"
            else (
                "Bhagavad Gita AI, Gita GPT, and Ask Gita Guides For Anxiety, Career, "
                "Relationships, and Real Life Questions"
            )
        )
        meta_description = (
            "भगवद गीता एआई, गीता जीपीटी या Ask Gita जैसी खोज करने वालों के लिए चिंता, करियर उलझन, "
            "रिश्तों और जीवन चुनौतियों पर केंद्रित भगवद गीता मार्गदर्शिकाएँ देखें।"
            if language == "hi"
            else (
                "Explore Bhagavad Gita AI, Gita GPT, and Ask Gita style landing pages for anxiety, "
                "career confusion, relationships, and other real-life challenges."
            )
        )
        meta_keywords = (
            SEO_INTENT_KEYWORDS_HI
            if language == "hi"
            else SEO_INTENT_KEYWORDS_EN
        )
        page_heading = (
            "जीवन की वास्तविक समस्याओं के लिए भगवद गीता मार्गदर्शन"
            if language == "hi"
            else "Bhagavad Gita Guides For Real Life Problems"
        )
        page_intro = (
            "नीचे एक केंद्रित गाइड चुनें, प्रासंगिक श्लोक देखें, और फिर व्यक्तिगत उत्तर के लिए ऐप में जाएँ।"
            if language == "hi"
            else (
                "Choose a focused guide below, explore relevant verses, and then continue into the full app "
                "for a personalized answer."
            )
        )
        search_intent_copy = (
            "यदि आप भगवद गीता एआई, गीता जीपीटी, Ask Gita, या कृष्ण से प्रश्न पूछने वाला टूल खोज रहे हैं, "
            "तो यह पेज उसी इरादे के लिए बनाया गया है—पहले विषय चुनें, फिर पूरे ऐप में अपना सटीक प्रश्न पूछें।"
            if language == "hi"
            else (
                "If you searched for Bhagavad Gita AI, Gita GPT, Ask Gita, or a Krishna guidance app, "
                "this page is built for that same intent: start with a topic, then continue into the full "
                "app to ask your exact question."
            )
        )
        structured_data = json.dumps(
            [
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "name": "Bhagavad Gita Guide",
                    "url": site_url,
                    "alternateName": [
                        "Ask Bhagavad Gita",
                        "Ask Gita",
                        "Bhagavad Gita AI",
                        "Gita GPT",
                    ],
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
                {
                    "@context": "https://schema.org",
                    "@type": "ItemList",
                    "name": (
                        "Most Searched Bhagavad Gita Verses"
                        if language != "hi"
                        else "सबसे अधिक खोजे जाने वाले भगवद गीता श्लोक"
                    ),
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": index + 1,
                            "name": f"{card['reference']} {card['label']}",
                            "description": card["summary"],
                        }
                        for index, card in enumerate(popular_verse_cards)
                    ],
                },
                {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": faq["question"],
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": faq["answer"],
                            },
                        }
                        for faq in faq_items
                    ],
                },
            ],
            ensure_ascii=False,
        )
        context = {
            "page_title": page_title,
            "meta_description": meta_description,
            "meta_keywords": meta_keywords,
            "page_heading": page_heading,
            "page_intro": page_intro,
            "topics": topics,
            "popular_verse_cards": popular_verse_cards,
            "faq_items": faq_items,
            "search_intent_copy": search_intent_copy,
            "language": language,
            "canonical_url": canonical_url,
            "alternate_en_url": alternate_en_url,
            "alternate_hi_url": alternate_hi_url,
            "og_type": "website",
            "structured_data": structured_data,
            "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        }
        _track_web_visit(request, source=WebAudienceProfile.SOURCE_SEO_INDEX)
        response = render(request, self.template_name, context)
        _attach_web_audience_cookie(request, response)
        return response


class SeoQuestionArchiveView(View):
    """Public archive page of common Bhagavad Gita questions for search intent."""

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
        question_groups_src = (
            QUESTION_ARCHIVE_GROUPS_HI
            if language == "hi"
            else QUESTION_ARCHIVE_GROUPS_EN
        )
        question_groups = []
        for group in question_groups_src:
            question_groups.append(
                {
                    "title": group["title"],
                    "questions": [
                        {
                            "text": q,
                            "chat_url_with_prefill": (
                                f"/api/chat-ui/?mode=simple&language={language}"
                                f"&prefill={quote_plus(q)}"
                            ),
                        }
                        for q in group["questions"]
                    ],
                }
            )
        page_title = (
            "भगवद गीता सामान्य प्रश्न | Ask Gita शैली प्रश्न संग्रह"
            if language == "hi"
            else "Frequently Asked Bhagavad Gita Questions | Ask Gita Style Question Archive"
        )
        meta_description = (
            "चिंता, करियर, रिश्ते, अनुशासन और जीवन के प्रश्नों पर सामान्य भगवद गीता प्रश्नों का संग्रह देखें।"
            if language == "hi"
            else (
                "Browse a public archive of common Bhagavad Gita questions about anxiety, career, relationships, "
                "discipline, and real-life struggles."
            )
        )
        meta_keywords = (
            "भगवद गीता प्रश्न, Ask Gita प्रश्न, गीता एआई प्रश्न, भगवद गीता सामान्य प्रश्न"
            if language == "hi"
            else (
                "Bhagavad Gita questions, Ask Gita questions, Gita AI questions, common Bhagavad Gita questions"
            )
        )
        page_heading = (
            "अक्सर पूछे जाने वाले भगवद गीता प्रश्न"
            if language == "hi"
            else "Frequently Asked Bhagavad Gita Questions"
        )
        page_intro = (
            "ये वे सामान्य प्रश्न हैं जिनके लिए लोग गीता में मार्गदर्शन खोजते हैं। किसी भी प्रश्न पर क्लिक करें और पूरे ऐप में उस प्रश्न का श्लोक-आधारित उत्तर पाएँ।"
            if language == "hi"
            else (
                "These are common question patterns people search when looking for Bhagavad Gita guidance. "
                "Click any question to open the full app with that question prefilled."
            )
        )
        faq_items = [
            {
                "question": (
                    "क्या यह पेज वास्तविक गीता प्रश्नों के लिए बनाया गया है?"
                    if language == "hi"
                    else "Is this page designed around real Bhagavad Gita search questions?"
                ),
                "answer": (
                    "हाँ। इसमें वही प्रकार के प्रश्न शामिल हैं जिन्हें लोग चिंता, करियर, रिश्तों और अनुशासन जैसे विषयों पर खोजते हैं।"
                    if language == "hi"
                    else "Yes. It groups together the kinds of questions people commonly search around anxiety, career, relationships, and discipline."
                ),
            },
            {
                "question": (
                    "क्या मैं इन प्रश्नों को अपनी स्थिति के अनुसार बदल सकता हूँ?"
                    if language == "hi"
                    else "Can I customize these questions for my own situation?"
                ),
                "answer": (
                    "बिल्कुल। किसी भी प्रश्न से शुरुआत करें, फिर पूरे ऐप में अपने शब्दों में उसे और विशिष्ट बना दें।"
                    if language == "hi"
                    else "Absolutely. Start with any question here, then make it more specific inside the full app in your own words."
                ),
            },
        ]
        structured_data = json.dumps(
            [
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": page_heading,
                    "description": meta_description,
                    "url": canonical_url,
                    "inLanguage": "hi" if language == "hi" else "en",
                },
                {
                    "@context": "https://schema.org",
                    "@type": "ItemList",
                    "name": page_heading,
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": index + 1,
                            "name": q["text"],
                        }
                        for index, group in enumerate(question_groups)
                        for q in group["questions"]
                    ],
                },
                {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": faq["question"],
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": faq["answer"],
                            },
                        }
                        for faq in faq_items
                    ],
                },
            ],
            ensure_ascii=False,
        )
        context = {
            "page_title": page_title,
            "meta_description": meta_description,
            "meta_keywords": meta_keywords,
            "page_heading": page_heading,
            "page_intro": page_intro,
            "language": language,
            "canonical_url": canonical_url,
            "alternate_en_url": alternate_en_url,
            "alternate_hi_url": alternate_hi_url,
            "og_type": "website",
            "structured_data": structured_data,
            "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
            "question_groups": question_groups,
            "faq_items": faq_items,
            "topics": [],
            "popular_verse_cards": [],
            "archive_mode": True,
            "archive_backlinks": [
                {
                    "label": _seo_value(page, "topic_label", language),
                    "slug": page["slug"],
                }
                for page in SEO_LANDING_PAGES.values()
            ],
            "search_intent_copy": (
                "यदि आप Ask Gita, Gita AI, या भगवद गीता प्रश्नों का संग्रह खोज रहे हैं, तो यह पेज उसी इरादे के लिए बनाया गया है।"
                if language == "hi"
                else "If you searched for Ask Gita questions, Gita AI questions, or a Bhagavad Gita question archive, this page is built for that exact intent."
            ),
        }
        _track_web_visit(request, source=WebAudienceProfile.SOURCE_SEO_INDEX)
        response = render(request, self.template_name, context)
        _attach_web_audience_cookie(request, response)
        return response


class SeoDailyVerseHubView(View):
    """Public SEO page for today's verse plus recent daily verse history."""

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
        today = timezone.localdate()
        recent_daily_verses = [
            DailyVerseView._build_daily_payload(
                day=today - timedelta(days=offset),
                language=language,
            )
            for offset in range(7)
        ]
        featured = recent_daily_verses[0]
        page_title = (
            "आज का भगवद गीता श्लोक | दैनिक गीता मार्गदर्शन"
            if language == "hi"
            else "Today's Bhagavad Gita Verse | Daily Gita Guidance and Reflection"
        )
        meta_description = (
            "आज का भगवद गीता श्लोक, उसका अर्थ, चिंतन और पिछले दिनों के श्लोक एक ही पेज पर देखें।"
            if language == "hi"
            else (
                "Read today's Bhagavad Gita verse, its meaning, reflection, and recent daily verses in one place."
            )
        )
        meta_keywords = (
            "आज का गीता श्लोक, दैनिक भगवद गीता श्लोक, गीता का आज का विचार"
            if language == "hi"
            else "today's Bhagavad Gita verse, daily Gita verse, Bhagavad Gita daily quote"
        )
        page_heading = (
            "आज का भगवद गीता श्लोक"
            if language == "hi"
            else "Today's Bhagavad Gita Verse"
        )
        page_intro = (
            "हर दिन एक श्लोक, एक अर्थ, और एक चिंतन। यदि कोई श्लोक आपसे जुड़ता है, तो उसी श्लोक को पूरे ऐप में अपनी स्थिति से जोड़कर समझ सकते हैं।"
            if language == "hi"
            else (
                "One verse, one meaning, and one reflection for today. If a verse resonates, continue into the full app "
                "to connect it with your own situation."
            )
        )
        structured_data = json.dumps(
            [
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": page_heading,
                    "description": meta_description,
                    "url": canonical_url,
                    "inLanguage": "hi" if language == "hi" else "en",
                },
                {
                    "@context": "https://schema.org",
                    "@type": "ItemList",
                    "name": (
                        "Recent daily Bhagavad Gita verses"
                        if language != "hi"
                        else "हाल के दैनिक भगवद गीता श्लोक"
                    ),
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": index + 1,
                            "name": f"{item['reference']}",
                            "description": item["quote"],
                        }
                        for index, item in enumerate(recent_daily_verses)
                    ],
                },
            ],
            ensure_ascii=False,
        )
        context = {
            "page_title": page_title,
            "meta_description": meta_description,
            "meta_keywords": meta_keywords,
            "page_heading": page_heading,
            "page_intro": page_intro,
            "language": language,
            "canonical_url": canonical_url,
            "alternate_en_url": alternate_en_url,
            "alternate_hi_url": alternate_hi_url,
            "og_type": "website",
            "structured_data": structured_data,
            "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
            "archive_mode": True,
            "daily_verse_mode": True,
            "featured_daily_verse": featured,
            "recent_daily_verses": recent_daily_verses[1:],
            "faq_items": [
                {
                    "question": (
                        "क्या आज का गीता श्लोक हर दिन बदलता है?"
                        if language == "hi"
                        else "Does the daily Bhagavad Gita verse change every day?"
                    ),
                    "answer": (
                        "हाँ, यह पेज दिन के आधार पर एक स्थिर श्लोक चुनता है ताकि सभी उपयोगकर्ताओं को उसी दिन वही दैनिक श्लोक दिखे।"
                        if language == "hi"
                        else "Yes. The page selects a stable verse based on the current day so everyone sees the same daily verse for that date."
                    ),
                },
                {
                    "question": (
                        "क्या मैं इसी श्लोक को अपनी समस्या पर लागू करके पूछ सकता हूँ?"
                        if language == "hi"
                        else "Can I ask how this verse applies to my own life?"
                    ),
                    "answer": (
                        "हाँ। हर दैनिक श्लोक कार्ड से आप पूरे ऐप में जा सकते हैं और उसी श्लोक को अपनी स्थिति से जोड़कर समझ सकते हैं।"
                        if language == "hi"
                        else "Yes. Each daily verse can open the full app with a prefilled prompt so you can apply that verse to your own situation."
                    ),
                },
            ],
            "topics": [],
            "popular_verse_cards": [],
            "question_groups": [],
            "archive_backlinks": [
                {
                    "label": _seo_value(page, "topic_label", language),
                    "slug": page["slug"],
                }
                for page in SEO_LANDING_PAGES.values()
            ],
            "search_intent_copy": (
                "यदि आप आज का गीता श्लोक, दैनिक भगवद गीता विचार, या daily Gita verse खोज रहे हैं, तो यह पेज उसी इरादे के लिए बनाया गया है।"
                if language == "hi"
                else "If you searched for today's Gita verse, daily Bhagavad Gita verse, or a daily spiritual reflection, this page is built for that exact intent."
            ),
        }
        _track_web_visit(request, source=WebAudienceProfile.SOURCE_SEO_INDEX)
        response = render(request, self.template_name, context)
        _attach_web_audience_cookie(request, response)
        return response


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
        meta_keywords = (
            f"{_seo_value(page, 'topic_label', language)}, "
            + (
                SEO_INTENT_KEYWORDS_HI
                if language == "hi"
                else SEO_INTENT_KEYWORDS_EN
            )
        )
        faq_items = page.get("faq", [])
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
            ]
            + (
                [
                    {
                        "@context": "https://schema.org",
                        "@type": "FAQPage",
                        "mainEntity": [
                            {
                                "@type": "Question",
                                "name": faq["question"],
                                "acceptedAnswer": {
                                    "@type": "Answer",
                                    "text": faq["answer"],
                                },
                            }
                            for faq in faq_items
                        ],
                    }
                ]
                if faq_items
                else []
            ),
            ensure_ascii=False,
        )
        context = {
            "page_title": page_title,
            "meta_description": meta_description,
            "meta_keywords": meta_keywords,
            "page_heading": _seo_value(page, "hero_title", language),
            "page_intro": _seo_value(page, "hero_body", language),
            "topic_label": _seo_value(page, "topic_label", language),
            "problem_points": _seo_value(page, "problem_points", language),
            "featured_verses": _fetch_curated_verses(page["verse_refs"]),
            "starter_question": starter_question,
            "chat_url": chat_url,
            "chat_url_with_prefill": f"{chat_url}&prefill={quote_plus(starter_question)}",
            "faq_items": faq_items,
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
        _track_web_visit(request, source=WebAudienceProfile.SOURCE_SEO_TOPIC)
        response = render(request, self.template_name, context)
        _attach_web_audience_cookie(request, response)
        return response


def _get_user_plan_and_usage(user):
    """Return user subscription record and today's usage counter."""
    subscription, _ = UserSubscription.objects.get_or_create(user=user)
    subscription = _normalize_subscription_state(subscription)
    usage, _ = DailyAskUsage.objects.get_or_create(
        user=user,
        date=timezone.localdate(),
        defaults={"ask_count": 0},
    )
    return subscription, usage


def _normalize_subscription_state(subscription: UserSubscription) -> UserSubscription:
    """Downgrade expired paid subscriptions to Free and persist the change.

    This keeps runtime behavior correct even without a background scheduler.
    """
    if subscription.plan == UserSubscription.PLAN_FREE:
        return subscription
    if (
        subscription.subscription_end_date is not None
        and subscription.subscription_end_date <= timezone.now()
    ):
        subscription.plan = UserSubscription.PLAN_FREE
        subscription.is_active = False
        subscription.subscription_end_date = None
        subscription.save(
            update_fields=[
                "plan",
                "is_active",
                "subscription_end_date",
                "updated_at",
            ],
        )
    return subscription


def _request_quota_settings() -> RequestQuotaSettings | None:
    """Return singleton admin quota settings with a short-lived safe cache."""
    now = time.monotonic()
    cached_value = _quota_settings_cache.get("value", _QUOTA_SETTINGS_UNSET)
    loaded_at = float(_quota_settings_cache.get("loaded_at", 0.0) or 0.0)
    if (
        cached_value not in {_QUOTA_SETTINGS_UNSET, None}
        and (now - loaded_at) < _QUOTA_SETTINGS_CACHE_TTL_SECONDS
    ):
        return cached_value

    try:
        quota_settings = RequestQuotaSettings.objects.first()
    except Exception:
        logger.exception("request_quota_settings_lookup_failed")
        if cached_value is not _QUOTA_SETTINGS_UNSET:
            return cached_value
        return None

    _quota_settings_cache["value"] = quota_settings
    _quota_settings_cache["loaded_at"] = now
    return quota_settings


def _current_month_start() -> timezone.datetime:
    """Return timezone-aware start timestamp of the current month."""
    now = timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _monthly_ask_count(user) -> int:
    """Count total asks in current month from daily usage rows."""
    month_start = timezone.localdate().replace(day=1)
    return int(
        DailyAskUsage.objects.filter(
            user=user,
            date__gte=month_start,
        ).aggregate(total=Sum("ask_count"))["total"]
        or 0
    )


def _monthly_deep_ask_count(user) -> int:
    """Count served deep-mode asks in current month from ask events."""
    return AskEvent.objects.filter(
        user_id=user.get_username(),
        outcome=AskEvent.OUTCOME_SERVED,
        mode=AskEvent.MODE_DEEP,
        created_at__gte=_current_month_start(),
    ).count()


def _plan_daily_limit(plan: str) -> int | None:
    """Resolve daily ask limit from admin settings, then env defaults."""
    if settings.DISABLE_ALL_QUOTAS:
        return None
    quota_settings = _request_quota_settings()
    if plan == UserSubscription.PLAN_PRO:
        if quota_settings:
            if not quota_settings.pro_limit_enabled:
                return None
            return quota_settings.pro_daily_ask_limit
        return settings.ASK_LIMIT_PRO_DAILY or None

    if plan == UserSubscription.PLAN_PLUS:
        if quota_settings:
            if not quota_settings.plus_limit_enabled:
                return None
            return quota_settings.plus_daily_ask_limit
        plus_daily_limit = getattr(settings, "ASK_LIMIT_PLUS_DAILY", 0)
        return plus_daily_limit or None

    if quota_settings:
        if not quota_settings.free_limit_enabled:
            return None
        return quota_settings.free_daily_ask_limit
    return settings.ASK_LIMIT_FREE_DAILY


def _plan_max_output_tokens(plan: str) -> int | None:
    """Return LLM max_output_tokens limit for the given plan."""
    if plan == UserSubscription.PLAN_PRO:
        return settings.MAX_OUTPUT_TOKENS_PRO
    if plan == UserSubscription.PLAN_PLUS:
        return settings.MAX_OUTPUT_TOKENS_PLUS
    return settings.MAX_OUTPUT_TOKENS_FREE


def _plan_max_context_verses(plan: str, mode: str) -> int:
    """Return retrieval verse limit for the given plan and mode."""
    if plan == UserSubscription.PLAN_PRO:
        return settings.MAX_CONTEXT_VERSES_PRO
    if plan == UserSubscription.PLAN_PLUS:
        return settings.MAX_CONTEXT_VERSES_PLUS
    return settings.MAX_CONTEXT_VERSES_FREE


def _plan_monthly_limit(plan: str) -> int | None:
    """Return monthly ask quota for the selected plan."""
    if settings.DISABLE_ALL_QUOTAS:
        return None
    quota_settings = _request_quota_settings()
    if quota_settings:
        if plan == UserSubscription.PLAN_FREE:
            return quota_settings.free_monthly_ask_limit
        if plan == UserSubscription.PLAN_PLUS:
            return quota_settings.plus_monthly_ask_limit
        if plan == UserSubscription.PLAN_PRO:
            return quota_settings.pro_monthly_ask_limit

    if plan == UserSubscription.PLAN_FREE:
        return settings.ASK_LIMIT_FREE_MONTHLY
    if plan == UserSubscription.PLAN_PLUS:
        return settings.ASK_LIMIT_PLUS_MONTHLY
    if plan == UserSubscription.PLAN_PRO:
        return settings.ASK_LIMIT_PRO_MONTHLY
    return None


def _plan_deep_mode_allowed(plan: str) -> bool:
    """Return whether deep mode is enabled for plan."""
    quota_settings = _request_quota_settings()
    if plan == UserSubscription.PLAN_FREE:
        if quota_settings:
            return quota_settings.free_deep_mode_enabled
        return settings.ENABLE_FREE_DEEP_MODE
    return True


def _plan_deep_monthly_limit(plan: str) -> int | None:
    """Return deep-mode monthly cap for the selected plan."""
    if settings.DISABLE_ALL_QUOTAS:
        return None
    quota_settings = _request_quota_settings()
    if quota_settings:
        if plan == UserSubscription.PLAN_PLUS:
            return (
                None
                if quota_settings.plus_deep_monthly_limit <= 0
                else quota_settings.plus_deep_monthly_limit
            )
        if plan == UserSubscription.PLAN_PRO:
            return (
                None
                if quota_settings.pro_deep_monthly_limit <= 0
                else quota_settings.pro_deep_monthly_limit
            )
        return 0 if not quota_settings.free_deep_mode_enabled else None

    if plan == UserSubscription.PLAN_PLUS:
        return (
            None
            if settings.ASK_LIMIT_PLUS_DEEP_MONTHLY <= 0
            else settings.ASK_LIMIT_PLUS_DEEP_MONTHLY
        )
    if plan == UserSubscription.PLAN_PRO:
        return (
            None
            if settings.ASK_LIMIT_PRO_DEEP_MONTHLY <= 0
            else settings.ASK_LIMIT_PRO_DEEP_MONTHLY
        )
    return 0 if not settings.ENABLE_FREE_DEEP_MODE else None


def _remaining_today(
    *,
    daily_limit: int | None,
    used_today: int,
) -> int | None:
    """Return remaining asks, or None when plan limits are disabled."""
    if daily_limit is None:
        return None
    return max(daily_limit - used_today, 0)


def _remaining_monthly(*, monthly_limit: int | None, used_month: int) -> int | None:
    """Return remaining monthly asks, or None when monthly caps are disabled."""
    if monthly_limit is None:
        return None
    return max(monthly_limit - used_month, 0)


def _quota_snapshot_for_user(subscription, usage, user) -> dict:
    """Build enriched quota payload with daily + monthly + deep caps."""
    daily_limit = _plan_daily_limit(subscription.plan)
    used_today = usage.ask_count
    used_month = _monthly_ask_count(user)
    monthly_limit = _plan_monthly_limit(subscription.plan)
    deep_monthly_limit = _plan_deep_monthly_limit(subscription.plan)
    deep_used_month = _monthly_deep_ask_count(user)
    return {
        "plan": subscription.plan,
        "daily_limit": daily_limit,
        "used_today": used_today,
        "remaining_today": _remaining_today(
            daily_limit=daily_limit,
            used_today=used_today,
        ),
        "monthly_limit": monthly_limit,
        "used_month": used_month,
        "remaining_month": _remaining_monthly(
            monthly_limit=monthly_limit,
            used_month=used_month,
        ),
        "deep_mode_allowed": _plan_deep_mode_allowed(subscription.plan),
        "deep_monthly_limit": deep_monthly_limit,
        "deep_used_month": deep_used_month,
        "deep_remaining_month": _remaining_monthly(
            monthly_limit=deep_monthly_limit,
            used_month=deep_used_month,
        ),
    }


def _quota_violation_for_request(
    *,
    subscription,
    usage,
    user,
    mode: str,
) -> tuple[str, str, dict] | None:
    """Return violation tuple (code, message, snapshot) if request exceeds caps."""
    snapshot = _quota_snapshot_for_user(subscription, usage, user)
    if mode == AskEvent.MODE_DEEP and not snapshot["deep_mode_allowed"]:
        return (
            "deep_mode_not_included",
            "Deep mode is not included in your current plan.",
            snapshot,
        )
    if (
        snapshot["daily_limit"] is not None
        and snapshot["used_today"] >= snapshot["daily_limit"]
    ):
        return (
            "daily_quota_exceeded",
            "Daily ask limit reached for your plan.",
            snapshot,
        )
    if (
        snapshot["monthly_limit"] is not None
        and snapshot["used_month"] >= snapshot["monthly_limit"]
    ):
        return (
            "monthly_quota_exceeded",
            "Monthly ask limit reached for your plan.",
            snapshot,
        )
    if (
        mode == AskEvent.MODE_DEEP
        and snapshot["deep_monthly_limit"] is not None
        and snapshot["deep_used_month"] >= snapshot["deep_monthly_limit"]
    ):
        return (
            "deep_quota_exceeded",
            "Deep-mode monthly limit reached for your plan.",
            snapshot,
        )
    return None


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
    if language == "hi":
        normalized_language = "hi"
    elif language == "hinglish":
        normalized_language = "hinglish"
    else:
        normalized_language = "en"
    label_prefix = primary_theme.replace("_", " ").title()

    if normalized_language == "hinglish":
        prompts = [
            {
                "label": f"{label_prefix}: 3-step plan",
                "prompt": (
                    f"Agle 24 ghante ke liye is issue par practical 3-step plan do: "
                    f"{message}"
                ),
                "intent": "action_plan",
            },
            {
                "label": f"{label_prefix}: deeper meaning",
                "prompt": (
                    "Ek key verse ko simple Hinglish mein samjhao aur batao main aaj "
                    "kaise apply karoon."
                ),
                "intent": "deeper_meaning",
            },
            {
                "label": "Self-reflection",
                "prompt": (
                    "Is guidance ke basis par ek reflection sawal aur ek journaling "
                    "prompt poochho."
                ),
                "intent": "self_reflection",
            },
        ]
    elif normalized_language == "hi":
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
        quota_snapshot = _quota_snapshot_for_user(
            subscription,
            usage,
            request.user,
        )
        return Response(
            {
                "username": request.user.get_username(),
                **quota_snapshot,
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
        quota_snapshot = _quota_snapshot_for_user(
            subscription,
            usage,
            request.user,
        )
        return Response(
            {
                "username": request.user.get_username(),
                **quota_snapshot,
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
        quota_violation = _quota_violation_for_request(
            subscription=subscription,
            usage=usage,
            user=request.user,
            mode=data["mode"],
        )
        if quota_violation is not None:
            violation_code, violation_message, snapshot = quota_violation
            _log_ask_event(
                user_id=request.user.get_username(),
                source=AskEvent.SOURCE_API,
                mode=data["mode"],
                outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
                plan=subscription.plan,
            )
            return _error_response(
                message=violation_message,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code=violation_code,
                extra=snapshot,
            )

        response_language = resolve_guidance_language(
            data["language"],
            data["message"],
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
        quota_snapshot = _quota_snapshot_for_user(
            subscription,
            usage,
            request.user,
        )
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
            "intent_type": guidance.intent_type,
            "show_meaning": guidance.show_meaning and bool(guidance.meaning),
            "show_actions": guidance.show_actions and bool(guidance.actions),
            "show_reflection": (
                guidance.show_reflection and bool(guidance.reflection)
            ),
            "show_related_verses": guidance.show_related_verses,
            "verse_references": [
                f"{verse.chapter}.{verse.verse}" for verse in verses
            ],
            "related_verses": _related_verses_payload_for_response(
                guidance=guidance,
                message=data["message"],
                verses=verses,
            ),
            "language": data["language"],
            "response_language": response_language,
            **quota_snapshot,
            "engagement": _serialize_engagement_profile(engagement),
        }
        follow_ups = []
        if guidance.show_actions:
            follow_ups = _build_contextual_follow_ups(
                message=data["message"],
                mode=data["mode"],
                language=response_language,
                query_themes=retrieval.query_themes,
            )
        response_data["follow_ups"] = follow_ups
        if follow_ups:
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
        response_language = resolve_guidance_language(
            data["language"],
            data["message"],
        )
        follow_ups = _build_contextual_follow_ups(
            message=data["message"],
            mode=data["mode"],
            language=response_language,
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
                "response_language": response_language,
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


class AnalyticsEventIngestView(APIView):
    """Capture frontend growth events (starter/share/copy/ask submit)."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        """Validate and persist growth event payload."""
        serializer = AnalyticsEventIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        _log_growth_event(
            request=request,
            event_type=data["event_type"],
            source=data["source"],
            path=data.get("path", "") or request.path,
            metadata=data.get("metadata", {}),
        )
        response = Response({"status": "ok"}, status=status.HTTP_201_CREATED)
        _attach_web_audience_cookie(request, response)
        return response


class AnalyticsSummaryView(APIView):
    """Staff-only growth snapshot and trends for dashboard/reporting."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return all-time totals plus daily trends and conversion metrics."""
        if not request.user.is_staff:
            return _error_response(
                message="Admin access required.",
                status_code=status.HTTP_403_FORBIDDEN,
                code="admin_required",
            )

        serializer = AnalyticsSummaryRequestSerializer(
            data={"days": request.query_params.get("days", 7)}
        )
        serializer.is_valid(raise_exception=True)
        days = serializer.validated_data["days"]

        today = timezone.localdate()
        since = timezone.now() - timedelta(days=days - 1)

        ask_qs = AskEvent.objects.filter(created_at__gte=since)
        growth_qs = GrowthEvent.objects.filter(created_at__gte=since)

        daily_rows = []
        for offset in range(days):
            day = today - timedelta(days=(days - 1 - offset))
            day_ask_qs = ask_qs.filter(created_at__date=day)
            day_growth_qs = growth_qs.filter(created_at__date=day)
            landing_views = day_growth_qs.filter(
                event_type=GrowthEvent.EVENT_LANDING_VIEW,
                source=GrowthEvent.SOURCE_CHAT_UI,
            ).count()
            starter_clicks = day_growth_qs.filter(
                event_type=GrowthEvent.EVENT_STARTER_CLICK,
                source=GrowthEvent.SOURCE_CHAT_UI,
            ).count()
            ask_submits = day_growth_qs.filter(
                event_type=GrowthEvent.EVENT_ASK_SUBMIT,
                source=GrowthEvent.SOURCE_CHAT_UI,
            ).count()
            daily_rows.append(
                {
                    "date": day.isoformat(),
                    "unique_visitors": WebAudienceProfile.objects.filter(
                        last_seen_at__date=day,
                    ).count(),
                    "queries_fired": day_ask_qs.count(),
                    "queries_served": day_ask_qs.filter(
                        outcome=AskEvent.OUTCOME_SERVED,
                    ).count(),
                    "landing_views": landing_views,
                    "starter_clicks": starter_clicks,
                    "ask_submits": ask_submits,
                }
            )

        landing_window = growth_qs.filter(
            event_type=GrowthEvent.EVENT_LANDING_VIEW,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        starter_window = growth_qs.filter(
            event_type=GrowthEvent.EVENT_STARTER_CLICK,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        ask_submit_window = growth_qs.filter(
            event_type=GrowthEvent.EVENT_ASK_SUBMIT,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()
        share_window = growth_qs.filter(
            event_type=GrowthEvent.EVENT_SHARE_CLICK,
            source=GrowthEvent.SOURCE_CHAT_UI,
        ).count()

        source_counts = {}
        for row in WebAudienceProfile.objects.exclude(first_utm_source=""):
            source = row.first_utm_source
            source_counts[source] = source_counts.get(source, 0) + 1
        top_sources = [
            {"source": source, "visitors": count}
            for source, count in sorted(
                source_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:8]
        ]

        return Response(
            {
                "window_days": days,
                "all_time": {
                    "unique_visitors": WebAudienceProfile.objects.count(),
                    "unique_users_used": AskEvent.objects.filter(
                        outcome=AskEvent.OUTCOME_SERVED,
                    ).values("user_id").distinct().count(),
                    "queries_fired": AskEvent.objects.count(),
                    "queries_served": AskEvent.objects.filter(
                        outcome=AskEvent.OUTCOME_SERVED,
                    ).count(),
                },
                "conversion": {
                    "landing_views": landing_window,
                    "starter_clicks": starter_window,
                    "ask_submits": ask_submit_window,
                    "share_clicks": share_window,
                    "starter_click_rate_pct": round(
                        (starter_window / landing_window * 100)
                        if landing_window
                        else 0,
                        2,
                    ),
                    "ask_submit_rate_pct": round(
                        (ask_submit_window / landing_window * 100)
                        if landing_window
                        else 0,
                        2,
                    ),
                    "share_rate_pct": round(
                        (share_window / landing_window * 100)
                        if landing_window
                        else 0,
                        2,
                    ),
                },
                "top_sources": top_sources,
                "daily": daily_rows,
            }
        )


class SharedAnswerCreateView(APIView):
    """Create a shareable answer card from a guidance response."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        """Persist a guidance response and return a public share URL."""
        serializer = SharedAnswerCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        question = str(data.get("question", "")).strip()
        if not question:
            question = "What does the Bhagavad Gita say about this situation?"
        audience_id = _resolve_web_audience_id(request)
        shared = SharedAnswer.objects.create(
            question=question,
            guidance=data["guidance"],
            meaning=data.get("meaning", ""),
            actions=data.get("actions", []),
            reflection=data.get("reflection", ""),
            verse_references=data["verse_references"],
            language=data["language"],
            user_id=audience_id,
        )
        share_url = f"/share/{shared.share_id}/"
        response = Response(
            {"share_id": str(shared.share_id), "share_url": share_url},
            status=status.HTTP_201_CREATED,
        )
        _attach_web_audience_cookie(request, response)
        return response


class SharedAnswerPageView(View):
    """Public OG-optimized page for a shared guidance answer."""

    template_name = "guide_api/shared_answer.html"

    def get(self, request, share_id: str, legacy_suffix: str = ""):
        """Render the answer card with rich Open Graph metadata."""
        if legacy_suffix:
            # Some clients append tokens (for example: /ok); normalize to canonical URL.
            return HttpResponsePermanentRedirect(f"/share/{share_id}/")
        try:
            shared = SharedAnswer.objects.get(share_id=share_id)
        except (SharedAnswer.DoesNotExist, ValueError):
            return JsonResponse({"detail": "Not found."}, status=404)

        question_short = (
            shared.question[:120] + "…"
            if len(shared.question) > 120
            else shared.question
        )
        guidance_short = (
            shared.guidance[:200] + "…"
            if len(shared.guidance) > 200
            else shared.guidance
        )
        if shared.meaning:
            guidance_short = (
                shared.meaning[:200] + "…"
                if len(shared.meaning) > 200
                else shared.meaning
            )
        chat_url = (
            f"/api/chat-ui/?mode=simple&language={shared.language}"
            f"&prefill={quote_plus(shared.question[:500])}"
        )
        canonical_url = request.build_absolute_uri(request.path)
        structured_data = json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": question_short,
                "description": guidance_short,
                "url": canonical_url,
                "publisher": {
                    "@type": "Organization",
                    "name": "Bhagavad Gita Guide",
                    "url": request.build_absolute_uri("/"),
                },
            },
            ensure_ascii=False,
        )
        context = {
            "shared": shared,
            "question_short": question_short,
            "guidance_short": guidance_short,
            "chat_url": chat_url,
            "canonical_url": canonical_url,
            "structured_data": structured_data,
        }
        response = render(request, self.template_name, context)
        _attach_web_audience_cookie(request, response)
        return response


class DailyVerseView(APIView):
    """Return a deterministic daily verse and short reflection."""

    @staticmethod
    def _clean_signal_text(value: str) -> str:
        """Normalize noisy verse/commentary text for compact sidebar display."""
        text = str(value or "").strip()
        if not text:
            return ""
        # Decode escaped unicode markers that can appear in serialized text.
        text = text.replace("\\u0022", '"').replace("\\u000A", " ")
        text = text.replace("\n", " ").replace("\r", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _strip_signal_prefix(text: str) -> str:
        """Drop leading verse-number markers like '।।11.55।।' from snippets."""
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"^[।|\s\-\d.]+", "", cleaned).strip()
        return cleaned

    @classmethod
    def _compact_signal_text(cls, value: str, limit: int) -> str:
        """Return a meaningful sentence-like chunk with safe truncation."""
        cleaned = cls._clean_signal_text(value)
        if not cleaned:
            return ""

        # Split by sentence boundaries, then choose the first substantial fragment.
        segments = [
            cls._strip_signal_prefix(segment)
            for segment in re.split(r"(?<=[.!?।])\s+", cleaned)
            if segment.strip()
        ]
        candidate = ""
        for segment in segments:
            # Skip tiny markers like 'हे पाण्डव!' that are context but not meaning.
            alpha_len = len(re.sub(r"[^\w\u0900-\u097F]+", "", segment))
            if len(segment) >= 50 and alpha_len >= 24:
                candidate = segment
                break

        if not candidate:
            candidate = " ".join(segments[:2]).strip() or cleaned

        if len(candidate) <= limit:
            return candidate
        return candidate[: limit - 1].rstrip() + "…"

    @staticmethod
    def _resolve_daily_verse(day: date):
        """Pick a stable verse for a given day from the canonical verse table."""
        ensure_seed_verses()
        queryset = Verse.objects.order_by("chapter", "verse")
        count = queryset.count()
        if count > 0:
            return queryset[Random(day.isoformat()).randrange(count)]

        verses = retrieve_verses("daily verse", limit=1)
        return verses[0] if verses else None

    @classmethod
    def _build_daily_payload(cls, *, day: date, language: str) -> dict:
        """Return one date-seeded verse payload for API and public pages."""
        verse = cls._resolve_daily_verse(day)
        if verse is None:
            return {
                "date": day.isoformat(),
                "verse": None,
                "quote": "",
                "meaning": "",
                "reflection": "",
            }

        detail = get_verse_detail(verse.chapter, verse.verse) or {}

        sanskrit_sloka = cls._clean_signal_text(detail.get("slok", ""))
        transliteration = cls._clean_signal_text(detail.get("transliteration", ""))
        english_prose = cls._clean_signal_text(detail.get("english_meaning", ""))
        english_translation = cls._clean_signal_text(
            str(detail.get("translation", "")).strip()
            or verse.translation.strip()
        )
        hindi_meaning = cls._clean_signal_text(detail.get("hindi_meaning", ""))
        commentary = cls._clean_signal_text(verse.commentary or "")
        # Meaning line: UI language — English gloss vs Hindi gloss (not duplicate prose).
        meaning = (
            cls._compact_signal_text(hindi_meaning, 260)
            if language == "hi" and hindi_meaning
            else cls._compact_signal_text(english_translation, 260)
            or cls._compact_signal_text(english_prose, 260)
            or cls._compact_signal_text(commentary, 260)
        )
        # Quote line: always show the śloka in Devanagari when available, then
        # IAST/transliteration; avoid repeating the same English as ``meaning``.
        quote = cls._compact_signal_text(sanskrit_sloka, 260)
        if not quote:
            quote = cls._compact_signal_text(transliteration, 260)
        if not quote:
            quote = (
                cls._compact_signal_text(hindi_meaning, 260)
                if language == "hi" and hindi_meaning
                else cls._compact_signal_text(english_prose, 260)
                or cls._compact_signal_text(english_translation, 260)
            )
        if (
            meaning
            and quote
            and quote.strip() == meaning.strip()
            and transliteration
        ):
            quote = cls._compact_signal_text(transliteration, 260)
        reflection = (
            "आज इस श्लोक को अपने एक निर्णय, एक प्रतिक्रिया, और एक कर्म में उतारने का अभ्यास करें।"
            if language == "hi"
            else "Practice applying this verse today in one decision, one reaction, and one concrete action."
        )
        reference = f"{verse.chapter}.{verse.verse}"
        prefill = (
            f"Explain Bhagavad Gita {reference} in simple Hindi and show how I can apply it today."
            if language == "hi"
            else f"Explain Bhagavad Gita {reference} in simple language and help me apply it today."
        )
        return {
            "date": day.isoformat(),
            "verse": VerseSerializer(verse).data,
            "reference": reference,
            "quote": quote,
            "meaning": meaning,
            "reflection": reflection,
            "prefill": prefill,
        }

    def get(self, request):
        """Serve one date-seeded verse with language-aware meaning."""
        language = str(request.query_params.get("language", "en")).strip()
        if language not in {"en", "hi"}:
            language = "en"
        payload = self._build_daily_payload(
            day=timezone.localdate(),
            language=language,
        )
        return Response(
            {
                "verse": payload["verse"],
                "quote": payload["quote"],
                "meaning": payload["meaning"],
                "reflection": payload["reflection"],
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
        if settings.DISABLE_ALL_QUOTAS:
            return {
                "enabled": False,
                "limit": 0,
            }
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
        # Single source of truth for all plan limits exposed to the template.
        # Change settings.py (or env vars) and every UI reference updates automatically.
        plus_price_inr = settings.SUBSCRIPTION_PRICE_PLUS_INR // 100
        plus_price_usd_cents = settings.SUBSCRIPTION_PRICE_PLUS_USD
        pro_price_inr = settings.SUBSCRIPTION_PRICE_PRO_INR // 100
        pro_price_usd_cents = settings.SUBSCRIPTION_PRICE_PRO_USD
        plus_usd = f"{plus_price_usd_cents / 100:.2f}"
        pro_usd = f"{pro_price_usd_cents / 100:.2f}"
        billing_currency = _billing_currency_for_request(request)
        context.setdefault("billing_currency", billing_currency)
        context.setdefault("billing_country_code", _request_country_code(request) or "")
        default_country_code, default_country_name = _billing_country_defaults(
            request,
            requested_currency=billing_currency,
        )
        billing_user = self._chat_ui_authenticated_user(request)
        context.setdefault(
            "billing_name_default",
            (
                billing_user.get_full_name() or billing_user.username
                if billing_user
                else str(request.session.get("chat_ui_auth_username", "")).strip()
            ),
        )
        context.setdefault(
            "billing_email_default",
            billing_user.email if billing_user else "",
        )
        context.setdefault("billing_country_name_default", default_country_name)
        context.setdefault("billing_country_code_default", default_country_code)
        default_plan_limits = {
            "free_daily": _plan_daily_limit(UserSubscription.PLAN_FREE),
            "free_monthly": _plan_monthly_limit(UserSubscription.PLAN_FREE),
            # Plus: total monthly pool; deep is a sub-limit within that pool.
            "plus_monthly": _plan_monthly_limit(UserSubscription.PLAN_PLUS),
            "plus_deep_monthly": _plan_deep_monthly_limit(UserSubscription.PLAN_PLUS),
            # Pro: total monthly pool; deep limit may be capped by settings.
            "pro_monthly": _plan_monthly_limit(UserSubscription.PLAN_PRO),
            "pro_deep_monthly": _plan_deep_monthly_limit(UserSubscription.PLAN_PRO),
            "free_deep_enabled": _plan_deep_mode_allowed(UserSubscription.PLAN_FREE),
            "plus_price_inr": plus_price_inr,
            "plus_price_usd": plus_usd,
            "pro_price_inr": pro_price_inr,
            "pro_price_usd": pro_usd,
        }
        # Hydrate all expected keys even if a caller provided an empty/partial map.
        context_plan_limits = context.get("plan_limits")
        if not isinstance(context_plan_limits, dict):
            context_plan_limits = {}
        context["plan_limits"] = {
            **default_plan_limits,
            **context_plan_limits,
        }
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
        latest_billing_record = None
        if billing_user:
            latest_billing_record = (
                BillingRecord.objects.filter(user=billing_user)
                .order_by("-created_at")
                .first()
            )
        context.setdefault("latest_billing_record", latest_billing_record)
        response = render(request, self.template_name, context)
        _attach_web_audience_cookie(request, response)
        return response

    def _chat_ui_analytics_user_id(self, request, authenticated_username: str) -> str:
        """Build a stable telemetry ID for guests and authenticated users."""
        if authenticated_username:
            return authenticated_username
        guest_id = str(getattr(request, "chat_ui_guest_id", "")).strip()
        if guest_id:
            return f"guest:{guest_id}"
        return "guest:anonymous"

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

    @staticmethod
    def _sync_guest_daily_quota(identity: GuestChatIdentity) -> GuestChatIdentity:
        """Reset per-day guest usage when the browser returns on a new day."""
        today = timezone.localdate()
        if identity.daily_asks_date != today:
            identity.daily_asks_date = today
            identity.daily_asks_used = 0
            identity.save(
                update_fields=[
                    "daily_asks_date",
                    "daily_asks_used",
                    "last_seen_at",
                ],
            )
        return identity

    def _guest_quota_snapshot(self, request) -> dict | None:
        """Summarize guest chat availability for the current browser."""
        identity = self._guest_identity(request)
        if identity is None:
            return None
        identity = self._sync_guest_daily_quota(identity)
        guest_quota = self._guest_limit_settings()
        limit_enabled = guest_quota["enabled"]
        limit = guest_quota["limit"]
        used = identity.daily_asks_used
        return {
            "ask_limit": limit,
            "asks_used": used,
            "remaining_asks": max(limit - used, 0) if limit_enabled else None,
            "limit_reached": (used >= limit) if limit_enabled else False,
            "limit_enabled": limit_enabled,
        }

    def _consume_guest_conversation_slot(self, request) -> dict:
        """Count each guest prompt against the browser's daily guest cap."""
        identity = self._guest_identity(request)
        if identity is None:
            return {"allowed": True, "snapshot": None}
        identity = self._sync_guest_daily_quota(identity)
        guest_quota = self._guest_limit_settings()
        if (
            guest_quota["enabled"]
            and identity.daily_asks_used >= guest_quota["limit"]
        ):
            return {
                "allowed": False,
                "snapshot": self._guest_quota_snapshot(request),
            }
        update_fields = ["last_seen_at", "total_asks", "daily_asks_used"]
        identity.total_asks += 1
        identity.daily_asks_used += 1
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
        deep_lock_error = ""
        if (
            mode == AskEvent.MODE_DEEP
            and not authenticated_username
            and not settings.ENABLE_FREE_DEEP_MODE
        ):
            mode = AskEvent.MODE_SIMPLE
            deep_lock_error = (
                "Deep mode is available on Plus and Pro plans. "
                "You can continue in Simple mode or sign in to upgrade."
            )
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
        _track_web_visit(request, source=WebAudienceProfile.SOURCE_CHAT_UI)
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
        quota_snapshot = None
        selected_plan = UserSubscription.PLAN_FREE
        if authenticated_username:
            quota_state = self._resolve_chat_ui_quota(default_user_id)
            if quota_state is not None:
                selected_plan = quota_state["subscription"].plan
                quota_snapshot = _quota_snapshot_for_user(
                    quota_state["subscription"],
                    quota_state["usage"],
                    quota_state["user"],
                )
        return self._render_chat_ui(
            request,
            {
                "response_data": None,
                "error": deep_lock_error,
                "feedback_message": "",
                "selected_plan": selected_plan,
                "quota_snapshot": quota_snapshot,
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
        analytics_user_id = self._chat_ui_analytics_user_id(
            request,
            authenticated_username,
        )
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

        if (
            mode == AskEvent.MODE_DEEP
            and not authenticated_username
            and not settings.ENABLE_FREE_DEEP_MODE
        ):
            return self._render_chat_ui(
                request,
                {
                    "response_data": None,
                    "error": (
                        "Deep mode is available on Plus and Pro plans. "
                        "Please sign in and upgrade to continue with Deep mode."
                    ),
                    "feedback_message": "",
                    "active_conversation_id": "",
                    "conversation_messages": self._guest_conversation_messages(
                        request,
                    ),
                    "conversations": [],
                    "user_id": user_id,
                    "is_guest_chat": True,
                    "mode": AskEvent.MODE_SIMPLE,
                    "language": language,
                    "message": message,
                    "starter_prompts": starter_prompts,
                    "recent_questions": recent_questions,
                    "follow_up_prompts": [],
                },
            )

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
                user_id=analytics_user_id,
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
        if quota:
            quota_violation = _quota_violation_for_request(
                subscription=quota["subscription"],
                usage=quota["usage"],
                user=quota["user"],
                mode=mode,
            )
            if quota_violation is not None:
                _, violation_message, violation_snapshot = quota_violation
                _log_ask_event(
                    user_id=analytics_user_id,
                    source=AskEvent.SOURCE_CHAT_UI,
                    mode=mode,
                    outcome=AskEvent.OUTCOME_BLOCKED_QUOTA,
                    plan=quota["subscription"].plan,
                )
                return self._render_chat_ui(
                    request,
                    {
                        "response_data": None,
                        "error": violation_message,
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
                        "selected_plan": quota["subscription"].plan,
                        "quota_snapshot": violation_snapshot,
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
                    user_id=analytics_user_id,
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
                    plan=quota["subscription"].plan if quota else UserSubscription.PLAN_FREE,
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
            "question": message,
            "guidance": guidance.guidance,
            "verses": VerseSerializer(verses, many=True).data,
            "meaning": guidance.meaning,
            "actions": guidance.actions,
            "reflection": guidance.reflection,
            "intent_type": guidance.intent_type,
            "show_meaning": guidance.show_meaning and bool(guidance.meaning),
            "show_actions": guidance.show_actions and bool(guidance.actions),
            "show_reflection": (
                guidance.show_reflection and bool(guidance.reflection)
            ),
            "show_related_verses": guidance.show_related_verses,
            "verse_references": [
                f"{verse.chapter}.{verse.verse}" for verse in verses
            ],
            "related_verses": _related_verses_payload_for_response(
                guidance=guidance,
                message=message,
                verses=verses,
            ),
            "language": language,
            "response_language": resolve_guidance_language(language, message),
        }
        follow_ups = []
        if guidance.show_actions:
            follow_ups = _build_contextual_follow_ups(
                message=message,
                mode=mode,
                language=response_data["response_language"],
                query_themes=retrieval.query_themes,
            )
        response_data["follow_ups"] = follow_ups
        if follow_ups:
            _log_follow_up_events(
                user_id=analytics_user_id,
                source=FollowUpEvent.SOURCE_CHAT_UI,
                event_type=FollowUpEvent.EVENT_SHOWN,
                mode=mode,
                follow_ups=follow_ups,
            )
        if follow_up_intent:
            _log_follow_up_events(
                user_id=analytics_user_id,
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
            quota_snapshot = _quota_snapshot_for_user(
                quota["subscription"],
                quota["usage"],
                quota["user"],
            )
            response_data.update(quota_snapshot)
        _log_ask_event(
            user_id=analytics_user_id,
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
                    "daily_limit": response_data.get("daily_limit"),
                    "used_today": response_data.get("used_today", 0),
                    "remaining_today": response_data.get("remaining_today"),
                    "monthly_limit": response_data.get("monthly_limit"),
                    "used_month": response_data.get("used_month", 0),
                    "remaining_month": response_data.get("remaining_month"),
                    "deep_mode_allowed": response_data.get(
                        "deep_mode_allowed",
                    ),
                    "deep_monthly_limit": response_data.get(
                        "deep_monthly_limit",
                    ),
                    "deep_used_month": response_data.get(
                        "deep_used_month",
                        0,
                    ),
                    "deep_remaining_month": response_data.get(
                        "deep_remaining_month",
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
        message = normalize_chat_user_message(str(message or "").strip())
        language = resolve_guidance_language(language, message)
        guest_messages = self._guest_conversation_objects(request)
        conversation_messages = guest_messages + [
            SimpleNamespace(role=Message.ROLE_USER, content=message)
        ]
        intent = classify_user_intent(message, mode=mode)
        if intent.intent_type == "verse_explanation" and intent.explicit_references:
            ensure_seed_verses()
            primary_ref = intent.explicit_references[0]
            parsed = tuple(int(part) for part in primary_ref.split(".", 1))
            verse = Verse.objects.filter(
                chapter=parsed[0],
                verse=parsed[1],
            ).first()
            if verse is not None:
                verses = [verse]
                support_verses = [verse, *get_related_verses(message=message, seed_verses=[verse], limit=4)]
                retrieval = empty_retrieval_result(
                    intent=intent,
                    query_interpretation={
                        **intent.as_dict(),
                        "life_domain": "exact verse explanation",
                        "match_strictness": "exact_reference",
                        "confidence": 0.99,
                    },
                    retrieval_mode="direct_reference",
                )
                guidance = build_verse_explanation(
                    message=message,
                    verse=verse,
                    support_verses=support_verses,
                    language=language,
                    mode=mode,
                    conversation_messages=conversation_messages,
                    max_output_tokens=_plan_max_output_tokens(UserSubscription.PLAN_FREE),
                    intent=intent,
                )
            else:
                verses = []
                retrieval = empty_retrieval_result(
                    intent=intent,
                    query_interpretation={
                        **intent.as_dict(),
                        "life_domain": "missing verse reference",
                        "match_strictness": "exact_reference",
                        "confidence": 0.25,
                    },
                    retrieval_mode="direct_reference_missing",
                )
                guidance = build_guidance(
                    message,
                    verses,
                    conversation_messages=conversation_messages,
                    language=language,
                    query_interpretation=retrieval.query_interpretation,
                    mode=mode,
                    max_output_tokens=_plan_max_output_tokens(UserSubscription.PLAN_FREE),
                    intent_analysis=intent.as_dict(),
                )
        elif intent.intent_type == "chapter_explanation" and intent.chapter_number:
            verses = []
            retrieval = empty_retrieval_result(
                intent=intent,
                query_interpretation={
                    **intent.as_dict(),
                    "life_domain": "chapter explanation",
                    "match_strictness": "direct",
                    "confidence": 0.95,
                },
                retrieval_mode="direct_chapter",
            )
            guidance = build_chapter_explanation(
                message=message,
                chapter_number=intent.chapter_number,
                language=language,
            )
        elif intent.intent_type in {"greeting", "casual_chat"}:
            verses = []
            retrieval = empty_retrieval_result(
                intent=intent,
                query_interpretation={
                    **intent.as_dict(),
                    "life_domain": "conversation",
                    "match_strictness": "none",
                    "confidence": 0.9,
                },
                retrieval_mode="none",
            )
            guidance = build_guidance(
                message,
                verses,
                conversation_messages=conversation_messages,
                language=language,
                query_interpretation=retrieval.query_interpretation,
                mode=mode,
                max_output_tokens=_plan_max_output_tokens(UserSubscription.PLAN_FREE),
                intent_analysis=intent.as_dict(),
            )
        else:
            retrieval = retrieve_verses_with_trace(
                message=message,
                limit=_plan_max_context_verses(UserSubscription.PLAN_FREE, mode),
            )
            verses = refine_verses_for_guidance(message, retrieval.verses)
            guidance = build_guidance(
                message,
                verses,
                conversation_messages=conversation_messages,
                language=language,
                query_interpretation=retrieval.query_interpretation,
                mode=mode,
                max_output_tokens=_plan_max_output_tokens(UserSubscription.PLAN_FREE),
                intent_analysis=intent.as_dict(),
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
        snapshot = _quota_snapshot_for_user(subscription, usage, user)
        return {
            "user": user,
            "subscription": subscription,
            "usage": usage,
            "snapshot": snapshot,
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
            UserSubscription.PLAN_PLUS,
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
                    **refreshed["snapshot"],
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
        auth_login(request, user)
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
        auth_login(request, user)
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
        auth_logout(request)
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
        session_username = str(
            request.session.get("chat_ui_auth_username", ""),
        ).strip()
        if session_username:
            return session_username
        if request.user and request.user.is_authenticated:
            return request.user.get_username()
        return "guest"

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
        session_username = str(
            request.session.get("chat_ui_auth_username", ""),
        ).strip()
        if session_username:
            return session_username
        if request.user and request.user.is_authenticated:
            return request.user.get_username()
        return ""

    @staticmethod
    def _chat_ui_authenticated_user(request):
        """Return the authenticated Django user, or a session-mapped fallback."""
        username = str(request.session.get("chat_ui_auth_username", "")).strip()
        user_model = get_user_model()
        if username:
            return user_model.objects.filter(username=username).first()
        if request.user and request.user.is_authenticated:
            return request.user
        return None

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
    """Resolve active chat-ui user, preferring explicit chat-ui session identity."""
    # In DRF APIView, access session from the underlying Django request
    session = getattr(request, "session", None)
    if session is None:
        session = getattr(request, "_request", request).session

    # Prefer the explicit chat-ui username when present so billing and
    # subscription actions affect the same account visible in the web UI.
    username = session.get("chat_ui_auth_username")
    if username:
        User = get_user_model()
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            pass

    django_request = getattr(request, "_request", request)
    if getattr(django_request, "user", None) and django_request.user.is_authenticated:
        return django_request.user

    token_key = session.get("chat_ui_auth_token")
    if token_key:
        try:
            return Token.objects.select_related("user").get(key=token_key).user
        except Token.DoesNotExist:
            return None
    return None


def _normalize_paid_plan(raw_value: str | None) -> str | None:
    """Return normalized paid tier (`plus` or `pro`) or None."""
    value = str(raw_value or "").strip().lower()
    if value in {UserSubscription.PLAN_PLUS, UserSubscription.PLAN_PRO}:
        return value
    return None


def _request_country_code(request) -> str | None:
    """Best-effort country code from edge headers or language hints."""
    meta = request.META
    for key in (
        "HTTP_CF_IPCOUNTRY",
        "HTTP_CLOUDFRONT_VIEWER_COUNTRY",
        "HTTP_X_COUNTRY_CODE",
        "HTTP_X_APPENGINE_COUNTRY",
    ):
        value = str(meta.get(key, "")).strip().upper()
        if len(value) == 2 and value.isalpha():
            return value

    # Fallback heuristic when edge country headers are unavailable.
    accept_language = str(meta.get("HTTP_ACCEPT_LANGUAGE", "")).lower()
    if "-in" in accept_language or "en-in" in accept_language or "hi-in" in accept_language:
        return "IN"
    return None


def _billing_currency_for_request(
    request,
    *,
    requested_currency: str | None = None,
) -> str:
    """Return enforced billing currency: INR for India, USD for other known countries."""
    accept_language = str(request.META.get("HTTP_ACCEPT_LANGUAGE", "")).lower()
    # Locale override for India users when edge geo is inaccurate.
    if "-in" in accept_language or "en-in" in accept_language or "hi-in" in accept_language:
        return UserSubscription.CURRENCY_INR

    country_code = _request_country_code(request)
    if country_code == "IN":
        return UserSubscription.CURRENCY_INR
    if country_code:
        return UserSubscription.CURRENCY_USD

    # Unknown country: preserve explicit request if valid, otherwise default INR.
    req = str(requested_currency or "").strip().upper()
    if req in {UserSubscription.CURRENCY_INR, UserSubscription.CURRENCY_USD}:
        return req
    return UserSubscription.CURRENCY_INR


def _payment_amount_for_plan(*, plan: str, currency: str) -> int:
    """Return smallest-unit payment amount for selected plan and currency."""
    currency = currency.upper()
    if plan == UserSubscription.PLAN_PLUS:
        if currency == UserSubscription.CURRENCY_INR:
            return settings.SUBSCRIPTION_PRICE_PLUS_INR
        return settings.SUBSCRIPTION_PRICE_PLUS_USD
    if currency == UserSubscription.CURRENCY_INR:
        return settings.SUBSCRIPTION_PRICE_PRO_INR
    return settings.SUBSCRIPTION_PRICE_PRO_USD


def _infer_plan_from_amount(*, amount: int, currency: str) -> str:
    """Infer paid tier from settled payment amount; fallback to pro."""
    currency = currency.upper()
    if (
        amount == _payment_amount_for_plan(
            plan=UserSubscription.PLAN_PLUS,
            currency=currency,
        )
    ):
        return UserSubscription.PLAN_PLUS
    return UserSubscription.PLAN_PRO


class CreateOrderView(APIView):
    """Create a Razorpay order for subscription payment."""

    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        try:
            import razorpay
        except ModuleNotFoundError:
            return Response(
                {"error": "Payment SDK not available on server"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Get user - first try DRF auth, then session lookup
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

        selected_plan = _normalize_paid_plan(request.data.get("plan"))
        if selected_plan is None:
            selected_plan = UserSubscription.PLAN_PRO

        # Enforce currency by country: INR (India), USD (outside India).
        currency = _billing_currency_for_request(
            request,
            requested_currency=request.data.get("currency"),
        )

        amount = _payment_amount_for_plan(
            plan=selected_plan,
            currency=currency,
        )

        client = razorpay.Client(auth=(key_id, key_secret))

        try:
            billing_profile = _collect_billing_profile(request, user=user)
            order_data = {
                "amount": amount,
                "currency": currency,
                "receipt": f"sub_{user.id}_{timezone.now().timestamp()}",
                "notes": {
                    "user_id": str(user.id),
                    "plan": selected_plan,
                    "billing_email": billing_profile["billing_email"][:64],
                    "billing_country": billing_profile[
                        "billing_country_code"
                    ][:2],
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

            _upsert_billing_record(
                user=user,
                subscription=subscription,
                order_id=order["id"],
                plan=selected_plan,
                currency=currency,
                amount_minor=amount,
                billing_profile=billing_profile,
                payment_status=BillingRecord.STATUS_CREATED,
                raw_order_payload=order,
            )

            pending_plans = request.session.get("pending_subscription_plans", {})
            if not isinstance(pending_plans, dict):
                pending_plans = {}
            pending_plans[order["id"]] = selected_plan
            request.session["pending_subscription_plans"] = pending_plans

            return Response({
                "order_id": order["id"],
                "amount": amount,
                "currency": currency,
                "plan": selected_plan,
                "key_id": key_id,
                "user_email": user.email,
                "user_name": user.get_full_name() or user.username,
                "billing_country_code": billing_profile["billing_country_code"],
                "billing_country_name": billing_profile["billing_country_name"],
            })

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyPaymentView(APIView):
    """Verify Razorpay payment signature and activate subscription."""

    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        import hmac
        import hashlib

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

            pending_plans = request.session.get("pending_subscription_plans", {})
            pending_plan = None
            if isinstance(pending_plans, dict):
                pending_plan = _normalize_paid_plan(
                    pending_plans.get(razorpay_order_id),
                )

            requested_plan = _normalize_paid_plan(request.data.get("plan"))
            selected_plan = pending_plan or requested_plan or UserSubscription.PLAN_PRO

            subscription.plan = selected_plan
            subscription.is_active = True
            subscription.subscription_end_date = timezone.now() + timedelta(days=30)
            subscription.save()

            billing_record = BillingRecord.objects.filter(
                razorpay_order_id=razorpay_order_id,
            ).first()
            billing_profile = (
                {
                    "billing_name": billing_record.billing_name,
                    "billing_email": billing_record.billing_email,
                    "business_name": billing_record.business_name,
                    "gstin": billing_record.gstin,
                    "billing_country_code": billing_record.billing_country_code,
                    "billing_country_name": billing_record.billing_country_name,
                    "billing_state": billing_record.billing_state,
                    "billing_city": billing_record.billing_city,
                    "billing_postal_code": billing_record.billing_postal_code,
                    "billing_address": billing_record.billing_address,
                    "tax_treatment": billing_record.tax_treatment,
                    "is_international": billing_record.is_international,
                }
                if billing_record
                else _collect_billing_profile(request, user=user)
            )
            _upsert_billing_record(
                user=user,
                subscription=subscription,
                order_id=razorpay_order_id,
                plan=selected_plan,
                currency=subscription.payment_currency or UserSubscription.CURRENCY_INR,
                amount_minor=_payment_amount_for_plan(
                    plan=selected_plan,
                    currency=subscription.payment_currency
                    or UserSubscription.CURRENCY_INR,
                ),
                billing_profile=billing_profile,
                payment_status=BillingRecord.STATUS_VERIFIED,
                payment_id=razorpay_payment_id,
                verified_at=timezone.now(),
            )

            if isinstance(pending_plans, dict) and razorpay_order_id in pending_plans:
                pending_plans.pop(razorpay_order_id, None)
                request.session["pending_subscription_plans"] = pending_plans

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
                amount = int(payment_entity.get("amount") or 0)
                currency = str(payment_entity.get("currency") or "INR")

                if order_id:
                    try:
                        subscription = UserSubscription.objects.get(razorpay_order_id=order_id)
                        resolved_plan = _infer_plan_from_amount(
                            amount=amount,
                            currency=currency,
                        )
                        subscription.plan = resolved_plan
                        subscription.is_active = True
                        subscription.subscription_end_date = timezone.now() + timedelta(days=30)
                        subscription.save()
                        billing_record = BillingRecord.objects.filter(
                            razorpay_order_id=order_id,
                        ).first()
                        billing_profile = (
                            {
                                "billing_name": billing_record.billing_name,
                                "billing_email": billing_record.billing_email,
                                "business_name": billing_record.business_name,
                                "gstin": billing_record.gstin,
                                "billing_country_code": billing_record.billing_country_code,
                                "billing_country_name": billing_record.billing_country_name,
                                "billing_state": billing_record.billing_state,
                                "billing_city": billing_record.billing_city,
                                "billing_postal_code": billing_record.billing_postal_code,
                                "billing_address": billing_record.billing_address,
                                "tax_treatment": billing_record.tax_treatment,
                                "is_international": billing_record.is_international,
                            }
                            if billing_record
                            else {
                                "billing_name": "",
                                "billing_email": "",
                                "business_name": "",
                                "gstin": "",
                                "billing_country_code": "",
                                "billing_country_name": "",
                                "billing_state": "",
                                "billing_city": "",
                                "billing_postal_code": "",
                                "billing_address": "",
                                "tax_treatment": BillingRecord.TAX_UNKNOWN,
                                "is_international": False,
                            }
                        )
                        _upsert_billing_record(
                            user=subscription.user,
                            subscription=subscription,
                            order_id=order_id,
                            plan=resolved_plan,
                            currency=currency,
                            amount_minor=amount,
                            billing_profile=billing_profile,
                            payment_status=BillingRecord.STATUS_CAPTURED,
                            raw_payment_payload=payment_entity,
                            payment_id=payment_entity.get("id", ""),
                            payment_method=payment_entity.get("method", ""),
                            paid_at=timezone.now(),
                        )
                    except UserSubscription.DoesNotExist:
                        pass  # Order not found, ignore

            elif event == "payment.failed":
                payment_entity = payload.get("payload", {}).get("payment", {}).get(
                    "entity",
                    {},
                )
                order_id = payment_entity.get("order_id")
                if order_id:
                    BillingRecord.objects.filter(
                        razorpay_order_id=order_id,
                    ).update(
                        payment_status=BillingRecord.STATUS_FAILED,
                        razorpay_payment_id=str(payment_entity.get("id") or "")[:64],
                        raw_payment_payload=payment_entity,
                    )

            return Response({"status": "ok"})

        except json.JSONDecodeError:
            return Response(
                {"error": "Invalid JSON"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class SubscriptionStatusView(APIView):
    """Get current user's subscription status."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
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
        subscription = _normalize_subscription_state(subscription)

        is_pro = (
            subscription.plan == UserSubscription.PLAN_PRO
            and subscription.is_active
            and (
                subscription.subscription_end_date is None
                or subscription.subscription_end_date > timezone.now()
            )
        )

        latest_billing_record = BillingRecord.objects.filter(
            user=user,
        ).order_by("-created_at").first()

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
                "INR": settings.SUBSCRIPTION_PRICE_PRO_INR,
                "USD": settings.SUBSCRIPTION_PRICE_PRO_USD,
                "plans": {
                    "plus": {
                        "INR": settings.SUBSCRIPTION_PRICE_PLUS_INR,
                        "USD": settings.SUBSCRIPTION_PRICE_PLUS_USD,
                    },
                    "pro": {
                        "INR": settings.SUBSCRIPTION_PRICE_PRO_INR,
                        "USD": settings.SUBSCRIPTION_PRICE_PRO_USD,
                    },
                },
            },
            "latest_billing_record": (
                BillingRecordSerializer(latest_billing_record).data
                if latest_billing_record
                else None
            ),
        })


class PaymentHistoryView(APIView):
    """Return payment/billing ledger rows for the signed-in user."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        user = _get_user_from_session(request)

        if not user:
            return Response(
                {"error": "Please log in to view payment history"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            limit, offset = _pagination_params(request)
        except ValueError:
            return _error_response(
                message="limit and offset must be integers.",
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_pagination",
            )

        base_qs = BillingRecord.objects.filter(user=user).order_by("-created_at")
        rows = base_qs[offset:offset + limit]
        total = base_qs.count()
        next_offset = offset + limit if (offset + limit) < total else None
        serializer = BillingRecordSerializer(rows, many=True)
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
                "results": serializer.data,
            }
        )
