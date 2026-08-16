import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

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
    context_summary = models.TextField(blank=True, help_text="Brief context/meaning summary shown under the verse text.")
    reflection_prompt = models.TextField(help_text="A guiding question for the devotional reflection.")
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

    def __str__(self):
        return self.name

    @property
    def age(self):
        today = timezone.localdate()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


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
