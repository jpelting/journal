from datetime import date, timedelta
from io import BytesIO

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.timesince import timesince
from xhtml2pdf import pisa

from .bible import get_passage_text
from .models import (
    AccessRequest,
    Announcement,
    DevotionalPrompt,
    Entry,
    FeatureUsageEvent,
    Feedback,
    Goal,
    IntrospectionPrompt,
    LoginCount,
    MomentCheckIn,
    Prayer,
    Profile,
    StoicPractice,
    StoicPrompt,
    SurveyResponse,
)
from .reports import build_usage_report, render_report_csv

ACTIVE_WINDOW_MINUTES = 5
DASHBOARD_WINDOW_DAYS = 30


class GoalInline(admin.TabularInline):
    model = Goal
    extra = 0


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    list_display = DefaultUserAdmin.list_display + ("login_count_display", "last_seen_display")

    def login_count_display(self, obj):
        login_count = getattr(obj, "login_count", None)
        return login_count.count if login_count else 0

    login_count_display.short_description = "Sign-ins"
    login_count_display.admin_order_field = "login_count__count"

    def last_seen_display(self, obj):
        login_count = getattr(obj, "login_count", None)
        if not login_count or not login_count.last_activity_at:
            return "—"
        if login_count.last_activity_at >= timezone.now() - timedelta(minutes=ACTIVE_WINDOW_MINUTES):
            return "🟢 active now"
        return f"{timesince(login_count.last_activity_at)} ago"

    last_seen_display.short_description = "Last seen"
    last_seen_display.admin_order_field = "login_count__last_activity_at"


def activity_dashboard_view(request):
    now = timezone.now()
    active_cutoff = now - timedelta(minutes=ACTIVE_WINDOW_MINUTES)
    window_start = timezone.localdate() - timedelta(days=DASHBOARD_WINDOW_DAYS - 1)

    login_counts = list(LoginCount.objects.select_related("user").order_by("-last_activity_at"))
    active_now = [lc for lc in login_counts if lc.last_activity_at and lc.last_activity_at >= active_cutoff]

    feature_totals = (
        FeatureUsageEvent.objects.filter(date__gte=window_start)
        .values("feature")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    feature_labels = dict(FeatureUsageEvent.FEATURE_CHOICES)
    max_feature_count = max((row["n"] for row in feature_totals), default=0)
    feature_bars = [
        {
            "label": feature_labels.get(row["feature"], row["feature"]),
            "count": row["n"],
            "pct": round(row["n"] / max_feature_count * 100) if max_feature_count else 0,
        }
        for row in feature_totals
    ]

    daily_active = (
        FeatureUsageEvent.objects.filter(date__gte=window_start)
        .values("date")
        .annotate(n=Count("user", distinct=True))
        .order_by("date")
    )
    daily_by_date = {row["date"]: row["n"] for row in daily_active}
    max_daily = max(daily_by_date.values(), default=0)
    daily_bars = [
        {
            "date": window_start + timedelta(days=i),
            "count": daily_by_date.get(window_start + timedelta(days=i), 0),
            "pct": round(daily_by_date.get(window_start + timedelta(days=i), 0) / max_daily * 100) if max_daily else 0,
        }
        for i in range(DASHBOARD_WINDOW_DAYS)
    ]

    context = {
        **admin.site.each_context(request),
        "title": "User Activity",
        "active_now": active_now,
        "active_window_minutes": ACTIVE_WINDOW_MINUTES,
        "login_counts": login_counts,
        "feature_bars": feature_bars,
        "daily_bars": daily_bars,
        "window_days": DASHBOARD_WINDOW_DAYS,
        "default_start": window_start,
        "default_end": timezone.localdate(),
    }
    return TemplateResponse(request, "admin/activity_dashboard.html", context)


def _parse_report_date(value, fallback):
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


def activity_report_view(request):
    today = timezone.localdate()
    start_date = _parse_report_date(request.GET.get("start"), today - timedelta(days=DASHBOARD_WINDOW_DAYS - 1))
    end_date = _parse_report_date(request.GET.get("end"), today)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    report_format = request.GET.get("format", "csv")

    report = build_usage_report(start_date, end_date)
    filename_base = f"wax_tablet_usage_report_{start_date}_{end_date}"

    if report_format == "pdf":
        html = render_to_string("admin/activity_report_pdf.html", {"report": report})
        buffer = BytesIO()
        pisa.CreatePDF(html, dest=buffer)
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename_base}.pdf"'
        return response

    response = HttpResponse(render_report_csv(report), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename_base}.csv"'
    return response


_original_get_urls = admin.site.get_urls


def _get_urls():
    custom_urls = [
        path("activity/", admin.site.admin_view(activity_dashboard_view), name="activity-dashboard"),
        path("activity/report/", admin.site.admin_view(activity_report_view), name="activity-report"),
    ]
    return custom_urls + _original_get_urls()


admin.site.get_urls = _get_urls


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
