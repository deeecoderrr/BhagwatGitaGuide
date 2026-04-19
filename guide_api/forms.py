"""Forms for staff tools and reusable model-bound inputs."""

from django import forms

from guide_api.models import SadhanaDay, SadhanaProgram


class SadhanaProgramStudioForm(forms.ModelForm):
    """Course / sadhana program metadata used in Course Studio."""

    class Meta:
        model = SadhanaProgram
        fields = [
            "slug",
            "title",
            "subtitle",
            "description",
            "philosophy_blurb",
            "duration_days",
            "estimated_minutes_per_day",
            "free_sample_day_number",
            "sort_order",
            "is_published",
        ]
        widgets = {
            "slug": forms.TextInput(
                attrs={
                    "placeholder": "e.g. morning-elevation-30",
                    "class": "studio-input",
                },
            ),
            "title": forms.TextInput(
                attrs={"placeholder": "Public title", "class": "studio-input"},
            ),
            "subtitle": forms.TextInput(
                attrs={"placeholder": "Short line under the title", "class": "studio-input"},
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "What seekers experience; outcomes; tone.",
                    "class": "studio-textarea",
                },
            ),
            "philosophy_blurb": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optional wellness / non-medical disclaimer for seekers.",
                    "class": "studio-textarea",
                },
            ),
            "duration_days": forms.NumberInput(attrs={"class": "studio-input studio-input--narrow"}),
            "estimated_minutes_per_day": forms.NumberInput(
                attrs={"class": "studio-input studio-input--narrow"},
            ),
            "free_sample_day_number": forms.NumberInput(
                attrs={"class": "studio-input studio-input--narrow"},
            ),
            "sort_order": forms.NumberInput(attrs={"class": "studio-input studio-input--narrow"}),
            "is_published": forms.CheckboxInput(attrs={"class": "studio-checkbox"}),
        }


class SadhanaDayQuickForm(forms.ModelForm):
    """Add or edit a single day from Course Studio."""

    class Meta:
        model = SadhanaDay
        fields = ["day_number", "title", "summary", "intention"]
        widgets = {
            "day_number": forms.NumberInput(attrs={"class": "studio-input studio-input--narrow"}),
            "title": forms.TextInput(attrs={"class": "studio-input"}),
            "summary": forms.Textarea(
                attrs={"rows": 3, "class": "studio-textarea", "placeholder": "What happens this day"},
            ),
            "intention": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "studio-textarea",
                    "placeholder": "Closing cue — living the mantra",
                },
            ),
        }
