import calendar
from datetime import date
from io import BytesIO
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_not_required
from django.core.mail import send_mail
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from xhtml2pdf import pisa

from .context_processors import SESSION_KEY as ANNOUNCEMENT_SESSION_KEY
from .forms import (
    AccessRequestForm,
    AccountProfileForm,
    AccountUserForm,
    EntryForm,
    EveningCheckInForm,
    FeedbackForm,
    GoalCompletionFormSet,
    GoalFormSet,
    MomentCheckInForm,
    MorningCheckInForm,
    SurveyForm,
)
from .models import (
    AccessRequest,
    DevotionalPrompt,
    Entry,
    Feedback,
    IntrospectionPrompt,
    MomentCheckIn,
    Prayer,
    Profile,
    StoicPrompt,
    SurveyResponse,
)
from .weather import (
    get_current_weather,
    get_tomorrow_forecast,
    weather_animation_for_summary,
    weather_location_for_user,
)

JOURNAL_TYPES = {
    "stoic": {"label": "Stoic Reflections", "description": "Guided reflections on Stoic quotes and prompts."},
    "devotional": {"label": "Devotionals", "description": "Scripture-based devotional responses."},
    "freeform": {"label": "Freeform Journal", "description": "Open-ended daily journal entries."},
    "introspection": {"label": "Introspection", "description": "A daily reflection question, one for each day of the year."},
}


@login_not_required
def request_access_view(request):
    if request.method == "POST":
        form = AccessRequestForm(request.POST)
        if form.is_valid():
            access_request = form.save()
            _notify_admin_of_access_request(request, access_request)
            return render(request, "entries/request_access_sent.html")
    else:
        form = AccessRequestForm()
    response = render(request, "entries/request_access.html", {"form": form})
    # This is often filled out on a shared/family device - stop the browser's back/forward
    # cache from restoring a stale copy with the previous person's data still in the fields.
    response["Cache-Control"] = "no-store"
    return response


def _notify_admin_of_access_request(request, access_request):
    context = {
        "access_request": access_request,
        "approve_url": request.build_absolute_uri(
            reverse("access-request-approve", kwargs={"token": access_request.token})
        ),
        "reject_url": request.build_absolute_uri(
            reverse("access-request-reject", kwargs={"token": access_request.token})
        ),
    }
    subject = render_to_string("entries/access_request_admin_subject.txt", context).strip()
    body = render_to_string("entries/access_request_admin_email.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [settings.ADMIN_EMAIL])


@login_not_required
def access_request_approve_view(request, token):
    access_request = get_object_or_404(AccessRequest, token=token)
    if access_request.status == "pending":
        User = get_user_model()
        user = User.objects.create(
            username=access_request.username,
            email=access_request.email,
            password=access_request.password_hash,
            is_active=True,
        )
        Profile.objects.create(
            user=user,
            name=access_request.name,
            date_of_birth=access_request.date_of_birth,
            gender=access_request.gender,
            gender_self_description=access_request.gender_self_description,
            zipcode=access_request.zipcode,
        )
        access_request.status = "approved"
        access_request.decided_at = timezone.now()
        access_request.save()

        context = {"access_request": access_request, "login_url": request.build_absolute_uri(reverse("login"))}
        subject = render_to_string("entries/access_request_approved_subject.txt", context).strip()
        body = render_to_string("entries/access_request_approved_email.txt", context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [access_request.email])

    return render(request, "entries/access_request_outcome.html", {"access_request": access_request, "action": "approved"})


@login_not_required
def access_request_reject_view(request, token):
    access_request = get_object_or_404(AccessRequest, token=token)
    if access_request.status == "pending":
        access_request.status = "rejected"
        access_request.decided_at = timezone.now()
        access_request.save()

        context = {"access_request": access_request}
        subject = render_to_string("entries/access_request_rejected_subject.txt", context).strip()
        body = render_to_string("entries/access_request_rejected_email.txt", context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [access_request.email])

    return render(request, "entries/access_request_outcome.html", {"access_request": access_request, "action": "rejected"})


def account_view(request):
    profile = getattr(request.user, "profile", None) or Profile(user=request.user)
    if request.method == "POST":
        user_form = AccountUserForm(request.POST, instance=request.user)
        profile_form = AccountProfileForm(request.POST, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Your account has been updated.")
            return redirect("entries:account")
    else:
        user_form = AccountUserForm(instance=request.user)
        profile_form = AccountProfileForm(instance=profile)
    return render(request, "entries/account.html", {"user_form": user_form, "profile_form": profile_form})


def account_delete_view(request):
    if request.method == "POST":
        user = request.user
        auth_logout(request)
        user.delete()
        messages.success(request, "Your account and all its data have been deleted.")
        return redirect("login")
    return redirect("entries:account")


def dismiss_announcements_view(request):
    if request.method == "POST":
        now = timezone.now()
        profile = getattr(request.user, "profile", None)
        if profile:
            profile.last_seen_announcement_at = now
            profile.save(update_fields=["last_seen_announcement_at"])
        else:
            # No Profile to persist to (e.g. the original admin account) - fall back to
            # the session so dismissal still works instead of the popup reappearing forever.
            request.session[ANNOUNCEMENT_SESSION_KEY] = now.isoformat()

        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = reverse("entries:home")
        return redirect(next_url)
    return redirect("entries:home")


def survey_decline_view(request):
    if request.method == "POST":
        response, _ = SurveyResponse.objects.get_or_create(user=request.user)
        response.declined_at = timezone.now()
        response.save(update_fields=["declined_at"])

        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = reverse("entries:home")
        return redirect(next_url)
    return redirect("entries:home")


def survey_view(request):
    response, _ = SurveyResponse.objects.get_or_create(user=request.user)
    if response.completed_at:
        return render(request, "entries/survey.html", {"already_completed": True, "response": response})

    if request.method == "POST":
        form = SurveyForm(request.POST, instance=response)
        if form.is_valid():
            response = form.save(commit=False)
            response.completed_at = timezone.now()
            response.save()
            messages.success(request, "Thanks for taking the time — your feedback helps shape what's next.")
            return redirect("entries:home")
    else:
        form = SurveyForm(instance=response)
    return render(request, "entries/survey.html", {"form": form})


def feedback_view(request):
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.user = request.user
            feedback.save()
            _notify_admin_of_feedback(request, feedback)
            messages.success(request, "Thanks — your feedback has been sent.")
            return redirect("entries:feedback")
    else:
        form = FeedbackForm()
    return render(request, "entries/feedback.html", {"form": form})


def _notify_admin_of_feedback(request, feedback):
    context = {
        "feedback": feedback,
        "admin_url": request.build_absolute_uri(reverse("admin:entries_feedback_change", args=[feedback.pk])),
    }
    subject = render_to_string("entries/feedback_admin_subject.txt", context).strip()
    body = render_to_string("entries/feedback_admin_email.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [settings.ADMIN_EMAIL])


def _next_stoic_prompt(user):
    active = StoicPrompt.objects.filter(active=True)
    used_ids = Entry.objects.filter(user=user).exclude(stoic_prompt__isnull=True).values_list(
        "stoic_prompt_id", flat=True
    )
    unused = active.exclude(id__in=used_ids)
    # Once every active prompt has appeared in some entry of this user's, the cycle resets.
    pool = unused if unused.exists() else active
    return pool.order_by("?").first()


def _next_devotional_prompt(user=None):
    return DevotionalPrompt.objects.filter(active=True).order_by("?").first()


# journal_type -> (Entry FK field holding its prompt, function picking the next one)
_PROMPT_PICKERS = {
    "stoic": ("stoic_prompt", _next_stoic_prompt),
    "devotional": ("devotional_prompt", _next_devotional_prompt),
}


def _entries_for_journal_type(journal_type, user):
    """All of a user's entries, or entries with non-blank content for one JOURNAL_TYPES section."""
    entries = Entry.objects.filter(user=user)
    if journal_type == "stoic":
        return entries.exclude(stoic_response="")
    if journal_type == "devotional":
        return entries.exclude(devotional_response="")
    if journal_type == "freeform":
        return entries.exclude(freeform_entry="")
    if journal_type == "introspection":
        return entries.exclude(introspection_response="")
    return entries


class EntryListView(TemplateView):
    template_name = "entries/entry_list.html"
    extra_context = {"journal_types": JOURNAL_TYPES}


class JournalTypeListView(ListView):
    model = Entry
    context_object_name = "entries"
    paginate_by = 30
    template_name = "entries/journal_type_list.html"

    def get_queryset(self):
        journal_type = self.kwargs["journal_type"]
        if journal_type not in JOURNAL_TYPES:
            raise Http404
        return _entries_for_journal_type(journal_type, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal_type = self.kwargs["journal_type"]
        context["journal_type"] = journal_type
        context["journal_label"] = JOURNAL_TYPES[journal_type]["label"]
        today_entry = Entry.objects.filter(user=self.request.user, date=timezone.localdate()).first()
        if today_entry and journal_type in _PROMPT_PICKERS:
            field_name, pick_prompt = _PROMPT_PICKERS[journal_type]
            if getattr(today_entry, f"{field_name}_id") is None:
                prompt = pick_prompt(self.request.user)
                if prompt:
                    setattr(today_entry, field_name, prompt)
                    today_entry.save(update_fields=[field_name])

        if today_entry:
            context["new_entry_url"] = f"{reverse('entries:edit', args=[today_entry.pk])}?type={journal_type}"
        else:
            context["new_entry_url"] = f"{reverse('entries:create')}?type={journal_type}"
        return context


class EntryDetailView(DetailView):
    model = Entry
    context_object_name = "entry"

    def get_queryset(self):
        return Entry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bible_attribution"] = settings.BIBLE_VERSION_ATTRIBUTION
        return context


def _resolve_prompt(form, field_name, model):
    pk = form[field_name].value()
    return model.objects.filter(pk=pk).first() if pk else None


def _form_date(form):
    value = form["date"].value()
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value or timezone.localdate()


class EntryFormMixin:
    model = Entry
    form_class = EntryForm
    template_name = "entries/entry_form.html"

    def get_queryset(self):
        return Entry.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.user = self.request.user
        return form

    def _journal_type_param(self):
        value = self.request.GET.get("type") or self.request.POST.get("type")
        return value if value in JOURNAL_TYPES else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stoic_prompt_obj"] = _resolve_prompt(context["form"], "stoic_prompt", StoicPrompt)
        context["devotional_prompt_obj"] = _resolve_prompt(context["form"], "devotional_prompt", DevotionalPrompt)
        context["form_date"] = _form_date(context["form"])
        context["introspection_prompt_obj"] = IntrospectionPrompt.for_date(context["form_date"])
        context["bible_attribution"] = settings.BIBLE_VERSION_ATTRIBUTION
        context["form_journal_type"] = self._journal_type_param()
        context["active_section"] = context["form_journal_type"] or "stoic"
        return context


class EntryCreateView(EntryFormMixin, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        initial["date"] = self.request.GET.get("date") or timezone.localdate()
        stoic = _next_stoic_prompt(self.request.user)
        devotional = _next_devotional_prompt(self.request.user)
        if stoic:
            initial["stoic_prompt"] = stoic
        if devotional:
            initial["devotional_prompt"] = devotional
        return initial


class EntryUpdateView(EntryFormMixin, UpdateView):
    pass


WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


MOOD_BANDS = [
    (2, 0),    # red: 1-2
    (5, 32),   # orange: 3-5
    (7, 52),   # yellow: 6-7
    (10, 125),  # green: 8-10
]

# Saturation scales with how many of the 4 dimensions have data, so a day
# with one lonely score reads as a faint hint rather than a fully-confident color.
MOOD_MIN_SATURATION = 40
MOOD_MAX_SATURATION = 75
MOOD_LIGHTNESS = 78


def _mood_color(entry):
    dimension_scores = [
        entry.mental_score,
        entry.physical_score,
        entry.emotional_score,
        entry.spiritual_score,
    ]
    present = [s for s in dimension_scores if s is not None]
    if not present:
        return None
    avg = sum(present) / len(present)
    hue = next(hue for ceiling, hue in MOOD_BANDS if avg <= ceiling)
    saturation = MOOD_MIN_SATURATION + (MOOD_MAX_SATURATION - MOOD_MIN_SATURATION) * (
        len(present) - 1
    ) / (len(dimension_scores) - 1)
    return f"hsl({hue}, {saturation:.0f}%, {MOOD_LIGHTNESS}%)"


def calendar_view(request, year=None, month=None):
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    entries_by_day = {
        entry.date.day: entry
        for entry in Entry.objects.filter(user=request.user, date__year=year, date__month=month)
        .select_related("stoic_prompt", "devotional_prompt")
        .prefetch_related("goals")
    }

    weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):
        week_days = []
        for day in week:
            if day == 0:
                week_days.append(None)
                continue
            entry = entries_by_day.get(day)
            week_days.append(
                {
                    "day": day,
                    "date": date(year, month, day),
                    "entry": entry,
                    "is_today": date(year, month, day) == today,
                    "bg_color": _mood_color(entry) if entry else None,
                }
            )
        weeks.append(week_days)

    context = {
        "year": year,
        "month": month,
        "month_name": date(year, month, 1).strftime("%B"),
        "weeks": weeks,
        "weekday_labels": WEEKDAY_LABELS,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
    }
    return render(request, "entries/calendar.html", context)


def _today_entry(user):
    entry, _ = Entry.objects.get_or_create(user=user, date=timezone.localdate())
    return entry


def _checkin_availability(now):
    """Morning check-in runs 12:01am-12:00pm; evening follow-up is the complement
    (12:01pm-12:00am), so the two windows never overlap and never gap."""
    minutes_since_midnight = now.hour * 60 + now.minute
    morning_available = 1 <= minutes_since_midnight <= 12 * 60
    return morning_available, not morning_available


def _local_now(timezone_name):
    """The current time in a user's own timezone (resolved from their zip code),
    falling back to the server's local time if the zone name is ever unusable."""
    try:
        return timezone.now().astimezone(ZoneInfo(timezone_name))
    except Exception:
        return timezone.localtime()


def checkin_view(request):
    _, _, _, timezone_name = weather_location_for_user(request.user)
    morning_available, _ = _checkin_availability(_local_now(timezone_name))
    return redirect("entries:checkin-morning" if morning_available else "entries:checkin-evening")


def checkin_morning_view(request):
    latitude, longitude, location_name, timezone_name = weather_location_for_user(request.user)
    now = _local_now(timezone_name)
    morning_available, evening_available = _checkin_availability(now)
    if not morning_available:
        return redirect("entries:checkin-evening")

    entry = _today_entry(request.user)
    if not entry.weather_summary:
        summary = get_current_weather(latitude, longitude)
        if summary:
            entry.weather_summary = summary
            entry.save(update_fields=["weather_summary"])

    if request.method == "POST":
        form = MorningCheckInForm(request.POST, instance=entry)
        goal_formset = GoalFormSet(request.POST, instance=entry, prefix="goals")
        if form.is_valid() and goal_formset.is_valid():
            form.save()
            goal_formset.save()
            return redirect("entries:checkin-morning")
    else:
        form = MorningCheckInForm(instance=entry)
        goal_formset = GoalFormSet(instance=entry, prefix="goals")

    return render(
        request,
        "entries/checkin_morning.html",
        {
            "entry": entry,
            "form": form,
            "goal_formset": goal_formset,
            "goal_visible_count": max(entry.goals.count(), 1),
            "now": now,
            "morning_available": morning_available,
            "evening_available": evening_available,
            "weather_location": location_name,
            "weather_animation": weather_animation_for_summary(entry.weather_summary),
            "today_prayer": Prayer.for_date(timezone.localdate()),
        },
    )


def checkin_evening_view(request):
    latitude, longitude, location_name, timezone_name = weather_location_for_user(request.user)
    now = _local_now(timezone_name)
    morning_available, evening_available = _checkin_availability(now)
    if not evening_available:
        return redirect("entries:checkin-morning")

    entry = _today_entry(request.user)
    if not entry.forecast_summary:
        summary = get_tomorrow_forecast(latitude, longitude)
        if summary:
            entry.forecast_summary = summary
            entry.save(update_fields=["forecast_summary"])

    if request.method == "POST":
        form = EveningCheckInForm(request.POST, instance=entry)
        goal_formset = GoalCompletionFormSet(request.POST, instance=entry, prefix="goals")
        if form.is_valid() and goal_formset.is_valid():
            form.save()
            goal_formset.save()
            return redirect("entries:checkin-evening")
    else:
        form = EveningCheckInForm(instance=entry)
        goal_formset = GoalCompletionFormSet(instance=entry, prefix="goals")

    goals = list(entry.goals.all())
    completed = sum(1 for goal in goals if goal.completed)
    percent_complete = round(completed / len(goals) * 100) if goals else None

    return render(
        request,
        "entries/checkin_evening.html",
        {
            "entry": entry,
            "form": form,
            "goal_formset": goal_formset,
            "percent_complete": percent_complete,
            "now": now,
            "morning_available": morning_available,
            "evening_available": evening_available,
            "weather_location": location_name,
            "forecast_animation": weather_animation_for_summary(entry.forecast_summary),
            "today_prayer": Prayer.for_date(timezone.localdate()),
        },
    )


def checkin_moment_view(request):
    if request.method == "POST":
        form = MomentCheckInForm(request.POST)
        if form.is_valid():
            MomentCheckIn.objects.create(
                user=request.user,
                emotions=",".join(form.cleaned_data["emotions"]),
                note=form.cleaned_data["note"],
                entry=Entry.objects.filter(user=request.user, date=timezone.localdate()).first(),
            )
            return redirect("entries:checkin-moment")
    else:
        form = MomentCheckInForm()

    _, _, _, timezone_name = weather_location_for_user(request.user)
    now = _local_now(timezone_name)
    morning_available, evening_available = _checkin_availability(now)

    return render(
        request,
        "entries/checkin_moment.html",
        {
            "form": form,
            "recent_moments": MomentCheckIn.objects.filter(user=request.user)[:10],
            "now": now,
            "morning_available": morning_available,
            "evening_available": evening_available,
            "today_prayer": Prayer.for_date(timezone.localdate()),
        },
    )


def _clean_journal_type(value):
    return value if value in JOURNAL_TYPES else None


class EntryExportSelectView(ListView):
    model = Entry
    context_object_name = "entries"
    template_name = "entries/export_select.html"

    def get_queryset(self):
        return _entries_for_journal_type(_clean_journal_type(self.request.GET.get("type")), self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["journal_types"] = JOURNAL_TYPES
        context["selected_type"] = _clean_journal_type(self.request.GET.get("type")) or ""
        return context


def export_pdf_view(request):
    ids = request.POST.getlist("ids") or request.GET.getlist("ids")
    journal_type = _clean_journal_type(request.POST.get("type") or request.GET.get("type"))
    entries = Entry.objects.filter(user=request.user, pk__in=ids).order_by("date")

    if not entries.exists():
        messages.error(request, "No entries selected to export.")
        return redirect("entries:export")

    html = render_to_string(
        "entries/pdf_export.html",
        {
            "entries": entries,
            "bible_attribution": settings.BIBLE_VERSION_ATTRIBUTION,
            "journal_type": journal_type,
        },
    )

    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)

    start, end = entries.first().date, entries.last().date
    type_prefix = f"{journal_type}_" if journal_type else ""
    filename = (
        f"journal_{type_prefix}{start.isoformat()}.pdf"
        if start == end
        else f"journal_{type_prefix}{start.isoformat()}_to_{end.isoformat()}.pdf"
    )

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
