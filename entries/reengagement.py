from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import LoginCount

INACTIVITY_THRESHOLD_DAYS = 5

# The send schedule within one inactivity episode, as (how many emails at this stage, days
# between each). First 4 emails every 5 days, then 6 emails roughly monthly (~6 months), then
# 5 emails roughly yearly (~5 years) - after that, silence until the user comes back and goes
# quiet again, which starts a fresh episode back at stage one.
REENGAGEMENT_SCHEDULE = [
    (4, 5),
    (6, 30),
    (5, 365),
]

# Caps how many candidates one cron tick evaluates - same rationale as
# entries.push.MAX_PROFILES_PER_TICK: bounds one request's latency regardless of how many users
# are inactive at once, with anything left over naturally retried next tick since a resend's
# dedup isn't consumed until the email actually sends.
MAX_REENGAGEMENT_PER_TICK = 200


def _interval_days_for(emails_sent_this_episode):
    """Days to wait before the next email, given how many have already gone out this episode -
    per REENGAGEMENT_SCHEDULE - or None once the whole schedule is exhausted."""
    remaining = emails_sent_this_episode
    for count, interval_days in REENGAGEMENT_SCHEDULE:
        if remaining < count:
            return interval_days
        remaining -= count
    return None


def send_due_reengagement_emails(login_url):
    """Emails any opted-in user a warm "come back" nudge once they've gone
    INACTIVITY_THRESHOLD_DAYS+ without a page view, per LoginCount.last_activity_at
    (updated on every request by entries.middleware.ActivityTrackingMiddleware), then keeps
    resending per REENGAGEMENT_SCHEDULE for as long as they stay inactive - tapering from every
    5 days, to roughly monthly, to roughly yearly, before finally going silent.

    Profile.reengagement_emails_sent_count tracks progress through the schedule for the
    current inactivity episode. If the user was active again after their last email
    (last_activity_at newer than last_reengagement_email_sent_at), that's treated as a new
    episode - the count resets to 0 and the schedule restarts at stage one, gated by the same
    INACTIVITY_THRESHOLD_DAYS as a first-time send.

    Called on the same cron tick as push notifications/prayer digests (see
    entries.views.send_due_notifications_view) since this app has no in-process scheduler.
    """
    now = timezone.now()
    inactivity_cutoff = now - timedelta(days=INACTIVITY_THRESHOLD_DAYS)
    sent = 0
    # Pushed into the query rather than filtered in Python per row: the profile__ join
    # requiring reengagement_emails_enabled=True already excludes Profile-less accounts
    # (e.g. createsuperuser) since that's an inner join, same effect as the old
    # `profile is None` check. The per-stage interval itself can't be expressed as a single
    # query condition (it depends on each user's own count), so that part is checked below.
    login_counts = (
        LoginCount.objects.filter(last_activity_at__lt=inactivity_cutoff, user__profile__reengagement_emails_enabled=True)
        .exclude(user__email="")
        .select_related("user__profile")
        .order_by("?")[:MAX_REENGAGEMENT_PER_TICK]
    )
    for login_count in login_counts:
        user = login_count.user
        profile = user.profile
        last_sent = profile.last_reengagement_email_sent_at

        new_episode = last_sent is None or login_count.last_activity_at > last_sent
        emails_sent_this_episode = 0 if new_episode else profile.reengagement_emails_sent_count

        interval_days = _interval_days_for(emails_sent_this_episode)
        if interval_days is None:
            continue  # schedule exhausted for this episode - stay quiet until a new one starts

        # A new episode is already gated by inactivity_cutoff above (INACTIVITY_THRESHOLD_DAYS,
        # same as stage one's interval); an ongoing episode needs its own stage interval to
        # have passed since the last send.
        if not new_episode and now - last_sent < timedelta(days=interval_days):
            continue

        context = {"first_name": profile.name.split(" ")[0], "login_url": login_url}
        subject = render_to_string("entries/reengagement_subject.txt", context).strip()
        text_body = render_to_string("entries/reengagement_email.txt", context)
        html_body = render_to_string("entries/reengagement_email.html", context)
        message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
        message.attach_alternative(html_body, "text/html")
        message.send()

        profile.last_reengagement_email_sent_at = now
        profile.reengagement_emails_sent_count = emails_sent_this_episode + 1
        profile.save(update_fields=["last_reengagement_email_sent_at", "reengagement_emails_sent_count"])
        sent += 1

    return sent
