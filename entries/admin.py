from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User

from .bible import get_passage_text
from .models import (
    AccessRequest,
    Announcement,
    DevotionalPrompt,
    Entry,
    Feedback,
    Goal,
    IntrospectionPrompt,
    MomentCheckIn,
    Prayer,
    Profile,
    StoicPractice,
    StoicPrompt,
    SurveyResponse,
)


class GoalInline(admin.TabularInline):
    model = Goal
    extra = 0


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    list_display = DefaultUserAdmin.list_display + ("login_count_display",)

    def login_count_display(self, obj):
        login_count = getattr(obj, "login_count", None)
        return login_count.count if login_count else 0

    login_count_display.short_description = "Sign-ins"
    login_count_display.admin_order_field = "login_count__count"


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


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "age", "gender", "zipcode"]


@admin.register(MomentCheckIn)
class MomentCheckInAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "emotions", "entry"]
    list_filter = ["user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ["username", "email", "status", "created_at", "decided_at"]
    list_filter = ["status"]
    readonly_fields = ["password_hash", "token", "created_at"]
    ordering = ["-created_at"]


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "is_active", "created_at"]
    list_filter = ["category", "is_active"]
    list_editable = ["is_active"]
    ordering = ["-created_at"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ["user", "category", "status", "created_at"]
    list_display_links = ["user"]
    list_editable = ["status"]
    list_filter = ["category", "status"]
    readonly_fields = ["user", "category", "message", "created_at"]
    ordering = ["-created_at"]


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ["user", "overall_rating", "appearance_rating", "content_helpful", "declined_at", "completed_at"]
    list_filter = ["overall_rating", "content_helpful", "reported_bug"]
    readonly_fields = [field.name for field in SurveyResponse._meta.fields]
    ordering = ["-completed_at"]
