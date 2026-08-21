import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from pywebpush import WebPushException, webpush

from .models import MotivationalQuote, Profile
from .weather import weather_location_for_user

logger = logging.getLogger(__name__)

QUOTE_SEND_WINDOW_MINUTES = 5


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
    if last_sent_date == today_local:
        return False
    window_end = (datetime.combine(today_local, quote_time) + timedelta(minutes=QUOTE_SEND_WINDOW_MINUTES)).time()
    return quote_time <= now_local.time() < window_end


def send_due_notifications():
    """Send any morning/evening quote pushes that are due right now, for every opted-in user.

    Called on a short interval (see the send_due_quote_notifications management command and
    the /internal/send-due-quote-notifications/ view it backs) since this app has no in-process
    scheduler - the Fly machine auto-stops when idle. Dedupes via last_<slot>_quote_sent_date so
    repeated ticks within the same send window don't double-fire.
    """
    sent = 0
    profiles = Profile.objects.filter(quotes_enabled=True).exclude(user__push_subscriptions__isnull=True).distinct()
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

        for enabled, quote_time, last_sent_field, slot in (
            (profile.quote_morning_enabled, profile.quote_morning_time, "last_morning_quote_sent_date", 1),
            (profile.quote_evening_enabled, profile.quote_evening_time, "last_evening_quote_sent_date", 2),
        ):
            if not enabled:
                continue
            last_sent_date = getattr(profile, last_sent_field)
            if not _slot_due(now_local, quote_time, last_sent_date, today_local):
                continue

            quote = MotivationalQuote.for_date(today_local, slot=slot)
            if quote is None:
                continue

            title = "Your morning quote" if slot == 1 else "Your evening quote"
            body = f"{quote.text} — {quote.author}"
            for subscription in subscriptions:
                send_to_subscription(subscription, title, body)
            setattr(profile, last_sent_field, today_local)
            profile.save(update_fields=[last_sent_field])
            sent += 1

    return sent
