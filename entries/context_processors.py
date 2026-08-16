from django.utils.dateparse import parse_datetime

from .models import Announcement

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
