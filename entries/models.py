from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

SCORE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(10)]


class StoicPrompt(models.Model):
    text = models.TextField(help_text="A stoic reflection prompt, e.g. quoting Marcus Aurelius, Seneca, Epictetus.")
    source = models.CharField(max_length=200, blank=True, help_text="Optional attribution, e.g. 'Meditations, Book 4'.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.text[:60]


class DevotionalPrompt(models.Model):
    reference = models.CharField(max_length=100, help_text="Scripture reference, e.g. 'Philippians 4:6-7'.")
    verse_text = models.TextField(blank=True, help_text="The passage text, if you want it displayed.")
    reflection_prompt = models.TextField(help_text="A guiding question for the devotional reflection.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.reference


class Entry(models.Model):
    date = models.DateField(default=timezone.localdate, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Part 1: check-in
    mental_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    physical_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    emotional_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    spiritual_score = models.PositiveSmallIntegerField(validators=SCORE_VALIDATORS, null=True, blank=True)
    checkin_notes = models.TextField(blank=True)

    # Part 2: stoic guided journal
    stoic_prompt = models.ForeignKey(StoicPrompt, null=True, blank=True, on_delete=models.SET_NULL)
    stoic_response = models.TextField(blank=True)

    # Part 3: biblical devotional
    devotional_prompt = models.ForeignKey(DevotionalPrompt, null=True, blank=True, on_delete=models.SET_NULL)
    devotional_response = models.TextField(blank=True)

    # Part 4: freeform journal
    freeform_entry = models.TextField(blank=True)

    # Part 5: exercise
    exercise_completed = models.BooleanField(default=False)
    exercise_type = models.CharField(max_length=100, blank=True)
    exercise_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    exercise_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "entries"

    def __str__(self):
        return self.date.isoformat()

    def get_absolute_url(self):
        return reverse("entries:detail", args=[self.pk])
