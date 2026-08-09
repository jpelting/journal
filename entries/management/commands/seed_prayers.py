import json
from pathlib import Path

from django.core.management.base import BaseCommand

from entries.models import Prayer

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "prayers.json"


class Command(BaseCommand):
    help = (
        "Load Prayer rows (one per calendar day, from 'God's Minute') "
        "from entries/data/prayers.json (idempotent)."
    )

    def handle(self, *args, **options):
        prayers = json.loads(DATA_FILE.read_text(encoding="utf-8"))

        created = 0
        updated = 0
        for prayer in prayers:
            _, was_created = Prayer.objects.update_or_create(
                month=prayer["month"],
                day=prayer["day"],
                defaults={
                    "reference": prayer.get("reference", ""),
                    "occasion": prayer.get("occasion", ""),
                    "quote": prayer.get("quote", ""),
                    "body": prayer["body"],
                    "attribution": prayer.get("attribution", ""),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        total = len(prayers)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new, updated {updated} existing; "
                f"{total} total in fixture; {Prayer.objects.count()} now in database."
            )
        )
