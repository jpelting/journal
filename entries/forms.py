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
            "introspection_response",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "stoic_prompt": forms.HiddenInput(),
            "stoic_response": forms.Textarea(attrs={"rows": 5}),
            "devotional_prompt": forms.HiddenInput(),
            "devotional_response": forms.Textarea(attrs={"rows": 5}),
            "freeform_entry": forms.Textarea(attrs={"rows": 8}),
            "introspection_response": forms.Textarea(attrs={"rows": 5}),
        }

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        if date and self.instance.user_id:
            clash = Entry.objects.filter(user=self.instance.user, date=date).exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error("date", "You already have an entry for this date.")
        return cleaned_data


class MorningCheckInForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = [
            "morning_mental_score",
            "morning_physical_score",
            "morning_emotional_score",
            "morning_spiritual_score",
            "one_percent_goal",
            "morning_anxious_about",
            "morning_within_control",
            "morning_reserve_clause",
        ]
        widgets = {
            **SCORE_WIDGETS,
            "one_percent_goal": forms.Textarea(
                attrs={"rows": 2, "placeholder": "What's one small thing that would make today 1% better?"}
            ),
            "morning_anxious_about": forms.Textarea(attrs={"rows": 2}),
            "morning_within_control": forms.Textarea(attrs={"rows": 2}),
            "morning_reserve_clause": forms.Textarea(
                attrs={"rows": 2, "placeholder": "e.g. I will deliver the project presentation today—if nothing happens to prevent me."}
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
            "evening_did_well",
            "evening_where_falter",
            "evening_could_improve",
            "evening_gratitude_audit",
        ]
        widgets = {
            **SCORE_WIDGETS,
            "evening_did_well": forms.Textarea(attrs={"rows": 2}),
            "evening_where_falter": forms.Textarea(attrs={"rows": 2}),
            "evening_could_improve": forms.Textarea(attrs={"rows": 2}),
            "evening_gratitude_audit": forms.Textarea(attrs={"rows": 2}),
        }


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
