from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Community, PrayerRequest
from .push import _slot_due, send_to_subscription

PURGE_DELAY_MINUTES = 30


def _active_member_users(community):
    return [membership.user for membership in community.memberships.filter(status="active").select_related("user")]


def _send_email(users, subject_template, text_template, context):
    """Sends a plain-text email with a styled HTML alternative (same template name, .html
    instead of .txt) attached, so HTML-capable clients render the styled version and others
    fall back to plain text."""
    recipients = [user.email for user in users if user.email]
    if not recipients:
        return
    subject = render_to_string(subject_template, context).strip()
    text_body = render_to_string(text_template, context)
    html_body = render_to_string(text_template.replace(".txt", ".html"), context)
    message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, recipients)
    message.attach_alternative(html_body, "text/html")
    message.send()


def _send_push_to_members(users, title, body):
    for user in users:
        for subscription in user.push_subscriptions.all():
            send_to_subscription(subscription, title, body)


def send_immediate_prayer_notification(prayer_request):
    """Instant email + push to every active member when an "immediate" prayer request is
    submitted. The request itself is not sent/purged yet - it's rolled into that community's
    next daily digest and purged from there (see send_due_prayer_digests/purge_expired_prayer_requests)."""
    community = prayer_request.community
    users = _active_member_users(community)
    context = {"community": community, "prayer_request": prayer_request}
    _send_email(
        users, "entries/prayer_request_immediate_subject.txt", "entries/prayer_request_immediate_email.txt", context
    )
    _send_push_to_members(
        users,
        "Immediate Prayer Request",
        f'An immediate prayer request has been shared in "{community.name}".',
    )
    prayer_request.immediate_sent_at = timezone.now()
    prayer_request.save(update_fields=["immediate_sent_at"])


def send_due_prayer_digests():
    """Send each community's daily prayer-request digest once its admin-configured
    prayer_digest_time has passed for the day, bundling every not-yet-digested request
    (immediate and scheduled alike). Called on the same cron tick as the quote/affirmation
    push sender - see send_due_notifications_view."""
    sent = 0
    tz = ZoneInfo(settings.WEATHER_TIMEZONE)
    now_local = timezone.now().astimezone(tz)
    today_local = now_local.date()

    for community in Community.objects.all():
        if not _slot_due(now_local, community.prayer_digest_time, community.last_prayer_digest_sent_date, today_local):
            continue

        pending = list(community.prayer_requests.filter(digest_sent_at__isnull=True))
        if pending:
            users = _active_member_users(community)
            _send_email(
                users,
                "entries/prayer_request_digest_subject.txt",
                "entries/prayer_request_digest_email.txt",
                {"community": community, "prayer_requests": pending},
            )
            now = timezone.now()
            PrayerRequest.objects.filter(pk__in=[p.pk for p in pending]).update(digest_sent_at=now)
            sent += 1

        community.last_prayer_digest_sent_date = today_local
        community.save(update_fields=["last_prayer_digest_sent_date"])

    return sent


def purge_expired_prayer_requests():
    """Delete prayer requests 30 minutes after they went out in a digest email - this table
    only ever holds same-day, not-yet-digested-long-ago data."""
    cutoff = timezone.now() - timedelta(minutes=PURGE_DELAY_MINUTES)
    deleted, _ = PrayerRequest.objects.filter(digest_sent_at__isnull=False, digest_sent_at__lte=cutoff).delete()
    return deleted
