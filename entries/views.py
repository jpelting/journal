import calendar
from datetime import date

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    EntryForm,
    EveningCheckInForm,
    GoalCompletionFormSet,
    GoalFormSet,
    MomentCheckInForm,
    MorningCheckInForm,
)
from .models import DevotionalPrompt, Entry, MomentCheckIn, StoicPrompt
from .weather import get_current_weather


class EntryListView(ListView):
    model = Entry
    context_object_name = "entries"
    paginate_by = 30


class EntryDetailView(DetailView):
    model = Entry
    context_object_name = "entry"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bible_attribution"] = settings.BIBLE_VERSION_ATTRIBUTION
        return context


def _resolve_prompt(form, field_name, model):
    pk = form[field_name].value()
    return model.objects.filter(pk=pk).first() if pk else None


class EntryFormMixin:
    model = Entry
    form_class = EntryForm
    template_name = "entries/entry_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stoic_prompt_obj"] = _resolve_prompt(context["form"], "stoic_prompt", StoicPrompt)
        context["devotional_prompt_obj"] = _resolve_prompt(context["form"], "devotional_prompt", DevotionalPrompt)
        context["bible_attribution"] = settings.BIBLE_VERSION_ATTRIBUTION
        return context


class EntryCreateView(EntryFormMixin, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        initial["date"] = self.request.GET.get("date") or timezone.localdate()
        stoic = self._next_stoic_prompt()
        devotional = DevotionalPrompt.objects.filter(active=True).order_by("?").first()
        if stoic:
            initial["stoic_prompt"] = stoic
        if devotional:
            initial["devotional_prompt"] = devotional
        return initial

    def _next_stoic_prompt(self):
        active = StoicPrompt.objects.filter(active=True)
        used_ids = Entry.objects.exclude(stoic_prompt__isnull=True).values_list("stoic_prompt_id", flat=True)
        unused = active.exclude(id__in=used_ids)
        # Once every active prompt has appeared in some entry, the cycle resets.
        pool = unused if unused.exists() else active
        return pool.order_by("?").first()


class EntryUpdateView(EntryFormMixin, UpdateView):
    pass


WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _mood_color(entry):
    scores = [s for s in (entry.mental_score, entry.physical_score, entry.emotional_score) if s is not None]
    if not scores:
        return None
    avg = sum(scores) / len(scores)
    hue = 10 + (avg - 1) / 9 * 100  # 1 -> reddish, 10 -> greenish
    return f"hsl({hue:.0f}, 45%, 85%)"


def calendar_view(request, year=None, month=None):
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    entries_by_day = {
        entry.date.day: entry
        for entry in Entry.objects.filter(date__year=year, date__month=month)
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


def _today_entry():
    entry, _ = Entry.objects.get_or_create(date=timezone.localdate())
    return entry


def checkin_view(request):
    return redirect("entries:checkin-morning")


def checkin_morning_view(request):
    entry = _today_entry()
    if not entry.weather_summary:
        summary = get_current_weather()
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
            "now": timezone.localtime(),
            "weather_location": settings.WEATHER_LOCATION_NAME,
        },
    )


def checkin_evening_view(request):
    entry = _today_entry()

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
            "now": timezone.localtime(),
        },
    )


def checkin_moment_view(request):
    if request.method == "POST":
        form = MomentCheckInForm(request.POST)
        if form.is_valid():
            MomentCheckIn.objects.create(
                emotions=",".join(form.cleaned_data["emotions"]),
                note=form.cleaned_data["note"],
                entry=Entry.objects.filter(date=timezone.localdate()).first(),
            )
            return redirect("entries:checkin-moment")
    else:
        form = MomentCheckInForm()

    return render(
        request,
        "entries/checkin_moment.html",
        {
            "form": form,
            "recent_moments": MomentCheckIn.objects.all()[:10],
            "now": timezone.localtime(),
        },
    )
