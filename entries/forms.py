from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import EMOTION_CHOICES, AccessRequest, Entry, Feedback, Goal, Profile, SurveyResponse

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


class ScopedEntrySaveMixin:
    """Restricts save() to this form's own fields when updating an existing Entry.

    A single Entry row is edited by three independently-submitted forms (morning
    check-in, evening check-in, and the guided-journal EntryForm) that can each be
    open in a different browser tab or device at once. Plain ModelForm.save()
    writes every field on the in-memory instance, so a stale copy loaded before
    another tab's save would silently clobber that tab's changes. update_fields
    scopes the UPDATE to just the columns this form actually owns.
    """

    def save(self, commit=True):
        entry = super().save(commit=False)
        if commit:
            if entry.pk:
                # auto_now fields aren't implicitly included by Django when
                # update_fields is passed, so updated_at needs to be listed
                # explicitly or it would silently stop tracking real edits.
                entry.save(update_fields=[*self.cleaned_data.keys(), "updated_at"])
            else:
                entry.save()
        return entry


class ScoreSliderMinFixMixin:
    """PositiveSmallIntegerField.formfield() defaults min_value to 0, which
    clobbers the widget's min=1 attrs at field-construction time — so the
    rendered slider lets you drag to 0 even though the model validators
    (SCORE_VALIDATORS) require >=1, causing a silent whole-form validation
    failure. Force min back to 1 on each bound field instance."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in SCORE_WIDGETS:
            if name in self.fields:
                self.fields[name].min_value = 1
                self.fields[name].widget.attrs["min"] = 1


class EntryForm(ScopedEntrySaveMixin, forms.ModelForm):
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


class MorningCheckInForm(ScopedEntrySaveMixin, ScoreSliderMinFixMixin, forms.ModelForm):
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


class EveningCheckInForm(ScopedEntrySaveMixin, ScoreSliderMinFixMixin, forms.ModelForm):
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


class AccessRequestForm(UserCreationForm):
    # This form is filled out on a shared/family device as often as a personal one, so every
    # field disables browser autofill - otherwise one person's name/email/DOB can be offered
    # to (or silently pre-filled for) whoever fills out the form next on that same browser.
    name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autocomplete": "off"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "off"}))
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "autocomplete": "off"}))
    gender = forms.ChoiceField(choices=Profile.GENDER_CHOICES, widget=forms.Select(attrs={"autocomplete": "off"}))
    gender_self_description = forms.CharField(
        max_length=100, required=False, widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    zipcode = forms.CharField(max_length=10, widget=forms.TextInput(attrs={"autocomplete": "off"}))

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    def clean_username(self):
        username = self.cleaned_data["username"]
        if AccessRequest.objects.filter(username__iexact=username, status="pending").exists():
            raise forms.ValidationError("There's already a pending request for this username.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        if AccessRequest.objects.filter(email__iexact=email, status="pending").exists():
            raise forms.ValidationError("There's already a pending request for this email.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("gender") == "self_describe" and not cleaned_data.get("gender_self_description"):
            self.add_error("gender_self_description", "Please describe your gender.")
        return cleaned_data

    def save(self, commit=True):
        # UserCreationForm hashes the password onto self.instance via set_password()
        # in its own save(); build that (unsaved) User to reuse the hashing, then copy
        # the hash into AccessRequest instead of ever persisting the User itself.
        user = super().save(commit=False)
        access_request = AccessRequest(
            username=self.cleaned_data["username"],
            password_hash=user.password,
            name=self.cleaned_data["name"],
            email=self.cleaned_data["email"],
            date_of_birth=self.cleaned_data["date_of_birth"],
            gender=self.cleaned_data["gender"],
            gender_self_description=self.cleaned_data.get("gender_self_description", ""),
            zipcode=self.cleaned_data["zipcode"],
        )
        if commit:
            access_request.save()
        return access_request


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ["category", "message"]
        widgets = {
            "message": forms.Textarea(
                attrs={"rows": 6, "placeholder": "A bug, an idea, anything you'd like changed…"}
            ),
        }


class AccountUserForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"]
        if get_user_model().objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class AccountProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("name", "date_of_birth", "gender", "gender_self_description", "zipcode")
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("gender") == "self_describe" and not cleaned_data.get("gender_self_description"):
            self.add_error("gender_self_description", "Please describe your gender.")
        return cleaned_data


class SurveyForm(forms.ModelForm):
    class Meta:
        model = SurveyResponse
        fields = [
            "overall_rating",
            "most_used_section",
            "least_used_section",
            "feature_request",
            "friction_feedback",
            "reported_bug",
            "bug_response_time_rating",
            "appearance_rating",
            "appearance_change",
            "content_helpful",
            "favorite_part",
            "disliked_part",
        ]
        widgets = {
            "overall_rating": forms.RadioSelect,
            "most_used_section": forms.Select,
            "least_used_section": forms.Select,
            "feature_request": forms.Textarea(attrs={"rows": 3}),
            "friction_feedback": forms.Textarea(attrs={"rows": 3}),
            "reported_bug": forms.RadioSelect,
            "bug_response_time_rating": forms.RadioSelect,
            "appearance_rating": forms.RadioSelect,
            "appearance_change": forms.Textarea(attrs={"rows": 3}),
            "content_helpful": forms.RadioSelect,
            "favorite_part": forms.Textarea(attrs={"rows": 3}),
            "disliked_part": forms.Textarea(attrs={"rows": 3}),
        }
