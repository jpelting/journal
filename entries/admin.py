from django.contrib import admin

from .bible import get_passage_text
from .models import (
    DevotionalPrompt,
    Entry,
    Goal,
    IntrospectionPrompt,
    MomentCheckIn,
    Prayer,
    StoicPractice,
    StoicPrompt,
)


class GoalInline(admin.TabularInline):
    model = Goal
    extra = 0


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "user",
        "mental_score",
        "physical_score",
        "emotional_score",
        "spiritual_score",
    ]
    list_filter = ["user"]
    date_hierarchy = "date"
    ordering = ["-date"]
    inlines = [GoalInline]
    readonly_fields = ["introspection_question", "stoic_practice_display"]

    def introspection_question(self, obj):
        prompt = obj.introspection_prompt if obj.pk else None
        return prompt.question if prompt else "—"

    introspection_question.short_description = "Question for this day"

    def stoic_practice_display(self, obj):
        practice = obj.stoic_practice if obj.pk else None
        return f"Week {practice.week_number}: {practice.title}" if practice else "—"

    stoic_practice_display.short_description = "This week's Stoic practice"

    fieldsets = [
        ("Entry", {"fields": ["user", "date"]}),
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
            "1b. Stoic daily reflection",
            {
                "fields": [
                    "stoic_practice_display",
                    "morning_anxious_about",
                    "morning_within_control",
                    "morning_reserve_clause",
                    "evening_did_well",
                    "evening_where_falter",
                    "evening_could_improve",
                    "evening_gratitude_audit",
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
            "5. Introspection",
            {"fields": ["introspection_question", "introspection_response"]},
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


@admin.register(IntrospectionPrompt)
class IntrospectionPromptAdmin(admin.ModelAdmin):
    list_display = ["day_of_year", "__str__"]
    ordering = ["day_of_year"]


@admin.register(Prayer)
class PrayerAdmin(admin.ModelAdmin):
    list_display = ["month", "day", "reference", "occasion"]
    ordering = ["month", "day"]


@admin.register(StoicPractice)
class StoicPracticeAdmin(admin.ModelAdmin):
    list_display = ["week_number", "part", "title"]
    ordering = ["week_number"]


@admin.register(MomentCheckIn)
class MomentCheckInAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "emotions", "entry"]
    list_filter = ["user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
