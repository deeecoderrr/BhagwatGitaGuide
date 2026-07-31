from __future__ import annotations

import re

from django import forms

from apps.marketing.services_catalog import CA_SERVICE_BY_KEY, SERVICE_CHOICES

ASSESSMENT_YEAR_CHOICES = [
    ("2025-26", "2025-26 (current year)"),
    ("2024-25", "2024-25"),
    ("other", "Other / not sure"),
]

INCOME_SOURCE_CHOICES = [
    ("", "— Select (optional) —"),
    ("salary", "Salary / pension"),
    ("business", "Business income"),
    ("professional", "Professional / freelancing"),
    ("capital_gains", "Capital gains"),
    ("mixed", "Mixed sources"),
    ("not_sure", "Not sure — help me decide"),
]


class AppointmentLeadForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        label="Full name",
        widget=forms.TextInput(
            attrs={"placeholder": "Your name", "autocomplete": "name"},
        ),
    )
    phone = forms.CharField(
        max_length=20,
        label="Mobile number",
        widget=forms.TextInput(
            attrs={
                "placeholder": "10-digit mobile",
                "autocomplete": "tel",
                "inputmode": "tel",
            },
        ),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={"placeholder": "you@example.com", "autocomplete": "email"},
        ),
    )
    service = forms.ChoiceField(
        label="Service you need",
        choices=[("", "— Select a service —")] + SERVICE_CHOICES,
    )
    assessment_year = forms.ChoiceField(
        label="Assessment year",
        choices=ASSESSMENT_YEAR_CHOICES,
        initial="2025-26",
    )
    income_source = forms.ChoiceField(
        label="Primary income source",
        choices=INCOME_SOURCE_CHOICES,
        required=False,
    )
    notes = forms.CharField(
        required=False,
        label="Anything else we should know?",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Optional — turnover, urgency, GSTIN status, etc.",
            },
        ),
    )
    source_page = forms.CharField(required=False, widget=forms.HiddenInput())
    # Honeypot — must stay empty
    company = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, service_key: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        key = (service_key or "").strip()
        if key and key in CA_SERVICE_BY_KEY and not self.is_bound:
            self.fields["service"].initial = key

    def clean_phone(self) -> str:
        raw = (self.cleaned_data.get("phone") or "").strip()
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10:
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")
        if len(digits) > 13:
            raise forms.ValidationError("Mobile number looks too long.")
        return raw

    def clean_company(self) -> str:
        if (self.cleaned_data.get("company") or "").strip():
            raise forms.ValidationError("Invalid submission.")
        return ""

    def clean_service(self) -> str:
        key = (self.cleaned_data.get("service") or "").strip()
        if not key:
            raise forms.ValidationError("Please select a service.")
        if key not in CA_SERVICE_BY_KEY:
            raise forms.ValidationError("Please select a valid service.")
        return key

    def income_source_display(self) -> str:
        val = (self.cleaned_data.get("income_source") or "").strip()
        if not val:
            return ""
        for k, label in INCOME_SOURCE_CHOICES:
            if k == val:
                return label
        return val
