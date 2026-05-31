from __future__ import annotations

from django import forms


class CommentForm(forms.Form):
    guest_name = forms.CharField(
        label="Your name",
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Your name",
            }
        ),
    )
    body = forms.CharField(
        label="",
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "form-input comments-textarea",
                "placeholder": "Share a brief reflection…",
            }
        ),
    )
    parent_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
