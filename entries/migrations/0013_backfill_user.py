from django.conf import settings
from django.db import migrations


def backfill_user(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Entry = apps.get_model("entries", "Entry")
    MomentCheckIn = apps.get_model("entries", "MomentCheckIn")

    unowned_entries = Entry.objects.filter(user__isnull=True)
    unowned_moments = MomentCheckIn.objects.filter(user__isnull=True)
    if not unowned_entries.exists() and not unowned_moments.exists():
        # Nothing to backfill (e.g. a freshly created test database) -- nothing to guard either.
        return

    user_count = User.objects.count()
    if user_count != 1:
        raise RuntimeError(
            f"Expected exactly one existing User to backfill onto, found {user_count}. "
            "This migration assigns all pre-existing Entry/MomentCheckIn rows to the sole "
            "existing account and refuses to guess when that assumption doesn't hold."
        )
    sole_user = User.objects.get()

    unowned_entries.update(user=sole_user)
    unowned_moments.update(user=sole_user)


def unbackfill_user(apps, schema_editor):
    Entry = apps.get_model("entries", "Entry")
    MomentCheckIn = apps.get_model("entries", "MomentCheckIn")
    Entry.objects.update(user=None)
    MomentCheckIn.objects.update(user=None)


class Migration(migrations.Migration):

    dependencies = [
        ("entries", "0012_add_user_nullable"),
    ]

    operations = [
        migrations.RunPython(backfill_user, unbackfill_user),
    ]
