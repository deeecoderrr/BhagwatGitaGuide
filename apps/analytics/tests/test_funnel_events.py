"""Funnel analytics tests."""
from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.analytics.events import EVENT_ITR_UPLOAD, log_itr_funnel_event
from apps.analytics.middleware import AUDIENCE_COOKIE
from apps.analytics.models import GrowthEvent


class FunnelEventTests(TestCase):
    def test_logs_event_with_visitor_cookie(self) -> None:
        request = RequestFactory().get("/itr-computation/documents/1/")
        request.COOKIES[AUDIENCE_COOKIE] = "abc123visitor"
        request.user = type("U", (), {"is_authenticated": False})()

        log_itr_funnel_event(request, EVENT_ITR_UPLOAD, document_id=7)

        ev = GrowthEvent.objects.get()
        self.assertEqual(ev.event_type, EVENT_ITR_UPLOAD)
        self.assertEqual(ev.metadata["document_id"], 7)
