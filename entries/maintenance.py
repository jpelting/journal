from django.core.management import call_command
from django.utils import timezone

from .models import CronMaintenanceState


def clean_up_expired_sessions_if_due():
    """Runs Django's `clearsessions` once a day, piggybacked on the same cron tick as the
    notification pipelines (see entries.views.send_due_notifications_view) rather than a
    dedicated cron job. CSRF_USE_SESSIONS=True means every anonymous /login/ visit now creates
    a session row too, and Django never prunes expired sessions on its own - without this, the
    django_session table grows forever. Returns True if it actually ran this tick.
    """
    today = timezone.localdate()
    state, _ = CronMaintenanceState.objects.get_or_create(pk=1)
    if state.last_session_cleanup_date == today:
        return False
    call_command("clearsessions")
    state.last_session_cleanup_date = today
    state.save(update_fields=["last_session_cleanup_date"])
    return True
