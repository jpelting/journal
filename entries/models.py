from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

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


class Entry(models.Model):
    date = models.DateField(default=timezone.localdate, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Part 1: check-in
    weather_summary = models.CharField(max_length=200, blank=True, help_text="Cached weather snapshot from the morning check-in.")

    morning_mental_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    morning_physical_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    morning_emotional_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    morning_spiritual_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    one_percent_goal = models.TextField(blank=True, help_text="One small thing that would make today 1% better.")

    evening_mental_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    evening_physical_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    evening_emotional_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    evening_spiritual_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    one_percent_goal_achieved = models.BooleanField(default=False)

    # Part 2: stoic guided journal
    stoic_prompt = models.ForeignKey(StoicPrompt, null=True, blank=True, on_delete=models.SET_NULL)
    stoic_response = models.TextField(blank=True)

    # Part 3: biblical devotional
    devotional_prompt = models.ForeignKey(DevotionalPrompt, null=True, blank=True, on_delete=models.SET_NULL)
    devotional_response = models.TextField(blank=True)

    # Part 4: freeform journal
    freeform_entry = models.TextField(blank=True)

    # Part 5: introspection
    introspection_response = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "entries"

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


class Goal(models.Model):
    entry = models.ForeignKey(Entry, related_name="goals", on_delete=models.CASCADE)
    text = models.CharField(max_length=300)
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


class MomentCheckIn(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    emotions = models.CharField(max_length=300, blank=True, help_text="Comma-separated emotion tags.")
    note = models.TextField(blank=True, help_text="What are you feeling, and why?")
    entry = models.ForeignKey(Entry, related_name="moments", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def emotion_list(self):
        return [e for e in self.emotions.split(",") if e]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {self.emotions}"
