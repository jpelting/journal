import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from entries.models import StoicPractice

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "stoic_practices.json"


class Command(BaseCommand):
    help = (
        "Load StoicPractice rows (52 weekly practices, one per ISO week) "
        "from entries/data/stoic_practices.json (idempotent)."
    )

    def handle(self, *args, **options):
        practices = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if len(practices) != 52:
            raise CommandError(f"Expected 52 practices, found {len(practices)}.")

        created = 0
        updated = 0
        for practice in practices:
            _, was_created = StoicPractice.objects.update_or_create(
                week_number=practice["week_number"],
                defaults={
                    "part": practice.get("part", ""),
                    "title": practice["title"],
                    "description": practice["description"],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new, updated {updated} existing; "
                f"{StoicPractice.objects.count()} now in database."
            )
        )
