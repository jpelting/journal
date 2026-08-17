import json
from pathlib import Path

from django.core.management.base import BaseCommand

from entries.bible import get_passage_text
from entries.models import DevotionalPrompt

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "devotional_prompts.json"


class Command(BaseCommand):
    help = (
        "Load DevotionalPrompt rows from entries/data/devotional_prompts.json (idempotent). "
        "verse_text comes from the fixture's hand-curated King James Version (public domain); "
        "if a prompt has none, live fetch from the YouVersion Bible API is tried as a fallback "
        "for newly created rows. Pass --force to overwrite verse_text/context_summary/"
        "meaning_summary/reflection_prompt on existing rows too."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite verse_text/context_summary/meaning_summary/reflection_prompt on rows that already exist.",
        )

    def handle(self, *args, **options):
        prompts = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        force = options["force"]

        created = 0
        fetched = 0
        updated = 0
        for prompt in prompts:
            obj, was_created = DevotionalPrompt.objects.get_or_create(
                reference=prompt["reference"],
                defaults={
                    "reflection_prompt": prompt["reflection_prompt"],
                    "context_summary": prompt.get("context_summary", ""),
                    "meaning_summary": prompt.get("meaning_summary", ""),
                    "verse_text": prompt.get("verse_text", ""),
                },
            )
            if was_created:
                created += 1
                if not obj.verse_text:
                    verse_text = get_passage_text(obj.reference)
                    if verse_text:
                        obj.verse_text = verse_text
                        obj.save(update_fields=["verse_text"])
                        fetched += 1
            else:
                fields = ["verse_text", "context_summary", "meaning_summary", "reflection_prompt"]
                changed = []
                for field in fields:
                    new_value = prompt.get(field, "")
                    current_value = getattr(obj, field)
                    if new_value and (force or not current_value):
                        setattr(obj, field, new_value)
                        changed.append(field)
                if changed:
                    obj.save(update_fields=changed)
                    updated += 1

        total = len(prompts)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new prompt(s) ({fetched} with verse text fetched live); "
                f"updated {updated} existing prompt(s); "
                f"{total} total in fixture; {DevotionalPrompt.objects.count()} now in database."
            )
        )
