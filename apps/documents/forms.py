from __future__ import annotations

from django import forms


class ItrUploadForm(forms.Form):
    """Upload filed ITR JSON (ITR-3). PDF is not accepted."""

    file = forms.FileField(
        label="Filed ITR JSON (ITR-3 acknowledgment / utility export)",
        allow_empty_file=False,
        widget=forms.ClearableFileInput(attrs={"accept": "application/json,.json"}),
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = getattr(f, "name", "") or ""
        if not name.lower().endswith(".json"):
            raise forms.ValidationError("Please upload a .json file.")
        return f


class DocumentReprocessForm(forms.Form):
    """Empty form for CSRF-protected POST to re-run import."""

    pass
