import calendar
from datetime import date
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from xhtml2pdf import pisa

from .forms import (
    EntryForm,
    EveningCheckInForm,
    GoalCompletionFormSet,
    GoalFormSet,
    MomentCheckInForm,
    MorningCheckInForm,
)
from .models import DevotionalPrompt, Entry, IntrospectionPrompt, MomentCheckIn, StoicPrompt
from .weather import get_current_weather, weather_animation_for_summary

JOURNAL_TYPES = {
    "stoic": {"label": "Stoic Reflections", "description": "Guided reflections on Stoic quotes and prompts."},
    "devotional": {"label": "Devotionals", "description": "Scripture-based devotional responses."},
    "freeform": {"label": "Freeform Journal", "description": "Open-ended daily journal entries."},
    "introspection": {"label": "Introspection", "description": "A daily reflection question, one for each day of the year."},
}


def _next_stoic_prompt():
    active = StoicPrompt.objects.filter(active=True)
    used_ids = Entry.objects.exclude(stoic_prompt__isnull=True).values_list("stoic_prompt_id", flat=True)
    unused = active.exclude(id__in=used_ids)
    # Once every active prompt has appeared in some entry, the cycle resets.
    pool = unused if unused.exists() else active
    return pool.order_by("?").first()


def _next_devotional_prompt():
    return DevotionalPrompt.objects.filter(active=True).order_by("?").first()


# journal_type -> (Entry FK field holding its prompt, function picking the next one)
_PROMPT_PICKERS = {
    "stoic": ("stoic_prompt", _next_stoic_prompt),
    "devotional": ("devotional_prompt", _next_devotional_prompt),
}


def _entries_for_journal_type(journal_type):
    """All entries, or entries with non-blank content for one JOURNAL_TYPES section."""
    if journal_type == "stoic":
        return Entry.objects.exclude(stoic_response="")
    if journal_type == "devotional":
        return Entry.objects.exclude(devotional_response="")
    if journal_type == "freeform":
        return Entry.objects.exclude(freeform_entry="")
    if journal_type == "introspection":
        return Entry.objects.exclude(introspection_response="")
    return Entry.objects.all()


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
        return _entries_for_journal_type(journal_type)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal_type = self.kwargs["journal_type"]
        context["journal_type"] = journal_type
        context["journal_label"] = JOURNAL_TYPES[journal_type]["label"]
        today_entry = Entry.objects.filter(date=timezone.localdate()).first()
        if today_entry and journal_type in _PROMPT_PICKERS:
            field_name, pick_prompt = _PROMPT_PICKERS[journal_type]
            if getattr(today_entry, f"{field_name}_id") is None:
                prompt = pick_prompt()
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

    def _journal_type_param(self):
        value = self.request.GET.get("type") or self.request.POST.get("type")
        return value if value in JOURNAL_TYPES else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stoic_prompt_obj"] = _resolve_prompt(context["form"], "stoic_prompt", StoicPrompt)
        context["devotional_prompt_obj"] = _resolve_prompt(context["form"], "devotional_prompt", DevotionalPrompt)
        context["introspection_prompt_obj"] = IntrospectionPrompt.for_date(_form_date(context["form"]))
        context["bible_attribution"] = settings.BIBLE_VERSION_ATTRIBUTION
        context["form_journal_type"] = self._journal_type_param()
        context["active_section"] = context["form_journal_type"] or "stoic"
        return context


class EntryCreateView(EntryFormMixin, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        initial["date"] = self.request.GET.get("date") or timezone.localdate()
        stoic = _next_stoic_prompt()
        devotional = _next_devotional_prompt()
        if stoic:
            initial["stoic_prompt"] = stoic
        if devotional:
            initial["devotional_prompt"] = devotional
        return initial


class EntryUpdateView(EntryFormMixin, UpdateView):
    pass


WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


MOOD_BANDS = [
    (2, "hsl(10, 45%, 85%)"),   # red: 1-2
    (5, "hsl(30, 45%, 85%)"),   # orange: 3-5
    (7, "hsl(50, 45%, 85%)"),   # yellow: 6-7
    (10, "hsl(110, 45%, 85%)"),  # green: 8-10
]


def _mood_color(entry):
    scores = [
        entry.morning_mental_score,
        entry.evening_mental_score,
        entry.morning_physical_score,
        entry.evening_physical_score,
        entry.morning_emotional_score,
        entry.evening_emotional_score,
        entry.morning_spiritual_score,
        entry.evening_spiritual_score,
    ]
    present = [s for s in scores if s is not None]
    if not present:
        return None
    avg = sum(present) / len(present)
    for ceiling, color in MOOD_BANDS:
        if avg <= ceiling:
            return color
    return MOOD_BANDS[-1][1]


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
            "weather_animation": weather_animation_for_summary(entry.weather_summary),
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


def _clean_journal_type(value):
    return value if value in JOURNAL_TYPES else None


class EntryExportSelectView(ListView):
    model = Entry
    context_object_name = "entries"
    template_name = "entries/export_select.html"

    def get_queryset(self):
        return _entries_for_journal_type(_clean_journal_type(self.request.GET.get("type")))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["journal_types"] = JOURNAL_TYPES
        context["selected_type"] = _clean_journal_type(self.request.GET.get("type")) or ""
        return context


def export_pdf_view(request):
    ids = request.POST.getlist("ids") or request.GET.getlist("ids")
    journal_type = _clean_journal_type(request.POST.get("type") or request.GET.get("type"))
    entries = Entry.objects.filter(pk__in=ids).order_by("date")

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
