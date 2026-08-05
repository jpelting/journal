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
        initial["date"] = timezone.localdate()
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
