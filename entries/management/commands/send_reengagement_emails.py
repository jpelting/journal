from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from entries.reengagement import send_due_reengagement_emails


class Command(BaseCommand):
    help = (
        "Email any opted-in user who's gone 5+ days without a page view a warm 'come back' "
        "nudge. Meant to be hit on the same tick as /internal/send-due-quote-notifications/ "
        "by an external scheduler; safe to run locally for testing."
    )

    def handle(self, *args, **options):
        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "localhost:8000"
        scheme = "http" if settings.DEBUG else "https"
        login_url = f"{scheme}://{host}{reverse('login')}"
        sent = send_due_reengagement_emails(login_url)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reengagement email(s)."))
