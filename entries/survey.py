from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from .models import SURVEY_ELIGIBLE_ACCOUNT_AGE_DAYS, SurveyResponse

# Caps how many candidates one cron tick evaluates - same rationale as
# entries.reengagement.MAX_REENGAGEMENT_PER_TICK.
MAX_SURVEY_EMAILS_PER_TICK = 200


def send_due_survey_emails(survey_url):
    """Emails an eligible user the day-14 site-feedback survey once, so the ask reaches
    their inbox in addition to the in-app prompt (see entries.context_processors.survey_prompt).

    Sent at most once ever per user - dedupe is SurveyResponse.email_sent_at being set, not
    tied to the in-app prompt's decline/cooldown logic, since a one-time nudge email shouldn't
    re-fire just because the in-app prompt re-arms after a decline.

    Called on the same cron tick as push notifications/prayer digests/reengagement emails
    (see entries.views.send_due_notifications_view) since this app has no in-process scheduler.
    """
    cutoff_date = timezone.localdate() - timedelta(days=SURVEY_ELIGIBLE_ACCOUNT_AGE_DAYS)
    sent = 0
    users = (
        get_user_model()
        .objects.filter(date_joined__date__lte=cutoff_date, profile__isnull=False)
        .exclude(email="")
        .exclude(Q(survey_response__email_sent_at__isnull=False) | Q(survey_response__completed_at__isnull=False))
        .select_related("profile")
        .order_by("?")[:MAX_SURVEY_EMAILS_PER_TICK]
    )
    for user in users:
        context = {"first_name": user.profile.name.split(" ")[0], "survey_url": survey_url}
        subject = render_to_string("entries/survey_email_subject.txt", context).strip()
        text_body = render_to_string("entries/survey_email.txt", context)
        html_body = render_to_string("entries/survey_email.html", context)
        message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
        message.attach_alternative(html_body, "text/html")
        message.send()

        response, _ = SurveyResponse.objects.get_or_create(user=user)
        response.email_sent_at = timezone.now()
        response.save(update_fields=["email_sent_at"])
        sent += 1

    return sent
