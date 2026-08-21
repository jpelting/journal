from django.core.management.base import BaseCommand

from entries.push import send_due_notifications


class Command(BaseCommand):
    help = (
        "Send any morning/evening motivational-quote push notifications that are due right "
        "now, for every opted-in user. Meant to be hit on a short interval by an external "
        "scheduler (see the /internal/send-due-quote-notifications/ view this backs); safe to "
        "run locally for testing."
    )

    def handle(self, *args, **options):
        sent = send_due_notifications()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} quote notification(s)."))
