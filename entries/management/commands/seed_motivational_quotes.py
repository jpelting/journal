import json
from pathlib import Path

from django.core.management.base import BaseCommand

from entries.models import MotivationalQuote

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "motivational_quotes.json"


class Command(BaseCommand):
    help = (
        "Load MotivationalQuote rows (one morning + one evening per day of year) "
        "from entries/data/motivational_quotes.json (idempotent)."
    )

    def handle(self, *args, **options):
        quotes = json.loads(DATA_FILE.read_text(encoding="utf-8"))

        created = 0
        updated = 0
        for quote in quotes:
            _, was_created = MotivationalQuote.objects.update_or_create(
                day_of_year=quote["day_of_year"],
                slot=quote["slot"],
                defaults={
                    "text": quote["text"],
                    "author": quote["author"],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        total = len(quotes)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new, updated {updated} existing; "
                f"{total} total in fixture; {MotivationalQuote.objects.count()} now in database."
            )
        )
