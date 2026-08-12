from django.db import migrations

from entries.crypto import decrypt_text, encrypt_text

ENTRY_FIELDS = [
    "one_percent_goal",
    "morning_anxious_about",
    "morning_within_control",
    "morning_reserve_clause",
    "evening_did_well",
    "evening_where_falter",
    "evening_could_improve",
    "evening_gratitude_audit",
    "stoic_response",
    "devotional_response",
    "freeform_entry",
    "introspection_response",
]
MOMENT_CHECKIN_FIELDS = ["note"]
GOAL_FIELDS = ["text"]


def _transform_rows(model, fields, transform):
    rows = list(model.objects.all())
    for row in rows:
        for field in fields:
            value = getattr(row, field)
            if value:
                setattr(row, field, transform(value))
    model.objects.bulk_update(rows, fields)


def encrypt_existing_content(apps, schema_editor):
    Entry = apps.get_model("entries", "Entry")
    MomentCheckIn = apps.get_model("entries", "MomentCheckIn")
    Goal = apps.get_model("entries", "Goal")

    _transform_rows(Entry, ENTRY_FIELDS, encrypt_text)
    _transform_rows(MomentCheckIn, MOMENT_CHECKIN_FIELDS, encrypt_text)
    _transform_rows(Goal, GOAL_FIELDS, encrypt_text)


def decrypt_existing_content(apps, schema_editor):
    Entry = apps.get_model("entries", "Entry")
    MomentCheckIn = apps.get_model("entries", "MomentCheckIn")
    Goal = apps.get_model("entries", "Goal")

    _transform_rows(Entry, ENTRY_FIELDS, decrypt_text)
    _transform_rows(MomentCheckIn, MOMENT_CHECKIN_FIELDS, decrypt_text)
    _transform_rows(Goal, GOAL_FIELDS, decrypt_text)


class Migration(migrations.Migration):

    dependencies = [
        ("entries", "0014_tighten_user_and_date_constraint"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_content, decrypt_existing_content),
    ]
