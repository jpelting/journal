import json
from pathlib import Path

from django.core.management.base import BaseCommand

from entries.models import StoicPrompt

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "stoic_prompts.json"


class Command(BaseCommand):
    help = "Load StoicPrompt rows from entries/data/stoic_prompts.json (idempotent)."

    def handle(self, *args, **options):
        prompts = json.loads(DATA_FILE.read_text(encoding="utf-8"))

        created = 0
        for prompt in prompts:
            _, was_created = StoicPrompt.objects.get_or_create(
                text=prompt["text"],
                defaults={"source": prompt.get("source", "")},
            )
            if was_created:
                created += 1

        total = len(prompts)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new prompt(s); {total} total in fixture; "
                f"{StoicPrompt.objects.count()} now in database."
            )
        )
