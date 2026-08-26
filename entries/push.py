import json
import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from pywebpush import WebPushException, webpush

from .models import Entry, MotivationalQuote, Profile, SelfAffirmation
from .weather import weather_location_for_user

logger = logging.getLogger(__name__)


def send_to_subscription(subscription, title, body, url="/"):
    """Best-effort push send to one PushSubscription; never raises.

    `url` is where the notification takes the user on click (see sw.js's
    notificationclick handler) - defaults to the app root, but callers pass a more
    specific page (e.g. /notify/quote/?slot=1) so clicking the notification lands
    directly on the content it was about, not just the general check-in page.

    Prunes the subscription on a 404/410 (push service says the endpoint is
    gone - browser uninstalled, notification permission revoked, etc.),
    same fire-and-forget philosophy as entries.weather/entries.bible.
    """
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_CLAIM_EMAIL},
        )
    except WebPushException as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code in (404, 410):
            subscription.delete()
        else:
            logger.warning("Push send failed for subscription %s: %s", subscription.pk, exc)
    except Exception:
        logger.exception("Unexpected error sending push to subscription %s", subscription.pk)


def _slot_due(now_local, quote_time, last_sent_date, today_local):
    """True once `quote_time` has passed today and hasn't been sent yet today.

    Deliberately has no upper bound on how late "due" can fire: this is
    ticked by a GitHub Actions `schedule` cron, which GitHub does not
    guarantee runs every 5 minutes - under load (particularly near the top
    of the hour) ticks are commonly delayed by 20-50 minutes or more, so a
    narrow window (e.g. quote_time to quote_time+5min) can be - and was -
    skipped over entirely between two ticks, silently dropping that day's
    notification. Firing on whatever tick comes next after quote_time,
    however late, is preferable to missing the day outright; same-day
    dedup via last_sent_date still guarantees at most one send.
    """
    if last_sent_date == today_local:
        return False
    return now_local.time() >= quote_time


def _send_due_slot(profile, subscriptions, now_local, today_local, *, enabled, send_time, last_sent_field, slot, title, get_content, format_body, url):
    """Shared due-check/send/dedupe logic for one morning-or-evening slot of one
    notification kind (quote or affirmation). Returns True if a push went out."""
    if not enabled:
        return False
    last_sent_date = getattr(profile, last_sent_field)
    if not _slot_due(now_local, send_time, last_sent_date, today_local):
        return False

    content = get_content(today_local, slot)
    if content is None:
        return False

    body = format_body(content)
    for subscription in subscriptions:
        send_to_subscription(subscription, title, body, url=url)
    setattr(profile, last_sent_field, today_local)
    profile.save(update_fields=[last_sent_field])
    return True


def _send_due_checkin_reminder_slot(profile, subscriptions, now_local, today_local, *, enabled, send_time, last_sent_field, score_fields, url):
    """Sends one push nudging the user to do one morning-or-evening check-in, once its
    reminder time has passed, unless that slot's scores are already filled in for today.

    Deliberately does *not* set last_sent_field when skipped because the check-in is
    already done - only when a push actually goes out - so an early completion (before
    reminder time) permanently silences that slot's reminder for the day, while a
    not-yet-done user keeps getting evaluated tick to tick until the single push fires.
    """
    if not enabled:
        return False
    last_sent_date = getattr(profile, last_sent_field)
    if not _slot_due(now_local, send_time, last_sent_date, today_local):
        return False

    entry = Entry.objects.filter(user=profile.user, date=today_local).first()
    if entry and any(getattr(entry, field) is not None for field in score_fields):
        return False

    for subscription in subscriptions:
        send_to_subscription(subscription, "Check-in reminder", "Don't forget to check in today.", url=url)
    setattr(profile, last_sent_field, today_local)
    profile.save(update_fields=[last_sent_field])
    return True


def send_due_notifications():
    """Send any morning/evening quote/affirmation pushes, or check-in reminder push, due right
    now, for every opted-in user.

    Called on a short interval (see the send_due_quote_notifications management command and
    the /internal/send-due-quote-notifications/ view it backs) since this app has no in-process
    scheduler - the Fly machine auto-stops when idle. Dedupes via last_<slot>_{quote,affirmation}_sent_date
    / last_checkin_reminder_sent_date so repeated ticks within the same day don't double-fire.
    """
    sent = 0
    profiles = (
        Profile.objects.filter(
            Q(quotes_enabled=True) | Q(affirmations_enabled=True) | Q(checkin_reminder_enabled=True)
        )
        .exclude(user__push_subscriptions__isnull=True)
        .distinct()
    )
    for profile in profiles:
        subscriptions = list(profile.user.push_subscriptions.all())
        if not subscriptions:
            continue

        _, _, _, timezone_name = weather_location_for_user(profile.user)
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo(settings.WEATHER_TIMEZONE)
        now_local = timezone.now().astimezone(tz)
        today_local = now_local.date()

        if profile.quotes_enabled:
            for enabled, send_time, last_sent_field, slot, title in (
                (profile.quote_morning_enabled, profile.quote_morning_time, "last_morning_quote_sent_date", 1, "Your morning quote"),
                (profile.quote_evening_enabled, profile.quote_evening_time, "last_evening_quote_sent_date", 2, "Your evening quote"),
            ):
                if _send_due_slot(
                    profile, subscriptions, now_local, today_local,
                    enabled=enabled, send_time=send_time, last_sent_field=last_sent_field, slot=slot, title=title,
                    get_content=lambda d, s: MotivationalQuote.for_date(d, slot=s),
                    format_body=lambda quote: f"{quote.text} — {quote.author}",
                    url=f"/notify/quote/?slot={slot}",
                ):
                    sent += 1

        if profile.affirmations_enabled:
            for enabled, send_time, last_sent_field, slot, title in (
                (profile.affirmation_morning_enabled, profile.affirmation_morning_time, "last_morning_affirmation_sent_date", 1, "Your morning affirmation"),
                (profile.affirmation_evening_enabled, profile.affirmation_evening_time, "last_evening_affirmation_sent_date", 2, "Your evening affirmation"),
            ):
                if _send_due_slot(
                    profile, subscriptions, now_local, today_local,
                    enabled=enabled, send_time=send_time, last_sent_field=last_sent_field, slot=slot, title=title,
                    get_content=lambda d, s: SelfAffirmation.for_date(d, slot=s),
                    format_body=lambda affirmation: affirmation.text,
                    url=f"/notify/affirmation/?slot={slot}",
                ):
                    sent += 1

        if profile.checkin_reminder_enabled:
            for enabled, send_time, last_sent_field, score_fields, url in (
                (
                    profile.checkin_reminder_morning_enabled,
                    profile.checkin_reminder_morning_time,
                    "last_morning_checkin_reminder_sent_date",
                    ("morning_mental_score", "morning_physical_score", "morning_emotional_score", "morning_spiritual_score"),
                    "/checkin/morning/",
                ),
                (
                    profile.checkin_reminder_evening_enabled,
                    profile.checkin_reminder_evening_time,
                    "last_evening_checkin_reminder_sent_date",
                    ("evening_mental_score", "evening_physical_score", "evening_emotional_score", "evening_spiritual_score"),
                    "/checkin/evening/",
                ),
            ):
                if _send_due_checkin_reminder_slot(
                    profile, subscriptions, now_local, today_local,
                    enabled=enabled, send_time=send_time, last_sent_field=last_sent_field, score_fields=score_fields, url=url,
                ):
                    sent += 1

    return sent
