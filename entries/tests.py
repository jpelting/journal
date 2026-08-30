import json
from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Entry,
    LoginCount,
    MomentCheckIn,
    MotivationalQuote,
    Profile,
    PushSubscription,
    SelfAffirmation,
    StoicPrompt,
)
from .push import send_due_notifications
from .reengagement import send_due_reengagement_emails
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

    def test_moment_checkin_saves_deep_dive_whys(self):
        self.client.force_login(self.user_a)
        self.client.post(
            reverse("entries:checkin-moment"),
            data={
                "emotions": [],
                "note": "felt anxious",
                "deep_dive_why_1": "because of the deadline",
                "deep_dive_why_2": "because I procrastinated",
                "deep_dive_why_3": "",
                "deep_dive_why_4": "",
                "deep_dive_why_5": "",
            },
        )
        moment = MomentCheckIn.objects.filter(user=self.user_a).latest("created_at")
        self.assertEqual(moment.note, "felt anxious")
        self.assertEqual(moment.deep_dive_why_1, "because of the deadline")
        self.assertEqual(moment.deep_dive_why_2, "because I procrastinated")
        self.assertEqual(moment.deep_dive_why_3, "")

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


class PushNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="quote-fan", password="pw12345")
        self.profile = Profile.objects.create(
            user=self.user,
            name="Quote Fan",
            date_of_birth=date(1990, 1, 1),
            gender="prefer_not_to_say",
            zipcode="28115",
            quotes_enabled=True,
            quote_morning_enabled=True,
            quote_morning_time=time(7, 0),
            quote_evening_enabled=False,
        )
        self.subscription = PushSubscription.objects.create(
            user=self.user, endpoint="https://push.example.com/abc", p256dh="pkey", auth="akey"
        )
        MotivationalQuote.objects.create(day_of_year=1, slot=1, text="Quote of the day.", author="Someone")

    def _fake_now(self, hour, minute):
        return datetime(2030, 1, 1, hour, minute, tzinfo=ZoneInfo("UTC"))

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_sends_once_at_quote_time_and_not_again_same_day(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        with patch("django.utils.timezone.now", return_value=self._fake_now(7, 2)):
            sent = send_due_notifications()
        self.assertEqual(sent, 1)
        mock_send.assert_called_once()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_morning_quote_sent_date, date(2030, 1, 1))

        mock_send.reset_mock()
        with patch("django.utils.timezone.now", return_value=self._fake_now(7, 4)):
            sent_again = send_due_notifications()
        self.assertEqual(sent_again, 0)
        mock_send.assert_not_called()

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_does_not_send_before_quote_time(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        with patch("django.utils.timezone.now", return_value=self._fake_now(6, 59)):
            sent = send_due_notifications()
        self.assertEqual(sent, 0)
        mock_send.assert_not_called()

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_sends_on_a_late_tick_if_still_unsent_for_today(self, mock_location, mock_send):
        # The sender is ticked by a GitHub Actions cron that isn't guaranteed to run every
        # 5 minutes - it commonly gets delayed 20-50+ minutes under load, which can (and did)
        # skip a narrow send window outright. A late tick should still deliver that day's
        # quote rather than silently drop it, as long as nothing's gone out yet today.
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        with patch("django.utils.timezone.now", return_value=self._fake_now(9, 0)):
            sent = send_due_notifications()
        self.assertEqual(sent, 1)
        mock_send.assert_called_once()

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_sends_affirmation_independently_of_quotes(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        SelfAffirmation.objects.create(day_of_year=1, slot=1, text="I am ready for today.")
        self.profile.quotes_enabled = False
        self.profile.affirmations_enabled = True
        self.profile.affirmation_morning_enabled = True
        self.profile.affirmation_morning_time = time(7, 0)
        self.profile.save()

        with patch("django.utils.timezone.now", return_value=self._fake_now(7, 2)):
            sent = send_due_notifications()
        self.assertEqual(sent, 1)
        mock_send.assert_called_once_with(
            self.subscription, "Your morning affirmation", "I am ready for today.", url="/notify/affirmation/?slot=1"
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_morning_affirmation_sent_date, date(2030, 1, 1))

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_sends_both_quote_and_affirmation_when_both_enabled(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        SelfAffirmation.objects.create(day_of_year=1, slot=1, text="I am ready for today.")
        self.profile.affirmations_enabled = True
        self.profile.affirmation_morning_enabled = True
        self.profile.affirmation_morning_time = time(7, 0)
        self.profile.save()

        with patch("django.utils.timezone.now", return_value=self._fake_now(7, 2)):
            sent = send_due_notifications()
        self.assertEqual(sent, 2)
        self.assertEqual(mock_send.call_count, 2)

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_sends_morning_checkin_reminder_when_not_yet_checked_in(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        self.profile.quotes_enabled = False
        self.profile.checkin_reminder_enabled = True
        self.profile.checkin_reminder_morning_enabled = True
        self.profile.checkin_reminder_morning_time = time(9, 0)
        self.profile.save()

        with patch("django.utils.timezone.now", return_value=self._fake_now(9, 2)):
            sent = send_due_notifications()
        self.assertEqual(sent, 1)
        mock_send.assert_called_once_with(
            self.subscription, "Check-in reminder", "Don't forget to check in today.", url="/checkin/morning/"
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_morning_checkin_reminder_sent_date, date(2030, 1, 1))

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_skips_morning_checkin_reminder_if_already_checked_in(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        self.profile.quotes_enabled = False
        self.profile.checkin_reminder_enabled = True
        self.profile.checkin_reminder_morning_enabled = True
        self.profile.checkin_reminder_morning_time = time(9, 0)
        self.profile.save()
        Entry.objects.create(user=self.user, date=date(2030, 1, 1), morning_mental_score=7)

        with patch("django.utils.timezone.now", return_value=self._fake_now(9, 2)):
            sent = send_due_notifications()
        self.assertEqual(sent, 0)
        mock_send.assert_not_called()
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.last_morning_checkin_reminder_sent_date)

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_evening_checkin_reminder_independent_of_morning(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        self.profile.quotes_enabled = False
        self.profile.checkin_reminder_enabled = True
        self.profile.checkin_reminder_evening_enabled = True
        self.profile.checkin_reminder_evening_time = time(20, 0)
        self.profile.save()
        Entry.objects.create(user=self.user, date=date(2030, 1, 1), morning_mental_score=7)

        with patch("django.utils.timezone.now", return_value=self._fake_now(20, 2)):
            sent = send_due_notifications()
        self.assertEqual(sent, 1)
        mock_send.assert_called_once_with(
            self.subscription, "Check-in reminder", "Don't forget to check in today.", url="/checkin/evening/"
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_evening_checkin_reminder_sent_date, date(2030, 1, 1))

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_checkin_reminder_still_fires_next_day_after_a_send(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        self.profile.quotes_enabled = False
        self.profile.checkin_reminder_enabled = True
        self.profile.checkin_reminder_morning_enabled = True
        self.profile.checkin_reminder_morning_time = time(9, 0)
        self.profile.last_morning_checkin_reminder_sent_date = date(2029, 12, 31)
        self.profile.save()

        with patch("django.utils.timezone.now", return_value=self._fake_now(9, 2)):
            sent = send_due_notifications()
        self.assertEqual(sent, 1)
        mock_send.assert_called_once()

    def test_push_subscribe_requires_login(self):
        response = self.client.post(
            reverse("entries:push-subscribe"),
            data=json.dumps({"endpoint": "https://push.example.com/new", "keys": {"p256dh": "a", "auth": "b"}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

    def test_push_subscribe_creates_subscription(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("entries:push-subscribe"),
            data=json.dumps({"endpoint": "https://push.example.com/new", "keys": {"p256dh": "a", "auth": "b"}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PushSubscription.objects.filter(endpoint="https://push.example.com/new", user=self.user).exists())

    def test_push_subscribe_rejects_malformed_payload(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("entries:push-subscribe"), data="not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_cron_endpoint_rejects_missing_or_wrong_secret(self):
        response = self.client.post(reverse("entries:send-due-quote-notifications"))
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("entries:send-due-quote-notifications"), HTTP_AUTHORIZATION="Bearer wrong-token"
        )
        self.assertEqual(response.status_code, 403)

    @patch("entries.push.send_to_subscription")
    @patch("entries.push.weather_location_for_user")
    def test_cron_endpoint_accepts_correct_secret(self, mock_location, mock_send):
        mock_location.return_value = (0, 0, "Nowhere", "UTC")
        with patch("django.utils.timezone.now", return_value=self._fake_now(7, 2)):
            response = self.client.post(
                reverse("entries:send-due-quote-notifications"),
                HTTP_AUTHORIZATION=f"Bearer {settings.CRON_SECRET}",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 1)


class ReengagementEmailTests(TestCase):
    FIXED_NOW = datetime(2030, 1, 10, 12, 0, tzinfo=ZoneInfo("UTC"))
    LOGIN_URL = "https://example.com/login/"

    def setUp(self):
        self.user = User.objects.create_user(username="quiet-user", email="quiet@example.com", password="pw12345")
        self.profile = Profile.objects.create(
            user=self.user,
            name="Quiet User",
            date_of_birth=date(1990, 1, 1),
            gender="prefer_not_to_say",
            zipcode="28115",
        )
        self.login_count = LoginCount.objects.create(
            user=self.user, last_activity_at=self.FIXED_NOW - timedelta(days=6)
        )

    def test_sends_after_threshold_and_not_again_until_active_since(self):
        with patch("django.utils.timezone.now", return_value=self.FIXED_NOW):
            sent = send_due_reengagement_emails(self.LOGIN_URL)
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Quiet", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_reengagement_email_sent_at, self.FIXED_NOW)

        with patch("django.utils.timezone.now", return_value=self.FIXED_NOW + timedelta(minutes=2)):
            sent_again = send_due_reengagement_emails(self.LOGIN_URL)
        self.assertEqual(sent_again, 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_does_not_send_before_threshold(self):
        self.login_count.last_activity_at = self.FIXED_NOW - timedelta(days=2)
        self.login_count.save()
        with patch("django.utils.timezone.now", return_value=self.FIXED_NOW):
            sent = send_due_reengagement_emails(self.LOGIN_URL)
        self.assertEqual(sent, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_respects_opt_out(self):
        self.profile.reengagement_emails_enabled = False
        self.profile.save()
        with patch("django.utils.timezone.now", return_value=self.FIXED_NOW):
            sent = send_due_reengagement_emails(self.LOGIN_URL)
        self.assertEqual(sent, 0)

    def test_skips_users_without_a_profile(self):
        self.profile.delete()
        with patch("django.utils.timezone.now", return_value=self.FIXED_NOW):
            sent = send_due_reengagement_emails(self.LOGIN_URL)
        self.assertEqual(sent, 0)

    def test_resends_after_activity_resumes_and_goes_quiet_again(self):
        with patch("django.utils.timezone.now", return_value=self.FIXED_NOW):
            send_due_reengagement_emails(self.LOGIN_URL)

        # User comes back the next day, then goes quiet again.
        self.login_count.last_activity_at = self.FIXED_NOW + timedelta(days=1)
        self.login_count.save()

        with patch("django.utils.timezone.now", return_value=self.FIXED_NOW + timedelta(days=7)):
            sent = send_due_reengagement_emails(self.LOGIN_URL)
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 2)
