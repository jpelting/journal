from datetime import timedelta

from django.db.models import Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Entry, MomentCheckIn

GRACE_PERIOD_DAYS = 7

MORNING_SCORE_FIELDS = (
    "morning_mental_score",
    "morning_physical_score",
    "morning_emotional_score",
    "morning_spiritual_score",
)
EVENING_SCORE_FIELDS = (
    "evening_mental_score",
    "evening_physical_score",
    "evening_emotional_score",
    "evening_spiritual_score",
)


def _active_dates(user):
    """Every calendar date the user did at least one check-in: a morning or evening
    mood score filled in on that day's Entry, or a Moment check-in logged that day."""
    score_filter = Q()
    for field in MORNING_SCORE_FIELDS + EVENING_SCORE_FIELDS:
        score_filter |= Q(**{f"{field}__isnull": False})
    entry_dates = set(Entry.objects.filter(user=user).filter(score_filter).values_list("date", flat=True))
    moment_dates = set(
        MomentCheckIn.objects.filter(user=user)
        .annotate(local_date=TruncDate("created_at"))
        .values_list("local_date", flat=True)
    )
    return entry_dates | moment_dates


def current_streak(user, today=None):
    """The user's current streak length in days, allowing one forgiven gap day per
    rolling GRACE_PERIOD_DAYS-day window - a "streak freeze" applied automatically,
    not something the user has to bank or activate.

    Walks backward day by day from today (or yesterday, if today has no check-in yet -
    today isn't a miss until it's over). Each active day adds 1. A gap day is forgiven
    (skipped without adding to the count, without ending the streak) as long as no
    other gap has been forgiven within the last GRACE_PERIOD_DAYS days; otherwise the
    walk stops there. Two gaps closer together than GRACE_PERIOD_DAYS apart therefore
    always end the streak, same as two gaps in the same rolling week would.
    """
    today = today or timezone.localdate()
    active_dates = _active_dates(user)
    if not active_dates:
        return 0

    cursor = today if today in active_dates else today - timedelta(days=1)

    streak = 0
    last_forgiven = None
    while True:
        if cursor in active_dates:
            streak += 1
            cursor -= timedelta(days=1)
            continue
        if last_forgiven is None or (last_forgiven - cursor).days >= GRACE_PERIOD_DAYS:
            last_forgiven = cursor
            cursor -= timedelta(days=1)
            continue
        break

    return streak
