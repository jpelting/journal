import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from entries.models import IntrospectionPrompt

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "introspection_prompts.json"


class Command(BaseCommand):
    help = (
        "Load IntrospectionPrompt rows (365 questions, one per day-of-year) "
        "from entries/data/introspection_prompts.json (idempotent)."
    )

    def handle(self, *args, **options):
        questions = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if len(questions) != 365:
            raise CommandError(f"Expected 365 questions, found {len(questions)}.")

        created = 0
        updated = 0
        for day, question in enumerate(questions, start=1):
            _, was_created = IntrospectionPrompt.objects.update_or_create(
                day_of_year=day,
                defaults={"question": question},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new, updated {updated} existing; "
                f"{IntrospectionPrompt.objects.count()} now in database."
            )
        )
