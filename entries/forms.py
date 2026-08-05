from django import forms

from .models import EMOTION_CHOICES, Entry, Goal

SLIDER_ATTRS = {"type": "range", "min": 1, "max": 10, "step": 1, "class": "slider"}
SCORE_WIDGETS = {
    "morning_mental_score": forms.NumberInput(attrs=SLIDER_ATTRS),
    "morning_physical_score": forms.NumberInput(attrs=SLIDER_ATTRS),
    "morning_emotional_score": forms.NumberInput(attrs=SLIDER_ATTRS),
    "morning_spiritual_score": forms.NumberInput(attrs=SLIDER_ATTRS),
    "evening_mental_score": forms.NumberInput(attrs=SLIDER_ATTRS),
    "evening_physical_score": forms.NumberInput(attrs=SLIDER_ATTRS),
    "evening_emotional_score": forms.NumberInput(attrs=SLIDER_ATTRS),
    "evening_spiritual_score": forms.NumberInput(attrs=SLIDER_ATTRS),
}


class EntryForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = [
            "date",
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
            "stoic_prompt": forms.HiddenInput(),
            "stoic_response": forms.Textarea(attrs={"rows": 5}),
            "devotional_response": forms.Textarea(attrs={"rows": 5}),
            "freeform_entry": forms.Textarea(attrs={"rows": 8}),
            "exercise_notes": forms.Textarea(attrs={"rows": 3}),
        }


class MorningCheckInForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = [
            "morning_mental_score",
            "morning_physical_score",
            "morning_emotional_score",
            "morning_spiritual_score",
            "one_percent_goal",
        ]
        widgets = {
            **SCORE_WIDGETS,
            "one_percent_goal": forms.Textarea(
                attrs={"rows": 2, "placeholder": "What's one small thing that would make today 1% better?"}
            ),
        }


class EveningCheckInForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = [
            "evening_mental_score",
            "evening_physical_score",
            "evening_emotional_score",
            "evening_spiritual_score",
            "one_percent_goal_achieved",
        ]
        widgets = SCORE_WIDGETS


GoalFormSet = forms.inlineformset_factory(
    Entry,
    Goal,
    fields=["text"],
    extra=6,
    max_num=20,
    can_delete=True,
    widgets={"text": forms.TextInput(attrs={"placeholder": "Add a goal for today..."})},
)

GoalCompletionFormSet = forms.inlineformset_factory(
    Entry,
    Goal,
    fields=["completed"],
    extra=0,
    can_delete=False,
)


class MomentCheckInForm(forms.Form):
    emotions = forms.MultipleChoiceField(
        choices=EMOTION_CHOICES, widget=forms.CheckboxSelectMultiple, required=False
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "What are you feeling, and why?"}),
        required=False,
    )
