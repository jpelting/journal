import json
from pathlib import Path

from django.core.management.base import BaseCommand

from entries.models import SelfAffirmation

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "self_affirmations.json"


class Command(BaseCommand):
    help = (
        "Load SelfAffirmation rows (one morning + one evening per day of year) "
        "from entries/data/self_affirmations.json (idempotent)."
    )

    def handle(self, *args, **options):
        affirmations = json.loads(DATA_FILE.read_text(encoding="utf-8"))

        created = 0
        updated = 0
        for affirmation in affirmations:
            _, was_created = SelfAffirmation.objects.update_or_create(
                day_of_year=affirmation["day_of_year"],
                slot=affirmation["slot"],
                defaults={"text": affirmation["text"]},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        total = len(affirmations)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new, updated {updated} existing; "
                f"{total} total in fixture; {SelfAffirmation.objects.count()} now in database."
            )
        )
