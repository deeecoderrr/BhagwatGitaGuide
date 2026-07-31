from __future__ import annotations

import re

from django import forms

from apps.marketing.services_catalog import SERVICE_CHOICES


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
    notes = forms.CharField(
        required=False,
        label="Anything we should know?",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Optional — assessment year, turnover, urgency, etc.",
            },
        ),
    )
    # Honeypot — must stay empty
    company = forms.CharField(required=False, widget=forms.HiddenInput())

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
        return key
