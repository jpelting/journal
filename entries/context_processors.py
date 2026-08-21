from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import SURVEY_DECLINE_COOLDOWN_DAYS, SURVEY_ELIGIBLE_ACCOUNT_AGE_DAYS, Announcement

SESSION_KEY = "last_seen_announcement_at"


def announcements(request):
    """Announcements the signed-in user hasn't dismissed yet, for the What's New popup.

    Dismissal is normally tracked on Profile.last_seen_announcement_at, but not every
    User has a Profile (e.g. the original admin account, created via createsuperuser
    rather than the access-request flow) - fall back to the session so the popup is
    always dismissible, never a permanent trap for accounts without one.
    """
    if not request.user.is_authenticated:
        return {}

    profile = getattr(request.user, "profile", None)
    if profile:
        since = profile.last_seen_announcement_at
    else:
        since = parse_datetime(request.session.get(SESSION_KEY, ""))

    unseen = Announcement.objects.filter(is_active=True)
    if since:
        unseen = unseen.filter(created_at__gt=since)

    return {"unseen_announcements": unseen}


def survey_prompt(request):
    """Whether to show the one-time site-feedback survey prompt.

    First offered once the account is SURVEY_ELIGIBLE_ACCOUNT_AGE_DAYS old. A completed
    response never shows it again; a decline re-arms it after SURVEY_DECLINE_COOLDOWN_DAYS
    so it can be re-offered rather than lost for good.
    """
    if not request.user.is_authenticated:
        return {}

    if request.resolver_match and request.resolver_match.url_name == "survey":
        return {}

    account_age_days = (timezone.localdate() - request.user.date_joined.date()).days
    if account_age_days < SURVEY_ELIGIBLE_ACCOUNT_AGE_DAYS:
        return {}

    response = getattr(request.user, "survey_response", None)
    if response:
        if response.completed_at:
            return {}
        if response.declined_at:
            cooldown_end = response.declined_at + timedelta(days=SURVEY_DECLINE_COOLDOWN_DAYS)
            if timezone.now() < cooldown_end:
                return {}

    return {"show_survey_prompt": True}
