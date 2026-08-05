from django.contrib import admin

from .bible import get_passage_text
from .models import DevotionalPrompt, Entry, Goal, MomentCheckIn, StoicPrompt


class GoalInline(admin.TabularInline):
    model = Goal
    extra = 0


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "mental_score",
        "physical_score",
        "emotional_score",
        "spiritual_score",
        "exercise_completed",
    ]
    list_filter = ["exercise_completed"]
    date_hierarchy = "date"
    ordering = ["-date"]
    inlines = [GoalInline]

    fieldsets = [
        ("Entry", {"fields": ["date"]}),
        (
            "1. Check-in",
            {
                "fields": [
                    "weather_summary",
                    "morning_mental_score",
                    "morning_physical_score",
                    "morning_emotional_score",
                    "morning_spiritual_score",
                    "one_percent_goal",
                    "evening_mental_score",
                    "evening_physical_score",
                    "evening_emotional_score",
                    "evening_spiritual_score",
                    "one_percent_goal_achieved",
                ]
            },
        ),
        (
            "2. Stoic guided journal",
            {"fields": ["stoic_prompt", "stoic_response"]},
        ),
        (
            "3. Biblical devotional",
            {"fields": ["devotional_prompt", "devotional_response"]},
        ),
        (
            "4. Freeform journal",
            {"fields": ["freeform_entry"]},
        ),
        (
            "5. Exercise",
            {
                "fields": [
                    "exercise_completed",
                    "exercise_type",
                    "exercise_duration_minutes",
                    "exercise_notes",
                ]
            },
        ),
    ]


@admin.register(StoicPrompt)
class StoicPromptAdmin(admin.ModelAdmin):
    list_display = ["__str__", "source", "active"]
    list_filter = ["active"]


@admin.register(DevotionalPrompt)
class DevotionalPromptAdmin(admin.ModelAdmin):
    list_display = ["reference", "active"]
    list_filter = ["active"]

    def save_model(self, request, obj, form, change):
        if not obj.verse_text and obj.reference:
            fetched = get_passage_text(obj.reference)
            if fetched:
                obj.verse_text = fetched
        super().save_model(request, obj, form, change)


@admin.register(MomentCheckIn)
class MomentCheckInAdmin(admin.ModelAdmin):
    list_display = ["created_at", "emotions", "entry"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
