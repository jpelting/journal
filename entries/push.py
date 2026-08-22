import json
import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from pywebpush import WebPushException, webpush

from .models import MotivationalQuote, Profile, SelfAffirmation
from .weather import weather_location_for_user

logger = logging.getLogger(__name__)


def send_to_subscription(subscription, title, body):
    """Best-effort push send to one PushSubscription; never raises.

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
            data=json.dumps({"title": title, "body": body}),
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


def _send_due_slot(profile, subscriptions, now_local, today_local, *, enabled, send_time, last_sent_field, slot, title, get_content, format_body):
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
        send_to_subscription(subscription, title, body)
    setattr(profile, last_sent_field, today_local)
    profile.save(update_fields=[last_sent_field])
    return True


def send_due_notifications():
    """Send any morning/evening quote or affirmation pushes due right now, for every opted-in user.

    Called on a short interval (see the send_due_quote_notifications management command and
    the /internal/send-due-quote-notifications/ view it backs) since this app has no in-process
    scheduler - the Fly machine auto-stops when idle. Dedupes via last_<slot>_{quote,affirmation}_sent_date
    so repeated ticks within the same day don't double-fire.
    """
    sent = 0
    profiles = (
        Profile.objects.filter(Q(quotes_enabled=True) | Q(affirmations_enabled=True))
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
                ):
                    sent += 1

    return sent
