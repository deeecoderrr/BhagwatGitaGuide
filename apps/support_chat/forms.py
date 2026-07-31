from __future__ import annotations

from django import forms

from apps.marketing.services_catalog import CA_SERVICE_BY_KEY, SERVICE_CHOICES


class NewThreadForm(forms.Form):
    subject = forms.CharField(
        max_length=200,
        label="Topic",
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. ITR-2 filing help", "autocomplete": "off"},
        ),
    )
    service = forms.ChoiceField(
        label="Related service (optional)",
        required=False,
        choices=[("", "— General question —")] + SERVICE_CHOICES,
    )
    body = forms.CharField(
        label="Your message",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "How can we help you?",
            },
        ),
    )

    def clean_service(self) -> str:
        key = (self.cleaned_data.get("service") or "").strip()
        if key and key not in CA_SERVICE_BY_KEY:
            raise forms.ValidationError("Invalid service.")
        return key


class ReplyForm(forms.Form):
    body = forms.CharField(
        label="Message",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Type your reply…",
                "class": "chat-compose__input",
            },
        ),
    )

    def clean_body(self) -> str:
        body = (self.cleaned_data.get("body") or "").strip()
        if not body:
            raise forms.ValidationError("Message cannot be empty.")
        if len(body) > 4000:
            raise forms.ValidationError("Message is too long (max 4000 characters).")
        return body
