from django.contrib import admin

from .models import DevotionalPrompt, Entry, StoicPrompt


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

    fieldsets = [
        ("Entry", {"fields": ["date"]}),
        (
            "1. Check-in",
            {
                "fields": [
                    "mental_score",
                    "physical_score",
                    "emotional_score",
                    "spiritual_score",
                    "checkin_notes",
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
