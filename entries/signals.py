from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from .models import LoginCount


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
    login_count, _ = LoginCount.objects.get_or_create(user=user)
    login_count.count += 1
    login_count.last_login_at = timezone.now()
    login_count.save(update_fields=["count", "last_login_at"])
