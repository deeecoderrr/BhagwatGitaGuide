from __future__ import annotations

from django import forms


class CommentForm(forms.Form):
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
