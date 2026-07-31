"""Promo pricing tests."""
from __future__ import annotations

from django.test import RequestFactory, TestCase, override_settings

from apps.billing.promo import (
    first_export_promo_eligible,
    payg_amount_paise,
    payg_list_amount_inr,
)


class PromoPricingTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override_settings(
        ITR_FIRST_EXPORT_PROMO_ENABLED=True,
        ITR_FIRST_EXPORT_AMOUNT_PAISE=1000,
        ITR_PAYG_AMOUNT_PAISE=2000,
    )
    def test_first_export_promo_amount(self) -> None:
        request = self.factory.get("/")
        request.session = self.client.session
        self.assertTrue(first_export_promo_eligible(request))
        self.assertEqual(payg_amount_paise(request), 1000)
        self.assertEqual(payg_list_amount_inr(), 20)

    @override_settings(ITR_FIRST_EXPORT_PROMO_ENABLED=True)
    def test_promo_not_eligible_after_use(self) -> None:
        request = self.factory.get("/")
        session = self.client.session
        session["itr_first_promo_used"] = True
        session.save()
        request.session = session
        self.assertFalse(first_export_promo_eligible(request))
