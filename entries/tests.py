from datetime import date

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Entry, MomentCheckIn, StoicPrompt
from .views import _next_stoic_prompt, _today_entry


class MultiUserIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="alice", password="pw12345")
        self.user_b = User.objects.create_user(username="bob", password="pw12345")
        self.entry_a = Entry.objects.create(user=self.user_a, date=date(2030, 1, 1), freeform_entry="alice's entry")
        self.entry_b = Entry.objects.create(user=self.user_b, date=date(2030, 1, 2), freeform_entry="bob's entry")

    def test_detail_view_200_for_own_entry(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("entries:detail", args=[self.entry_a.pk]))
        self.assertEqual(response.status_code, 200)

    def test_detail_view_404_for_other_users_entry(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("entries:detail", args=[self.entry_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_edit_view_404_for_other_users_entry_get(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("entries:edit", args=[self.entry_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_edit_view_404_for_other_users_entry_post(self):
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("entries:edit", args=[self.entry_b.pk]),
            {"date": "2030-01-02", "freeform_entry": "hijacked"},
        )
        self.assertEqual(response.status_code, 404)
        self.entry_b.refresh_from_db()
        self.assertEqual(self.entry_b.freeform_entry, "bob's entry")

    def test_create_view_sets_owner(self):
        self.client.force_login(self.user_a)
        self.client.post(
            reverse("entries:create"),
            {"date": "2030-06-01", "stoic_response": "", "devotional_response": "", "freeform_entry": "new one", "introspection_response": ""},
        )
        created = Entry.objects.get(user=self.user_a, date=date(2030, 6, 1))
        self.assertEqual(created.freeform_entry, "new one")

    def test_create_view_duplicate_date_shows_form_error_not_500(self):
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("entries:create"),
            {"date": "2030-01-01", "stoic_response": "", "devotional_response": "", "freeform_entry": "dup", "introspection_response": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "date", "You already have an entry for this date.")
        self.assertEqual(Entry.objects.filter(user=self.user_a, date=date(2030, 1, 1)).count(), 1)

    def test_export_pdf_excludes_other_users_entries(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("entries:export-pdf"), {"ids": [self.entry_b.pk]})
        self.assertRedirects(response, reverse("entries:export"))

    def test_export_pdf_mixed_ids_only_includes_own(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("entries:export-pdf"), {"ids": [self.entry_a.pk, self.entry_b.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("2030-01-01", response["Content-Disposition"])
        self.assertNotIn("2030-01-02", response["Content-Disposition"])

    def test_calendar_view_scoped_to_user(self):
        self.client.force_login(self.user_a)
        entry_a_same_month = Entry.objects.create(user=self.user_a, date=date(2030, 1, 5))
        entry_b_same_month = Entry.objects.create(user=self.user_b, date=date(2030, 1, 6))
        response = self.client.get(reverse("entries:calendar", args=[2030, 1]))
        entries_shown = {
            day["entry"].pk
            for week in response.context["weeks"]
            for day in week
            if day and day["entry"]
        }
        self.assertIn(self.entry_a.pk, entries_shown)
        self.assertIn(entry_a_same_month.pk, entries_shown)
        self.assertNotIn(self.entry_b.pk, entries_shown)
        self.assertNotIn(entry_b_same_month.pk, entries_shown)

    def test_journal_type_list_scoped(self):
        self.entry_a.stoic_response = "alice's stoic reflection"
        self.entry_a.save()
        self.entry_b.stoic_response = "bob's stoic reflection"
        self.entry_b.save()
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("entries:journal-type", args=["stoic"]))
        pks = {entry.pk for entry in response.context["entries"]}
        self.assertIn(self.entry_a.pk, pks)
        self.assertNotIn(self.entry_b.pk, pks)

    def test_moment_checkin_recents_scoped(self):
        MomentCheckIn.objects.create(user=self.user_a, note="alice's moment")
        MomentCheckIn.objects.create(user=self.user_b, note="bob's moment")
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("entries:checkin-moment"))
        notes = [moment.note for moment in response.context["recent_moments"]]
        self.assertIn("alice's moment", notes)
        self.assertNotIn("bob's moment", notes)

    def test_stoic_prompt_no_repeat_is_per_user(self):
        # Seed data (0002_seed_prompts) may have pre-loaded other active prompts;
        # isolate this test to exactly the two prompts it cares about.
        StoicPrompt.objects.update(active=False)
        prompt_1 = StoicPrompt.objects.create(text="prompt one", active=True)
        prompt_2 = StoicPrompt.objects.create(text="prompt two", active=True)
        self.entry_a.stoic_prompt = prompt_1
        self.entry_a.save()

        # user_a already used prompt_1, so with only prompt_2 left unused, the pick is deterministic.
        self.assertEqual(_next_stoic_prompt(self.user_a), prompt_2)

        # user_b has used nothing, so prompt_1 must still be a possible pick for them
        # (proves the "already used" scoping doesn't leak across users).
        picks_for_b = {_next_stoic_prompt(self.user_b).pk for _ in range(20)}
        self.assertIn(prompt_1.pk, picks_for_b)

    def test_today_entry_get_or_create_is_per_user(self):
        Entry.objects.filter(date=timezone.localdate()).delete()
        entry_for_a = _today_entry(self.user_a)
        entry_for_b = _today_entry(self.user_b)
        self.assertNotEqual(entry_for_a.pk, entry_for_b.pk)
        self.assertEqual(Entry.objects.filter(date=timezone.localdate()).count(), 2)

    def test_entry_unique_constraint_per_user_and_date(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Entry.objects.create(user=self.user_a, date=date(2030, 1, 1))

        # same date, different user, is fine (already true via entry_a/entry_b setup on distinct
        # dates) -- confirm explicitly with a shared date too.
        Entry.objects.create(user=self.user_b, date=date(2030, 1, 1))

    def test_admin_created_user_defaults_is_staff_false(self):
        new_user = User.objects.create_user(username="newperson", password="pw12345")
        self.assertFalse(new_user.is_staff)
        self.assertFalse(new_user.is_superuser)


class FieldEncryptionTests(TestCase):
    def test_round_trip_via_orm(self):
        entry = Entry.objects.create(user=self._make_user(), date=date(2030, 2, 1), freeform_entry="a private thought")
        fetched = Entry.objects.get(pk=entry.pk)
        self.assertEqual(fetched.freeform_entry, "a private thought")

    def test_raw_storage_is_not_plaintext(self):
        entry = Entry.objects.create(user=self._make_user(), date=date(2030, 2, 2), freeform_entry="another private thought")
        with connection.cursor() as cursor:
            cursor.execute("SELECT freeform_entry FROM entries_entry WHERE id=%s", [entry.pk])
            raw_value = cursor.fetchone()[0]
        self.assertNotIn("another private thought", raw_value)
        self.assertNotEqual(raw_value, "")

    def test_blank_stays_blank_and_exclude_filter_works(self):
        user = self._make_user()
        blank_entry = Entry.objects.create(user=user, date=date(2030, 2, 3), freeform_entry="")
        filled_entry = Entry.objects.create(user=user, date=date(2030, 2, 4), freeform_entry="not blank")

        with connection.cursor() as cursor:
            cursor.execute("SELECT freeform_entry FROM entries_entry WHERE id=%s", [blank_entry.pk])
            self.assertEqual(cursor.fetchone()[0], "")

        non_blank_pks = set(Entry.objects.filter(user=user).exclude(freeform_entry="").values_list("pk", flat=True))
        self.assertIn(filled_entry.pk, non_blank_pks)
        self.assertNotIn(blank_entry.pk, non_blank_pks)

    def test_key_rotation_old_ciphertext_still_decrypts(self):
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()

        with override_settings(FIELD_ENCRYPTION_KEYS=[old_key]):
            entry = Entry.objects.create(user=self._make_user(), date=date(2030, 2, 5), freeform_entry="rotate me")

        with override_settings(FIELD_ENCRYPTION_KEYS=[new_key, old_key]):
            fetched = Entry.objects.get(pk=entry.pk)
            self.assertEqual(fetched.freeform_entry, "rotate me")

            # a fresh save now re-encrypts under the new (first) key
            fetched.freeform_entry = "rotate me again"
            fetched.save()
            with connection.cursor() as cursor:
                cursor.execute("SELECT freeform_entry FROM entries_entry WHERE id=%s", [entry.pk])
                raw_after_rotation = cursor.fetchone()[0]

        with override_settings(FIELD_ENCRYPTION_KEYS=[old_key]):
            # old key alone can no longer decrypt data written under the new key
            with self.assertRaises(Exception):
                Entry.objects.get(pk=entry.pk).freeform_entry

        self.assertNotEqual(raw_after_rotation, "")

    def _make_user(self, **kwargs):
        counter = getattr(self, "_user_counter", 0) + 1
        self._user_counter = counter
        return User.objects.create_user(username=f"crypto-user-{counter}", password="pw12345", **kwargs)
