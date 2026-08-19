import csv
from collections import defaultdict
from datetime import timedelta
from io import StringIO

from django.db.models import Count
from django.db.models.functions import TruncWeek

from .models import FeatureUsageEvent, LoginCount

FEATURE_LABELS = dict(FeatureUsageEvent.FEATURE_CHOICES)


def build_usage_report(start_date, end_date):
    """Aggregate FeatureUsageEvent/LoginCount data between start_date and end_date (inclusive)
    into a plain dict, consumed by both the CSV/PDF renderers below and the
    send_usage_report management command. Never touches entry content.
    """
    events = FeatureUsageEvent.objects.filter(date__gte=start_date, date__lte=end_date)

    feature_rows = events.values("feature").annotate(n=Count("id")).order_by("-n")
    feature_totals = [
        {"feature": row["feature"], "label": FEATURE_LABELS.get(row["feature"], row["feature"]), "count": row["n"]}
        for row in feature_rows
    ]

    daily_rows = events.values("date").annotate(n=Count("user", distinct=True)).order_by("date")
    daily_by_date = {row["date"]: row["n"] for row in daily_rows}
    daily_active = []
    d = start_date
    while d <= end_date:
        daily_active.append({"date": d, "active_users": daily_by_date.get(d, 0)})
        d += timedelta(days=1)

    weekly_rows = (
        events.annotate(week=TruncWeek("date")).values("week").annotate(n=Count("user", distinct=True)).order_by("week")
    )
    weekly_active = [{"week_start": row["week"], "active_users": row["n"]} for row in weekly_rows]

    per_user_rows = (
        events.values("user_id", "user__username")
        .annotate(active_days=Count("date", distinct=True), events_total=Count("id"))
        .order_by("-events_total")
    )

    feature_by_user = defaultdict(dict)
    for row in events.values("user_id", "feature").annotate(n=Count("id")):
        feature_by_user[row["user_id"]][FEATURE_LABELS.get(row["feature"], row["feature"])] = row["n"]

    login_counts = {lc.user_id: lc for lc in LoginCount.objects.all()}

    per_user = []
    for row in per_user_rows:
        uid = row["user_id"]
        lc = login_counts.get(uid)
        per_user.append(
            {
                "username": row["user__username"],
                "active_days_in_range": row["active_days"],
                "events_in_range": row["events_total"],
                "lifetime_sign_ins": lc.count if lc else 0,
                "last_seen": lc.last_activity_at if lc else None,
                "feature_counts": feature_by_user[uid],
            }
        )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "feature_totals": feature_totals,
        "daily_active": daily_active,
        "weekly_active": weekly_active,
        "per_user": per_user,
    }


def render_report_csv(report):
    buf = StringIO()
    writer = csv.writer(buf)

    writer.writerow([f"The Wax Tablet usage report: {report['start_date']} to {report['end_date']}"])
    writer.writerow([])

    writer.writerow(["Feature usage"])
    writer.writerow(["Feature", "Count"])
    for row in report["feature_totals"]:
        writer.writerow([row["label"], row["count"]])
    writer.writerow([])

    writer.writerow(["Daily active users"])
    writer.writerow(["Date", "Active users"])
    for row in report["daily_active"]:
        writer.writerow([row["date"].isoformat(), row["active_users"]])
    writer.writerow([])

    writer.writerow(["Weekly active users"])
    writer.writerow(["Week starting", "Active users"])
    for row in report["weekly_active"]:
        writer.writerow([row["week_start"].isoformat(), row["active_users"]])
    writer.writerow([])

    writer.writerow(["Per-user summary"])
    all_features = sorted({label for row in report["per_user"] for label in row["feature_counts"]})
    writer.writerow(["User", "Active days in range", "Events in range", "Lifetime sign-ins", "Last seen"] + all_features)
    for row in report["per_user"]:
        writer.writerow(
            [
                row["username"],
                row["active_days_in_range"],
                row["events_in_range"],
                row["lifetime_sign_ins"],
                row["last_seen"].isoformat() if row["last_seen"] else "",
            ]
            + [row["feature_counts"].get(f, 0) for f in all_features]
        )

    return buf.getvalue()
