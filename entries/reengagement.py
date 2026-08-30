from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import LoginCount

INACTIVITY_THRESHOLD_DAYS = 5


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
    login_counts = LoginCount.objects.filter(last_activity_at__lt=cutoff).select_related("user__profile")
    for login_count in login_counts:
        user = login_count.user
        profile = getattr(user, "profile", None)
        if profile is None or not profile.reengagement_emails_enabled or not user.email:
            continue
        if (
            profile.last_reengagement_email_sent_at
            and profile.last_reengagement_email_sent_at > login_count.last_activity_at
        ):
            continue

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
