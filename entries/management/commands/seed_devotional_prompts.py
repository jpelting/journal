import json
from pathlib import Path

from django.core.management.base import BaseCommand

from entries.bible import get_passage_text
from entries.models import DevotionalPrompt

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "devotional_prompts.json"


class Command(BaseCommand):
    help = (
        "Load DevotionalPrompt rows from entries/data/devotional_prompts.json (idempotent). "
        "Verse text is fetched live from the YouVersion Bible API for newly created rows."
    )

    def handle(self, *args, **options):
        prompts = json.loads(DATA_FILE.read_text(encoding="utf-8"))

        created = 0
        fetched = 0
        for prompt in prompts:
            obj, was_created = DevotionalPrompt.objects.get_or_create(
                reference=prompt["reference"],
                defaults={"reflection_prompt": prompt["reflection_prompt"]},
            )
            if was_created:
                created += 1
                verse_text = get_passage_text(obj.reference)
                if verse_text:
                    obj.verse_text = verse_text
                    obj.save(update_fields=["verse_text"])
                    fetched += 1

        total = len(prompts)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new prompt(s) ({fetched} with verse text fetched); "
                f"{total} total in fixture; {DevotionalPrompt.objects.count()} now in database."
            )
        )
