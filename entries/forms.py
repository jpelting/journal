from django import forms

from .models import Entry

SLIDER_ATTRS = {"type": "range", "min": 1, "max": 10, "step": 1, "class": "slider"}


class EntryForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = [
            "date",
            "mental_score",
            "physical_score",
            "emotional_score",
            "spiritual_score",
            "checkin_notes",
            "stoic_prompt",
            "stoic_response",
            "devotional_prompt",
            "devotional_response",
            "freeform_entry",
            "exercise_completed",
            "exercise_type",
            "exercise_duration_minutes",
            "exercise_notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "mental_score": forms.NumberInput(attrs=SLIDER_ATTRS),
            "physical_score": forms.NumberInput(attrs=SLIDER_ATTRS),
            "emotional_score": forms.NumberInput(attrs=SLIDER_ATTRS),
            "spiritual_score": forms.NumberInput(attrs=SLIDER_ATTRS),
            "checkin_notes": forms.Textarea(attrs={"rows": 3}),
            "stoic_response": forms.Textarea(attrs={"rows": 5}),
            "devotional_response": forms.Textarea(attrs={"rows": 5}),
            "freeform_entry": forms.Textarea(attrs={"rows": 8}),
            "exercise_notes": forms.Textarea(attrs={"rows": 3}),
        }
