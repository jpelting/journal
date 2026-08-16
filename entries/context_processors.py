from .models import Announcement


def announcements(request):
    """Announcements the signed-in user hasn't dismissed yet, for the What's New popup."""
    if not request.user.is_authenticated:
        return {}

    profile = getattr(request.user, "profile", None)
    unseen = Announcement.objects.filter(is_active=True)
    if profile and profile.last_seen_announcement_at:
        unseen = unseen.filter(created_at__gt=profile.last_seen_announcement_at)

    return {"unseen_announcements": unseen}
