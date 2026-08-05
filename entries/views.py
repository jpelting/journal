import calendar
from datetime import date

from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import EntryForm
from .models import DevotionalPrompt, Entry, StoicPrompt


class EntryListView(ListView):
    model = Entry
    context_object_name = "entries"
    paginate_by = 30


class EntryDetailView(DetailView):
    model = Entry
    context_object_name = "entry"


class EntryFormMixin:
    model = Entry
    form_class = EntryForm
    template_name = "entries/entry_form.html"


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
