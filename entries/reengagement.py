from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.utils import timezone

from .models import LoginCount

INACTIVITY_THRESHOLD_DAYS = 5

# Caps how many candidates one cron tick evaluates - same rationale as
# entries.push.MAX_PROFILES_PER_TICK: bounds one request's latency regardless of how many users
# are inactive at once, with anything left over naturally retried next tick since an episode's
# dedup isn't consumed until the email actually sends.
MAX_REENGAGEMENT_PER_TICK = 200


def send_due_reengagement_emails(login_url):
    """Emails any opted-in user a warm "come back" nudge once they've gone
    INACTIVITY_THRESHOLD_DAYS+ without a page view, per LoginCount.last_activity_at
    (updated on every request by entries.middleware.ActivityTrackingMiddleware).

    Sent at most once per inactivity episode - dedupe is last_reengagement_email_sent_at
    being newer than last_activity_at, not a same-day check like the push notifications,
    since this should only fire again after the user has come back and gone quiet a
    second time, not once every day they stay away.

    Called on the same cron tick as push notifications/prayer digests (see
    entries.views.send_due_notifications_view) since this app has no in-process scheduler.
    """
    cutoff = timezone.now() - timedelta(days=INACTIVITY_THRESHOLD_DAYS)
    sent = 0
    # Pushed into the query rather than filtered in Python per row: the profile__ join
    # requiring reengagement_emails_enabled=True already excludes Profile-less accounts
    # (e.g. createsuperuser) since that's an inner join, same effect as the old
    # `profile is None` check.
    login_counts = (
        LoginCount.objects.filter(last_activity_at__lt=cutoff, user__profile__reengagement_emails_enabled=True)
        .exclude(user__email="")
        .filter(
            Q(user__profile__last_reengagement_email_sent_at__isnull=True)
            | Q(user__profile__last_reengagement_email_sent_at__lte=F("last_activity_at"))
        )
        .select_related("user__profile")
        .order_by("?")[:MAX_REENGAGEMENT_PER_TICK]
    )
    for login_count in login_counts:
        user = login_count.user
        profile = user.profile

        context = {"first_name": profile.name.split(" ")[0], "login_url": login_url}
        subject = render_to_string("entries/reengagement_subject.txt", context).strip()
        text_body = render_to_string("entries/reengagement_email.txt", context)
        html_body = render_to_string("entries/reengagement_email.html", context)
        message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
        message.attach_alternative(html_body, "text/html")
        message.send()

        profile.last_reengagement_email_sent_at = timezone.now()
        profile.save(update_fields=["last_reengagement_email_sent_at"])
        sent += 1

    return sent
