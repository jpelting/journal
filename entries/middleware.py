from django.utils import timezone

from .models import FeatureUsageEvent, LoginCount

ACTIVITY_HEARTBEAT_SECONDS = 60

FEATURE_BY_VIEW_NAME = {
    "entries:checkin-morning": "checkin_morning",
    "entries:checkin-evening": "checkin_evening",
    "entries:checkin-moment": "checkin_moment",
    "entries:calendar": "calendar",
    "entries:list": "journals_hub",
    "entries:create": "entry_create",
    "entries:edit": "entry_edit",
    "entries:detail": "entry_detail",
    "entries:export": "export",
    "entries:export-pdf": "export",
    "entries:account": "account",
    "entries:feedback": "feedback",
    "entries:survey": "survey",
    "entries:community-list": "community",
    "entries:community-detail": "community",
    "entries:notify-prayer-request": "prayer_request",
    "entries:notify-quote": "quote",
    "entries:notify-affirmation": "affirmation",
}

JOURNAL_TYPE_FEATURES = {
    "stoic": "journal_stoic",
    "devotional": "journal_devotional",
    "freeform": "journal_freeform",
    "introspection": "journal_introspection",
}


class ActivityTrackingMiddleware:
    """Best-effort tracking of who's signed in and which features they use, for the admin
    activity dashboard. Never blocks or breaks a request on failure, same fire-and-forget
    pattern as entries.weather/entries.bible. Records only feature names and timestamps,
    never entry content.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._track(request, response)
        except Exception:
            pass
        return response

    def _track(self, request, response):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return
        if not (200 <= response.status_code < 400):
            return

        self._update_last_activity(user)

        # Only count an actual page render (200), not a redirect away from the URL — e.g. the
        # morning check-in redirects outside its allowed time window, which is a *blocked*
        # attempt, not usage of the feature.
        if response.status_code != 200:
            return

        match = request.resolver_match
        if match is None:
            return
        feature = FEATURE_BY_VIEW_NAME.get(match.view_name)
        if match.view_name == "entries:journal-type":
            feature = JOURNAL_TYPE_FEATURES.get(match.kwargs.get("journal_type"))
        if feature:
            FeatureUsageEvent.objects.get_or_create(user=user, feature=feature, date=timezone.localdate())

    def _update_last_activity(self, user):
        now = timezone.now()
        login_count, _ = LoginCount.objects.get_or_create(user=user)
        stale = (
            login_count.last_activity_at is None
            or (now - login_count.last_activity_at).total_seconds() > ACTIVITY_HEARTBEAT_SECONDS
        )
        if stale:
            login_count.last_activity_at = now
            login_count.save(update_fields=["last_activity_at"])
