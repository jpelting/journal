import uuid
from datetime import time

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

from .fields import EncryptedTextField

SCORE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(10)]


class StoicPrompt(models.Model):
    text = models.TextField(help_text="A stoic quote, e.g. from Marcus Aurelius, Seneca, Epictetus.")
    source = models.CharField(max_length=200, blank=True, help_text="Optional attribution, e.g. 'Meditations, Book 4'.")
    context_summary = models.TextField(blank=True, default="", help_text="Brief context about the quote/author shown under the quote.")
    reflection_prompt = models.TextField(blank=True, default="", help_text="A guiding question for the reflection.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.text[:60]


class DevotionalPrompt(models.Model):
    reference = models.CharField(max_length=100, help_text="Scripture reference, e.g. 'Philippians 4:6-7'.")
    verse_text = models.TextField(blank=True, help_text="The passage text, if you want it displayed.")
    context_summary = models.TextField(
        blank=True, help_text="2-3 sentences of historical/authorial context: who wrote it, to whom, and why."
    )
    meaning_summary = models.TextField(
        blank=True, help_text="2-3 sentences explaining what the passage means."
    )
    reflection_prompt = models.TextField(
        help_text="A question asking how the passage's principle could be applied in a modern way in the user's life."
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.reference


class IntrospectionPrompt(models.Model):
    day_of_year = models.PositiveSmallIntegerField(
        unique=True, validators=[MinValueValidator(1), MaxValueValidator(365)]
    )
    question = models.TextField()
    principle_summary = models.TextField(
        help_text="2-3 sentences explaining the principle or idea behind the question, shown before it."
    )

    class Meta:
        ordering = ["day_of_year"]

    def __str__(self):
        return f"Day {self.day_of_year}: {self.question[:60]}"

    @classmethod
    def for_date(cls, d):
        day = min(d.timetuple().tm_yday, 365)  # leap-day 366 reuses day 365's question
        return cls.objects.filter(day_of_year=day).first()


class Prayer(models.Model):
    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    day = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(31)])
    reference = models.CharField(max_length=100, blank=True, help_text="Scripture reference for the opening quote.")
    occasion = models.CharField(max_length=100, blank=True, help_text="e.g. 'Christmas Day', 'For Sunday Morning'.")
    quote = models.TextField(blank=True, help_text="The opening scripture quote.")
    body = models.TextField(help_text="The prayer text.")
    attribution = models.CharField(max_length=200, blank=True, help_text="Original contributor, if known.")

    class Meta:
        ordering = ["month", "day"]
        constraints = [models.UniqueConstraint(fields=["month", "day"], name="unique_prayer_month_day")]

    def __str__(self):
        return f"{self.month:02d}-{self.day:02d}: {self.body[:50]}"

    @classmethod
    def for_date(cls, d):
        return cls.objects.filter(month=d.month, day=d.day).first()


class StoicPractice(models.Model):
    week_number = models.PositiveSmallIntegerField(
        unique=True, validators=[MinValueValidator(1), MaxValueValidator(52)]
    )
    part = models.CharField(max_length=100, blank=True, help_text="e.g. 'The Discipline of Desire'.")
    title = models.CharField(max_length=200)
    description = models.TextField()

    class Meta:
        ordering = ["week_number"]

    def __str__(self):
        return f"Week {self.week_number}: {self.title}"

    @classmethod
    def for_date(cls, d):
        week = min(d.isocalendar()[1], 52)  # ISO week 53 (rare) reuses week 52's practice
        return cls.objects.filter(week_number=week).first()


class MotivationalQuote(models.Model):
    SLOT_CHOICES = [(1, "Morning"), (2, "Evening")]

    day_of_year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(365)])
    slot = models.PositiveSmallIntegerField(choices=SLOT_CHOICES, default=1)
    text = models.TextField()
    author = models.CharField(max_length=200)

    class Meta:
        ordering = ["day_of_year", "slot"]
        constraints = [
            models.UniqueConstraint(fields=["day_of_year", "slot"], name="unique_motivational_quote_day_slot")
        ]

    def __str__(self):
        return f"Day {self.day_of_year} ({self.get_slot_display()}): {self.text[:50]}"

    @classmethod
    def for_date(cls, d, slot=1):
        day = min(d.timetuple().tm_yday, 365)  # leap-day 366 reuses day 365, same convention as IntrospectionPrompt/StoicPractice
        return cls.objects.filter(day_of_year=day, slot=slot).first()


class SelfAffirmation(models.Model):
    SLOT_CHOICES = [(1, "Morning"), (2, "Evening")]

    day_of_year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(365)])
    slot = models.PositiveSmallIntegerField(choices=SLOT_CHOICES, default=1)
    text = models.TextField()

    class Meta:
        ordering = ["day_of_year", "slot"]
        constraints = [
            models.UniqueConstraint(fields=["day_of_year", "slot"], name="unique_self_affirmation_day_slot")
        ]

    def __str__(self):
        return f"Day {self.day_of_year} ({self.get_slot_display()}): {self.text[:50]}"

    @classmethod
    def for_date(cls, d, slot=1):
        day = min(d.timetuple().tm_yday, 365)  # leap-day 366 reuses day 365, same convention as MotivationalQuote
        return cls.objects.filter(day_of_year=day, slot=slot).first()


class Entry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entries")
    date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Part 1: check-in
    weather_summary = models.CharField(max_length=200, blank=True, help_text="Cached weather snapshot from the morning check-in.")
    forecast_summary = models.CharField(max_length=200, blank=True, help_text="Cached tomorrow's forecast from the evening check-in.")

    morning_mental_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    morning_physical_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    morning_emotional_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    morning_spiritual_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    one_percent_goal = EncryptedTextField(blank=True, help_text="One small thing that would make today 1% better.")

    evening_mental_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    evening_physical_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    evening_emotional_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    evening_spiritual_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    one_percent_goal_achieved = models.BooleanField(default=False)

    # Part 1b: Stoic daily reflection (morning prep / evening review), per the
    # "Daily Stoic Journal" template — distinct from the Part 2 guided journal below.
    # The week's practice itself isn't stored per-entry; see the stoic_practice property.
    morning_anxious_about = EncryptedTextField(blank=True, help_text="What am I anxious about today?")
    morning_within_control = EncryptedTextField(blank=True, help_text="What part of this is 100% in my control?")
    morning_reserve_clause = EncryptedTextField(
        blank=True, help_text="Today's biggest event, held with “Fate permitting.”"
    )

    evening_did_well = EncryptedTextField(blank=True, help_text="Where did I show patience, discipline, or focus?")
    evening_where_falter = EncryptedTextField(
        blank=True, help_text="Did I lose my temper, complain, procrastinate, or let my ego take over?"
    )
    evening_could_improve = EncryptedTextField(
        blank=True, help_text="If I could rewrite today, how would my ideal self respond to those exact situations?"
    )
    evening_gratitude_audit = EncryptedTextField(
        blank=True, help_text="One thing I'd deeply miss if it were permanently taken away tomorrow."
    )

    # Part 2: stoic guided journal
    stoic_prompt = models.ForeignKey(StoicPrompt, null=True, blank=True, on_delete=models.SET_NULL)
    stoic_response = EncryptedTextField(blank=True)

    # Part 3: biblical devotional
    devotional_prompt = models.ForeignKey(DevotionalPrompt, null=True, blank=True, on_delete=models.SET_NULL)
    devotional_response = EncryptedTextField(blank=True)

    # Part 4: freeform journal
    freeform_entry = EncryptedTextField(blank=True)

    # Part 5: introspection
    introspection_response = EncryptedTextField(blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "entries"
        constraints = [models.UniqueConstraint(fields=["user", "date"], name="unique_entry_per_user_per_date")]

    def __str__(self):
        return self.date.isoformat()

    def get_absolute_url(self):
        return reverse("entries:detail", args=[self.pk])

    def _blended_score(self, morning, evening):
        values = [v for v in (morning, evening) if v is not None]
        return round(sum(values) / len(values)) if values else None

    @property
    def mental_score(self):
        return self._blended_score(self.morning_mental_score, self.evening_mental_score)

    @property
    def physical_score(self):
        return self._blended_score(self.morning_physical_score, self.evening_physical_score)

    @property
    def emotional_score(self):
        return self._blended_score(self.morning_emotional_score, self.evening_emotional_score)

    @property
    def spiritual_score(self):
        return self._blended_score(self.morning_spiritual_score, self.evening_spiritual_score)

    @property
    def introspection_prompt(self):
        return IntrospectionPrompt.for_date(self.date)

    @property
    def stoic_practice(self):
        return StoicPractice.for_date(self.date)


class Goal(models.Model):
    entry = models.ForeignKey(Entry, related_name="goals", on_delete=models.CASCADE)
    text = EncryptedTextField()
    completed = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


EMOTION_CHOICES = [
    ("happy", "Happy"),
    ("grateful", "Grateful"),
    ("calm", "Calm"),
    ("excited", "Excited"),
    ("content", "Content"),
    ("tired", "Tired"),
    ("anxious", "Anxious"),
    ("sad", "Sad"),
    ("frustrated", "Frustrated"),
    ("angry", "Angry"),
    ("overwhelmed", "Overwhelmed"),
    ("lonely", "Lonely"),
]


class Profile(models.Model):
    GENDER_CHOICES = [
        ("female", "Female"),
        ("male", "Male"),
        ("nonbinary", "Non-binary"),
        ("self_describe", "Self-describe"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    name = models.CharField(max_length=150)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES)
    gender_self_description = models.CharField(max_length=100, blank=True)
    zipcode = models.CharField(max_length=10)
    last_seen_announcement_at = models.DateTimeField(
        null=True, blank=True, help_text="When this user last dismissed the What's New popup."
    )

    quotes_enabled = models.BooleanField(
        default=False, help_text="Master opt-in for daily motivational quotes (desktop display and/or mobile push)."
    )
    quote_morning_enabled = models.BooleanField(default=False)
    quote_morning_time = models.TimeField(default=time(7, 0))
    quote_evening_enabled = models.BooleanField(default=False)
    quote_evening_time = models.TimeField(default=time(20, 0))
    last_morning_quote_sent_date = models.DateField(
        null=True, blank=True, help_text="Dedupes push sends within the same day across cron ticks."
    )
    last_evening_quote_sent_date = models.DateField(null=True, blank=True)

    affirmations_enabled = models.BooleanField(
        default=False, help_text="Master opt-in for daily self-affirmations (desktop display and/or mobile push)."
    )
    affirmation_morning_enabled = models.BooleanField(default=False)
    affirmation_morning_time = models.TimeField(default=time(7, 0))
    affirmation_evening_enabled = models.BooleanField(default=False)
    affirmation_evening_time = models.TimeField(default=time(20, 0))
    last_morning_affirmation_sent_date = models.DateField(
        null=True, blank=True, help_text="Dedupes push sends within the same day across cron ticks."
    )
    last_evening_affirmation_sent_date = models.DateField(null=True, blank=True)

    checkin_reminder_enabled = models.BooleanField(
        default=False, help_text="Master opt-in for a daily push reminder to check in."
    )
    checkin_reminder_morning_enabled = models.BooleanField(default=False)
    checkin_reminder_morning_time = models.TimeField(default=time(9, 0))
    checkin_reminder_evening_enabled = models.BooleanField(default=False)
    checkin_reminder_evening_time = models.TimeField(default=time(20, 0))
    last_morning_checkin_reminder_sent_date = models.DateField(
        null=True, blank=True, help_text="Dedupes push sends within the same day across cron ticks."
    )
    last_evening_checkin_reminder_sent_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def age(self):
        today = timezone.localdate()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class PushSubscription(models.Model):
    """One browser/device's Web Push subscription, from the PWA's push opt-in on the account page.

    A user can have more than one (phone + tablet, etc.) - each is delivered to independently.
    Pruned automatically (see entries.push.send_to_subscription) when the push service reports
    the endpoint as expired/invalid.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.endpoint[:60]}"


class AccessRequest(models.Model):
    """A pending request to create an account, awaiting admin approval by email link.

    Holds the same data `SignupForm`/`Profile` would need, plus an already-hashed
    password (never plaintext) captured at request time. On approval, a real `User`
    + `Profile` is created from these fields; on rejection, the row is just marked
    decided and no account is ever created.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    username = models.CharField(max_length=150)
    password_hash = models.CharField(max_length=255)
    name = models.CharField(max_length=150)
    email = models.EmailField()
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, choices=Profile.GENDER_CHOICES)
    gender_self_description = models.CharField(max_length=100, blank=True)
    zipcode = models.CharField(max_length=10)
    created_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.username} ({self.get_status_display()})"


class MomentCheckIn(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="moment_checkins")
    created_at = models.DateTimeField(default=timezone.now)
    emotions = models.CharField(max_length=300, blank=True, help_text="Comma-separated emotion tags.")
    note = EncryptedTextField(blank=True, help_text="What are you feeling, and why?")
    entry = models.ForeignKey(Entry, related_name="moments", null=True, blank=True, on_delete=models.SET_NULL)

    # Optional "Five Whys" deep dive, offered as an extra step past the initial note -
    # each answer meant to dig past the previous one toward the root cause.
    deep_dive_why_1 = EncryptedTextField(blank=True)
    deep_dive_why_2 = EncryptedTextField(blank=True)
    deep_dive_why_3 = EncryptedTextField(blank=True)
    deep_dive_why_4 = EncryptedTextField(blank=True)
    deep_dive_why_5 = EncryptedTextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def emotion_list(self):
        return [e for e in self.emotions.split(",") if e]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {self.emotions}"


class Feedback(models.Model):
    CATEGORY_CHOICES = [
        ("bug", "Bug report"),
        ("feature", "Feature request"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("new", "New"),
        ("reviewed", "Reviewed"),
        ("resolved", "Resolved"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback_messages")
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default="other")
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="new")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_category_display()} from {self.user} ({self.created_at:%Y-%m-%d})"


class Announcement(models.Model):
    """A "What's New" note shown as a popup after sign-in until a user dismisses it.

    Written for a non-technical reader: short, plain-language title and description,
    plus an optional pointer to where in the app to find the change.
    """

    CATEGORY_CHOICES = [
        ("feature", "New feature"),
        ("fix", "Bug fix"),
        ("improvement", "Improvement"),
    ]

    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default="feature")
    title = models.CharField(max_length=150, help_text="Short plain-language headline, e.g. 'Dictation now works on Safari'.")
    description = models.TextField(help_text="1-2 short sentences in plain language, no technical jargon.")
    location = models.CharField(
        max_length=150,
        blank=True,
        help_text="Where to find it, e.g. 'Morning Check-in'. Leave blank for bug fixes with nothing new to find.",
    )
    is_active = models.BooleanField(default=True, help_text="Uncheck to stop showing this in the popup.")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.title}"


class AnnouncementGenState(models.Model):
    """Singleton row tracking the last commit SHA the generate_announcements command
    processed. Lives in the database (not a local file) so state is correct no matter
    where the command runs - locally or from a CI job - since both talk to the same
    production database."""

    last_sha = models.CharField(max_length=40, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Announcement generation state (last_sha={self.last_sha[:8] or 'none'})"


class LoginCount(models.Model):
    """Tracks how many times each user has signed in, shown as a column on the admin User list.

    Kept as its own model (rather than a field on `Profile`) so it applies to every
    `User`, including ones with no `Profile` row (e.g. accounts made via `createsuperuser`).
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_count")
    count = models.PositiveIntegerField(default=0)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(
        null=True, blank=True, help_text="Last authenticated request seen from this user, updated on any page view (not just sign-in). Powers the admin 'active now' view."
    )

    def __str__(self):
        return f"{self.user}: {self.count}"


class FeatureUsageEvent(models.Model):
    """One row per (user, feature, day) a feature was touched — deduped server-side so repeat
    page loads in the same day don't inflate counts. Powers the admin activity dashboard.
    Deliberately records only *which feature*, never any journal content.
    """

    FEATURE_CHOICES = [
        ("checkin_morning", "Morning Check-in"),
        ("checkin_evening", "Evening Check-in"),
        ("checkin_moment", "Moment Check-in"),
        ("calendar", "Calendar"),
        ("journals_hub", "Journals Hub"),
        ("journal_stoic", "Journals: Stoic"),
        ("journal_devotional", "Journals: Devotional"),
        ("journal_freeform", "Journals: Freeform"),
        ("journal_introspection", "Journals: Introspection"),
        ("entry_create", "New Entry"),
        ("entry_edit", "Edit Entry"),
        ("entry_detail", "View Entry"),
        ("export", "Export"),
        ("account", "Account"),
        ("feedback", "Feedback"),
        ("survey", "Survey"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feature_usage_events")
    feature = models.CharField(max_length=30, choices=FEATURE_CHOICES)
    date = models.DateField(default=timezone.localdate)

    class Meta:
        unique_together = ("user", "feature", "date")
        indexes = [models.Index(fields=["feature", "date"])]

    def __str__(self):
        return f"{self.user}: {self.get_feature_display()} on {self.date}"


SURVEY_ELIGIBLE_ACCOUNT_AGE_DAYS = 14
SURVEY_DECLINE_COOLDOWN_DAYS = 90

RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]
YES_NO_CHOICES = [("yes", "Yes"), ("no", "No")]


class SurveyResponse(models.Model):
    """One user's answers to the one-time site-feedback survey, first offered on day 14
    after signup (see SURVEY_ELIGIBLE_ACCOUNT_AGE_DAYS) via entries.context_processors.
    A decline re-arms the prompt after SURVEY_DECLINE_COOLDOWN_DAYS; a completion is final.
    """

    SECTION_CHOICES = [
        ("checkin_morning", "Morning Check-in"),
        ("checkin_evening", "Evening Check-in"),
        ("stoic", "Stoic Journal"),
        ("devotional", "Devotional"),
        ("freeform", "Freeform Journal"),
        ("introspection", "Introspection"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="survey_response")
    declined_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    overall_rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES, null=True, blank=True,
        help_text="1. Overall, how satisfied are you with The Wax Tablet so far?",
    )
    most_used_section = models.CharField(
        max_length=20, choices=SECTION_CHOICES, blank=True, help_text="2. Which section do you use most?"
    )
    least_used_section = models.CharField(
        max_length=20, choices=SECTION_CHOICES, blank=True, help_text="2. Which section do you use least?"
    )
    feature_request = models.TextField(
        blank=True, help_text="3. If you could add or expand one feature, what would it be?"
    )
    friction_feedback = models.TextField(
        blank=True, help_text="4. Has anything been confusing, slow, or frustrating to use?"
    )
    reported_bug = models.CharField(
        max_length=3, choices=YES_NO_CHOICES, blank=True,
        help_text="5. Have you reported any bugs or glitches while using the app?",
    )
    bug_response_time_rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES, null=True, blank=True,
        help_text="6. How satisfied were you with how quickly it was addressed? (shown if Q5 is yes)",
    )
    appearance_rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES, null=True, blank=True, help_text="7. What do you think of the app's look and feel?"
    )
    appearance_change = models.TextField(
        blank=True, help_text="8. What would you change about the appearance?"
    )
    content_helpful = models.CharField(
        max_length=3, choices=YES_NO_CHOICES, blank=True, help_text="9. Did you find the content helpful?"
    )
    favorite_part = models.TextField(
        blank=True, help_text="10. What was your favorite part? (shown if Q9 is yes)"
    )
    disliked_part = models.TextField(
        blank=True, help_text="11. What did you not enjoy or use and why? (shown if Q9 is no)"
    )

    def __str__(self):
        return f"Survey response: {self.user}"


def _generate_invite_code():
    return get_random_string(8, allowed_chars="ABCDEFGHJKMNPQRSTUVWXYZ23456789")


class Community(models.Model):
    """A named group of users, joined by sharing an invite code (private, not a public directory)."""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    invite_code = models.CharField(max_length=8, unique=True, default=_generate_invite_code, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="communities_created"
    )
    created_at = models.DateTimeField(default=timezone.now)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="CommunityMembership", related_name="communities"
    )

    prayer_digest_time = models.TimeField(
        default=time(20, 0),
        help_text="Daily time (set by the community admin) that pending prayer requests are bundled into one digest email.",
    )
    last_prayer_digest_sent_date = models.DateField(
        null=True, blank=True, help_text="Dedupes digest sends within the same day across cron ticks."
    )

    admin_agreement_accepted_at = models.DateTimeField(
        null=True, blank=True, help_text="When the creator accepted the Community Admin Agreement to create this community."
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "communities"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("entries:community-detail", args=[self.pk])

    def is_admin(self, user):
        return user.pk == self.created_by_id


class CommunityMembership(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved - invite code sent, awaiting entry"),
        ("active", "Active"),
    ]

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_memberships")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    joined_at = models.DateTimeField(default=timezone.now)
    user_agreement_accepted_at = models.DateTimeField(
        null=True, blank=True, help_text="When this member accepted the Community User Agreement to request joining."
    )

    class Meta:
        unique_together = ("community", "user")
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user} in {self.community} ({self.status})"


class PrayerRequest(models.Model):
    """A community prayer request/concern, submitted as either "immediate" (triggers an
    instant email + push to the community right away) or "scheduled" (held until the
    community's next daily digest). Immediate requests are *also* rolled into that day's
    digest alongside scheduled ones - see entries.prayer.send_due_prayer_digests(). Rows are
    purged 30 minutes after their digest_sent_at (entries.prayer.purge_expired_prayer_requests()),
    so this table only ever holds same-day, not-yet-digested-long-ago data.
    """

    REQUEST_TYPE_CHOICES = [
        ("immediate", "Immediate"),
        ("scheduled", "Scheduled"),
    ]

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="prayer_requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="prayer_requests")
    request_type = models.CharField(max_length=10, choices=REQUEST_TYPE_CHOICES)
    text = EncryptedTextField()
    is_anonymous = models.BooleanField(
        default=False, help_text="Hides the requester's name in the community listing and in emails."
    )
    created_at = models.DateTimeField(default=timezone.now)
    immediate_sent_at = models.DateTimeField(
        null=True, blank=True, help_text="When the instant email/push went out, for an immediate request."
    )
    digest_sent_at = models.DateTimeField(
        null=True, blank=True, help_text="When this request was included in the community's daily digest email."
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_request_type_display()} prayer request from {self.user} in {self.community}"

    @property
    def display_name(self):
        return "Anonymous" if self.is_anonymous else self.user.username
