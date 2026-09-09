from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from entries.survey import send_due_survey_emails


class Command(BaseCommand):
    help = (
        "Email any eligible user (account 14+ days old, survey not yet emailed or completed) the "
        "one-time site-feedback survey. Meant to be hit on the same tick as "
        "/internal/send-due-quote-notifications/ by an external scheduler; safe to run locally for testing."
    )

    def handle(self, *args, **options):
        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "localhost:8000"
        scheme = "http" if settings.DEBUG else "https"
        survey_url = f"{scheme}://{host}{reverse('entries:survey')}"
        sent = send_due_survey_emails(survey_url)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} survey email(s)."))
