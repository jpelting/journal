import calendar
import hmac
import json
from datetime import date
from io import BytesIO
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_not_required
from django.core.mail import send_mail
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from xhtml2pdf import pisa

from .push import send_due_notifications, send_to_subscription

from .context_processors import SESSION_KEY as ANNOUNCEMENT_SESSION_KEY
from .forms import (
    AccessRequestForm,
    AccountProfileForm,
    AccountUserForm,
    AddMemberForm,
    CommunityForm,
    CommunityPrayerSettingsForm,
    EnterInviteCodeForm,
    EntryForm,
    EveningCheckInForm,
    FeedbackForm,
    GoalCompletionFormSet,
    GoalFormSet,
    JoinCommunityForm,
    MomentCheckInForm,
    MorningCheckInForm,
    NotificationSettingsForm,
    PrayerRequestForm,
    SurveyForm,
)
from .models import (
    AccessRequest,
    Community,
    CommunityMembership,
    DevotionalPrompt,
    Entry,
    Feedback,
    IntrospectionPrompt,
    MomentCheckIn,
    MotivationalQuote,
    Prayer,
    PrayerRequest,
    Profile,
    PushSubscription,
    SelfAffirmation,
    StoicPrompt,
    SurveyResponse,
)
from .prayer import purge_expired_prayer_requests, send_due_prayer_digests, send_immediate_prayer_notification
from .weather import (
    get_current_weather,
    get_tomorrow_forecast,
    weather_animation_for_summary,
    weather_location_for_user,
)

JOURNAL_TYPES = {
    "stoic": {"label": "Stoic Reflections", "description": "Guided reflections on Stoic quotes and prompts."},
    "devotional": {"label": "Devotionals", "description": "Scripture-based devotional responses."},
    "freeform": {"label": "Freeform Journal", "description": "Open-ended daily journal entries."},
    "introspection": {"label": "Introspection", "description": "A daily reflection question, one for each day of the year."},
}


@login_not_required
def request_access_view(request):
    if request.method == "POST":
        form = AccessRequestForm(request.POST)
        if form.is_valid():
            access_request = form.save()
            _notify_admin_of_access_request(request, access_request)
            return render(request, "entries/request_access_sent.html")
    else:
        form = AccessRequestForm()
    response = render(request, "entries/request_access.html", {"form": form})
    # This is often filled out on a shared/family device - stop the browser's back/forward
    # cache from restoring a stale copy with the previous person's data still in the fields.
    response["Cache-Control"] = "no-store"
    return response


def _notify_admin_of_access_request(request, access_request):
    context = {
        "access_request": access_request,
        "approve_url": request.build_absolute_uri(
            reverse("access-request-approve", kwargs={"token": access_request.token})
        ),
        "reject_url": request.build_absolute_uri(
            reverse("access-request-reject", kwargs={"token": access_request.token})
        ),
    }
    subject = render_to_string("entries/access_request_admin_subject.txt", context).strip()
    body = render_to_string("entries/access_request_admin_email.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [settings.ADMIN_EMAIL])


@login_not_required
def access_request_approve_view(request, token):
    access_request = get_object_or_404(AccessRequest, token=token)
    if access_request.status == "pending":
        User = get_user_model()
        user = User.objects.create(
            username=access_request.username,
            email=access_request.email,
            password=access_request.password_hash,
            is_active=True,
        )
        Profile.objects.create(
            user=user,
            name=access_request.name,
            date_of_birth=access_request.date_of_birth,
            gender=access_request.gender,
            gender_self_description=access_request.gender_self_description,
            zipcode=access_request.zipcode,
        )
        access_request.status = "approved"
        access_request.decided_at = timezone.now()
        access_request.save()

        context = {"access_request": access_request, "login_url": request.build_absolute_uri(reverse("login"))}
        subject = render_to_string("entries/access_request_approved_subject.txt", context).strip()
        body = render_to_string("entries/access_request_approved_email.txt", context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [access_request.email])

    return render(request, "entries/access_request_outcome.html", {"access_request": access_request, "action": "approved"})


@login_not_required
def access_request_reject_view(request, token):
    access_request = get_object_or_404(AccessRequest, token=token)
    if access_request.status == "pending":
        access_request.status = "rejected"
        access_request.decided_at = timezone.now()
        access_request.save()

        context = {"access_request": access_request}
        subject = render_to_string("entries/access_request_rejected_subject.txt", context).strip()
        body = render_to_string("entries/access_request_rejected_email.txt", context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [access_request.email])

    return render(request, "entries/access_request_outcome.html", {"access_request": access_request, "action": "rejected"})


def account_view(request):
    profile = getattr(request.user, "profile", None) or Profile(user=request.user)
    submitted_form = request.POST.get("form") if request.method == "POST" else None

    if submitted_form == "notifications":
        notification_form = NotificationSettingsForm(request.POST, instance=profile)
        if notification_form.is_valid():
            notification_form.save()
            messages.success(request, "Your notification settings have been updated.")
            return redirect("entries:account")
        user_form = AccountUserForm(instance=request.user)
        profile_form = AccountProfileForm(instance=profile)
    elif submitted_form == "account":
        user_form = AccountUserForm(request.POST, instance=request.user)
        profile_form = AccountProfileForm(request.POST, instance=profile)
        notification_form = NotificationSettingsForm(instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Your account has been updated.")
            return redirect("entries:account")
    else:
        user_form = AccountUserForm(instance=request.user)
        profile_form = AccountProfileForm(instance=profile)
        notification_form = NotificationSettingsForm(instance=profile)

    return render(
        request,
        "entries/account.html",
        {
            "user_form": user_form,
            "profile_form": profile_form,
            "notification_form": notification_form,
            "vapid_public_key": settings.VAPID_PUBLIC_KEY,
        },
    )


@csrf_exempt
@require_POST
def push_subscribe_view(request):
    """Creates/updates a PushSubscription for the signed-in user from the browser's
    PushManager.subscribe() result, posted as JSON by the "Enable notifications on this
    device" button on the account page.

    CSRF-exempt (still login-required via LoginRequiredMiddleware): this is the app's first
    fetch()-based POST, and Django's CSRF protection strictly requires a Referer header on
    HTTPS requests - installed PWAs on Android (running as a Trusted Web Activity) are known
    to sometimes omit/alter it in ways a normal tab doesn't, which 403'd this endpoint for
    real users. Worst case of exempting it is low-severity (an attacker CSRFing a signed-in
    user into pointing their quote notifications at another device), not account compromise
    or data exposure.
    """
    try:
        data = json.loads(request.body)
        endpoint = data["endpoint"]
        p256dh = data["keys"]["p256dh"]
        auth = data["keys"]["auth"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return HttpResponse(status=400)

    PushSubscription.objects.update_or_create(
        endpoint=endpoint, defaults={"user": request.user, "p256dh": p256dh, "auth": auth}
    )
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def push_test_view(request):
    """Sends an immediate test push to every one of the signed-in user's subscriptions, so
    they can confirm delivery works right after opting in rather than waiting for the next
    scheduled morning/evening slot. CSRF-exempt for the same reason as push_subscribe_view."""
    subscriptions = list(request.user.push_subscriptions.all())
    if not subscriptions:
        return JsonResponse({"ok": False, "error": "No subscription registered on this device yet."}, status=400)
    for subscription in subscriptions:
        send_to_subscription(subscription, "The Wax Tablet", "Test notification — push is working!")
    return JsonResponse({"ok": True})


@csrf_exempt
@login_not_required
@require_POST
def send_due_notifications_view(request):
    """Cron target: POST /internal/send-due-quote-notifications/, hit every few minutes by
    the GitHub Actions workflow (see .github/workflows/send-quote-notifications.yml) since
    this app has no in-process scheduler and the Fly machine auto-stops when idle. Not a
    Django-session endpoint - authenticated by a shared secret instead. Also drives the
    community prayer-request digest send and purge on the same tick (see entries/prayer.py) -
    piggybacking here avoids a second every-5-minutes cron workflow/secret."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, settings.CRON_SECRET):
        return HttpResponseForbidden()
    sent = send_due_notifications()
    prayer_digests_sent = send_due_prayer_digests()
    prayer_requests_purged = purge_expired_prayer_requests()
    return JsonResponse(
        {"sent": sent, "prayer_digests_sent": prayer_digests_sent, "prayer_requests_purged": prayer_requests_purged}
    )


@login_not_required
def service_worker_view(request):
    """Serves the service worker JS at the origin root (not under /static/) so its default
    scope is "/" and it can receive push events regardless of which page is open."""
    return render(request, "entries/sw.js", content_type="application/javascript")


def notify_quote_view(request):
    """Landing page for a clicked motivational-quote push notification (see
    entries/push.py's url=f"/notify/quote/?slot={slot}") - shows just that quote,
    nothing else."""
    slot = 2 if request.GET.get("slot") == "2" else 1
    return render(
        request, "entries/notify_quote.html", {"quote": MotivationalQuote.for_date(timezone.localdate(), slot=slot)}
    )


def notify_affirmation_view(request):
    """Landing page for a clicked affirmation push notification - shows just that
    affirmation, nothing else."""
    slot = 2 if request.GET.get("slot") == "2" else 1
    return render(
        request,
        "entries/notify_affirmation.html",
        {"affirmation": SelfAffirmation.for_date(timezone.localdate(), slot=slot)},
    )


def notify_prayer_request_view(request, pk):
    """Landing page for a clicked immediate-prayer-request push notification - shows just
    that one request. 404s for anyone not an active member of its community (the request
    may also already be gone if the community's digest+purge cycle ran before it was clicked)."""
    prayer_request = get_object_or_404(PrayerRequest, pk=pk)
    if not prayer_request.community.memberships.filter(user=request.user, status="active").exists():
        raise Http404
    return render(request, "entries/notify_prayer_request.html", {"prayer_request": prayer_request})


def account_delete_view(request):
    if request.method == "POST":
        user = request.user
        auth_logout(request)
        user.delete()
        messages.success(request, "Your account and all its data have been deleted.")
        return redirect("login")
    return redirect("entries:account")


def dismiss_announcements_view(request):
    if request.method == "POST":
        now = timezone.now()
        profile = getattr(request.user, "profile", None)
        if profile:
            profile.last_seen_announcement_at = now
            profile.save(update_fields=["last_seen_announcement_at"])
        else:
            # No Profile to persist to (e.g. the original admin account) - fall back to
            # the session so dismissal still works instead of the popup reappearing forever.
            request.session[ANNOUNCEMENT_SESSION_KEY] = now.isoformat()

        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = reverse("entries:home")
        return redirect(next_url)
    return redirect("entries:home")


def survey_decline_view(request):
    if request.method == "POST":
        response, _ = SurveyResponse.objects.get_or_create(user=request.user)
        response.declined_at = timezone.now()
        response.save(update_fields=["declined_at"])

        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = reverse("entries:home")
        return redirect(next_url)
    return redirect("entries:home")


def survey_view(request):
    response, _ = SurveyResponse.objects.get_or_create(user=request.user)
    if response.completed_at:
        return render(request, "entries/survey.html", {"already_completed": True, "response": response})

    if request.method == "POST":
        form = SurveyForm(request.POST, instance=response)
        if form.is_valid():
            response = form.save(commit=False)
            response.completed_at = timezone.now()
            response.save()
            messages.success(request, "Thanks for taking the time — your feedback helps shape what's next.")
            return redirect("entries:home")
    else:
        form = SurveyForm(instance=response)
    return render(request, "entries/survey.html", {"form": form})


def feedback_view(request):
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.user = request.user
            feedback.save()
            _notify_admin_of_feedback(request, feedback)
            messages.success(request, "Thanks — your feedback has been sent.")
            return redirect("entries:feedback")
    else:
        form = FeedbackForm()
    return render(request, "entries/feedback.html", {"form": form})


def _notify_admin_of_feedback(request, feedback):
    context = {
        "feedback": feedback,
        "admin_url": request.build_absolute_uri(reverse("admin:entries_feedback_change", args=[feedback.pk])),
    }
    subject = render_to_string("entries/feedback_admin_subject.txt", context).strip()
    body = render_to_string("entries/feedback_admin_email.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [settings.ADMIN_EMAIL])


def _community_list_context(request, **overrides):
    active_community_ids = CommunityMembership.objects.filter(user=request.user, status="active").values_list(
        "community_id", flat=True
    )
    context = {
        "communities": Community.objects.filter(pk__in=active_community_ids).order_by("name"),
        "pending_requests": CommunityMembership.objects.filter(user=request.user, status="pending")
        .select_related("community")
        .order_by("joined_at"),
        "approved_requests": CommunityMembership.objects.filter(user=request.user, status="approved")
        .select_related("community")
        .order_by("joined_at"),
        "create_form": CommunityForm(),
        "join_form": JoinCommunityForm(user=request.user),
        "enter_code_form": EnterInviteCodeForm(user=request.user),
    }
    context.update(overrides)
    return context


def community_list_view(request):
    return render(request, "entries/community_list.html", _community_list_context(request))


def community_admin_agreement_view(request):
    return render(request, "entries/community_admin_agreement.html")


def community_user_agreement_view(request):
    return render(request, "entries/community_user_agreement.html")


@require_POST
def community_create_view(request):
    form = CommunityForm(request.POST)
    if form.is_valid():
        community = form.save(commit=False)
        community.created_by = request.user
        community.admin_agreement_accepted_at = timezone.now()
        community.save()
        CommunityMembership.objects.create(
            community=community, user=request.user, status="active", user_agreement_accepted_at=timezone.now()
        )
        messages.success(request, f'"{community.name}" created — share its invite code to bring others in.')
        return redirect(community.get_absolute_url())
    return render(
        request, "entries/community_list.html", _community_list_context(request, create_form=form, create_open=True)
    )


@require_POST
def community_join_view(request):
    """Step 1 of joining: request access to a community by name - no invite code yet.
    The code only goes out (by email) once the admin approves; see
    community_enter_code_view for the step that completes the join."""
    form = JoinCommunityForm(request.POST, user=request.user)
    if form.is_valid():
        community = form.cleaned_data["community"]
        membership, created = CommunityMembership.objects.get_or_create(
            community=community,
            user=request.user,
            defaults={"status": "pending", "user_agreement_accepted_at": timezone.now()},
        )
        if created:
            messages.success(request, f'Request sent to join "{community.name}" — waiting on admin approval.')
            _notify_admin_of_join_request(request, membership)
        elif membership.status == "pending":
            messages.info(request, f'Your request to join "{community.name}" is still awaiting approval.')
        elif membership.status == "approved":
            messages.info(
                request,
                f'Your request to join "{community.name}" was already approved — check your email for the '
                "invite code, then enter it below.",
            )
        else:
            messages.info(request, f'You\'re already a member of "{community.name}".')
        return redirect("entries:community-list")
    return render(
        request, "entries/community_list.html", _community_list_context(request, join_form=form, join_open=True)
    )


@require_POST
def community_enter_code_view(request):
    """Step 3 of joining: the admin has approved and emailed the code - entering it
    correctly here finally makes the membership active."""
    form = EnterInviteCodeForm(request.POST, user=request.user)
    if form.is_valid():
        community = form.cleaned_data["community"]
        membership = community.memberships.get(user=request.user, status="approved")
        membership.status = "active"
        membership.save(update_fields=["status"])
        messages.success(request, f'You now have access to "{community.name}".')
        return redirect(community.get_absolute_url())
    return render(
        request,
        "entries/community_list.html",
        _community_list_context(request, enter_code_form=form, enter_code_open=True),
    )


def _notify_admin_of_join_request(request, membership):
    community = membership.community
    admin_email = community.created_by.email
    if not admin_email:
        return
    context = {
        "membership": membership,
        "community": community,
        "community_url": request.build_absolute_uri(community.get_absolute_url()),
    }
    subject = render_to_string("entries/community_join_request_admin_subject.txt", context).strip()
    body = render_to_string("entries/community_join_request_admin_email.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [admin_email])


def _send_invite_code_email(membership):
    community = membership.community
    user = membership.user
    if not user.email:
        return
    context = {"community": community, "membership": membership}
    subject = render_to_string("entries/community_access_approved_subject.txt", context).strip()
    body = render_to_string("entries/community_access_approved_email.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])


def community_detail_view(request, pk):
    community = get_object_or_404(request.user.communities, pk=pk)
    membership = community.memberships.get(user=request.user)
    if membership.status == "pending":
        messages.info(request, f'Your request to join "{community.name}" is still awaiting approval.')
        return redirect("entries:community-list")
    if membership.status == "approved":
        messages.info(
            request,
            f'Your request to join "{community.name}" was approved — check your email for the invite code, '
            "then enter it below to finish joining.",
        )
        return redirect("entries:community-list")
    if not membership.user_agreement_accepted_at:
        return render(request, "entries/community_agreement_gate.html", {"community": community})

    is_admin = community.is_admin(request.user)
    context = {
        "community": community,
        "is_admin": is_admin,
        "memberships": community.memberships.filter(status="active").select_related("user").order_by("joined_at"),
        "prayer_request_form": PrayerRequestForm(user=request.user),
        "prayer_requests": community.prayer_requests.select_related("user").order_by("-created_at"),
    }
    if is_admin:
        context["pending_memberships"] = (
            community.memberships.filter(status="pending").select_related("user").order_by("joined_at")
        )
        context["add_member_form"] = AddMemberForm()
        context["prayer_settings_form"] = CommunityPrayerSettingsForm(instance=community)
    return render(request, "entries/community_detail.html", context)


@require_POST
def community_accept_user_agreement_view(request, pk):
    community = get_object_or_404(request.user.communities, pk=pk)
    membership = community.memberships.get(user=request.user)
    membership.user_agreement_accepted_at = timezone.now()
    membership.save(update_fields=["user_agreement_accepted_at"])
    return redirect(community.get_absolute_url())


@require_POST
def community_leave_view(request, pk):
    community = get_object_or_404(request.user.communities, pk=pk)
    membership = community.memberships.get(user=request.user)
    was_active = membership.status == "active"
    membership.delete()
    if was_active:
        messages.success(request, f'You left "{community.name}".')
    else:
        messages.success(request, f'Your request to join "{community.name}" was canceled.')
    return redirect("entries:community-list")


@require_POST
def community_approve_view(request, pk, membership_id):
    community = get_object_or_404(Community, pk=pk, created_by=request.user)
    membership = get_object_or_404(community.memberships, pk=membership_id, status="pending")
    membership.status = "approved"
    membership.save(update_fields=["status"])
    _send_invite_code_email(membership)
    messages.success(request, f'Approved "{membership.user.username}" — the invite code was emailed to them.')
    return redirect(community.get_absolute_url())


@require_POST
def community_reject_view(request, pk, membership_id):
    community = get_object_or_404(Community, pk=pk, created_by=request.user)
    membership = get_object_or_404(community.memberships, pk=membership_id, status="pending")
    messages.info(request, f'Declined "{membership.user.username}"\'s request to join "{community.name}".')
    membership.delete()
    return redirect(community.get_absolute_url())


@require_POST
def community_add_member_view(request, pk):
    community = get_object_or_404(Community, pk=pk, created_by=request.user)
    form = AddMemberForm(request.POST)
    if form.is_valid():
        user = form.user
        membership, created = CommunityMembership.objects.get_or_create(
            community=community, user=user, defaults={"status": "active"}
        )
        if created:
            messages.success(request, f'Added "{user.username}" to "{community.name}".')
        elif membership.status != "active":
            membership.status = "active"
            membership.save(update_fields=["status"])
            messages.success(request, f'Added "{user.username}" into "{community.name}".')
        else:
            messages.info(request, f'"{user.username}" is already a member.')
    else:
        messages.error(request, "; ".join(form.errors.get("username", [])) or "Could not add that user.")
    return redirect(community.get_absolute_url())


@require_POST
def community_prayer_settings_view(request, pk):
    community = get_object_or_404(Community, pk=pk, created_by=request.user)
    form = CommunityPrayerSettingsForm(request.POST, instance=community)
    if form.is_valid():
        form.save()
        messages.success(request, "Prayer digest time updated.")
    else:
        messages.error(request, "Could not update the prayer digest time.")
    return redirect(community.get_absolute_url())


def _safe_next_url(request):
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return reverse("entries:checkin")


@require_POST
def prayer_request_create_view(request):
    next_url = _safe_next_url(request)
    form = PrayerRequestForm(request.POST, user=request.user)
    if form.is_valid():
        prayer_request = form.save()
        if prayer_request.request_type == "immediate":
            send_immediate_prayer_notification(prayer_request)
            messages.success(request, f'Immediate prayer request sent to "{prayer_request.community.name}".')
        else:
            messages.success(
                request, f'Prayer request saved — it will go out in "{prayer_request.community.name}"\'s next digest.'
            )
    else:
        messages.error(request, "; ".join(form.non_field_errors()) or "Could not submit that prayer request.")
    return redirect(next_url)


def _next_stoic_prompt(user):
    active = StoicPrompt.objects.filter(active=True)
    used_ids = Entry.objects.filter(user=user).exclude(stoic_prompt__isnull=True).values_list(
        "stoic_prompt_id", flat=True
    )
    unused = active.exclude(id__in=used_ids)
    # Once every active prompt has appeared in some entry of this user's, the cycle resets.
    pool = unused if unused.exists() else active
    return pool.order_by("?").first()


def _next_devotional_prompt(user=None):
    return DevotionalPrompt.objects.filter(active=True).order_by("?").first()


# journal_type -> (Entry FK field holding its prompt, function picking the next one)
_PROMPT_PICKERS = {
    "stoic": ("stoic_prompt", _next_stoic_prompt),
    "devotional": ("devotional_prompt", _next_devotional_prompt),
}


def _entries_for_journal_type(journal_type, user):
    """All of a user's entries, or entries with non-blank content for one JOURNAL_TYPES section."""
    entries = Entry.objects.filter(user=user)
    if journal_type == "stoic":
        return entries.exclude(stoic_response="")
    if journal_type == "devotional":
        return entries.exclude(devotional_response="")
    if journal_type == "freeform":
        return entries.exclude(freeform_entry="")
    if journal_type == "introspection":
        return entries.exclude(introspection_response="")
    return entries


class EntryListView(TemplateView):
    template_name = "entries/entry_list.html"
    extra_context = {"journal_types": JOURNAL_TYPES}


class JournalTypeListView(ListView):
    model = Entry
    context_object_name = "entries"
    paginate_by = 30
    template_name = "entries/journal_type_list.html"

    def get_queryset(self):
        journal_type = self.kwargs["journal_type"]
        if journal_type not in JOURNAL_TYPES:
            raise Http404
        return _entries_for_journal_type(journal_type, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal_type = self.kwargs["journal_type"]
        context["journal_type"] = journal_type
        context["journal_label"] = JOURNAL_TYPES[journal_type]["label"]
        today_entry = Entry.objects.filter(user=self.request.user, date=timezone.localdate()).first()
        if today_entry and journal_type in _PROMPT_PICKERS:
            field_name, pick_prompt = _PROMPT_PICKERS[journal_type]
            if getattr(today_entry, f"{field_name}_id") is None:
                prompt = pick_prompt(self.request.user)
                if prompt:
                    setattr(today_entry, field_name, prompt)
                    today_entry.save(update_fields=[field_name])

        if today_entry:
            context["new_entry_url"] = f"{reverse('entries:edit', args=[today_entry.pk])}?type={journal_type}"
        else:
            context["new_entry_url"] = f"{reverse('entries:create')}?type={journal_type}"
        return context


class EntryDetailView(DetailView):
    model = Entry
    context_object_name = "entry"

    def get_queryset(self):
        return Entry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bible_attribution"] = settings.BIBLE_VERSION_ATTRIBUTION
        journal_type = self.request.GET.get("type")
        journal_type_info = JOURNAL_TYPES.get(journal_type)
        context["show_entry_saved_modal"] = self.request.GET.get("saved") == "1"
        context["entry_saved_label"] = f"{journal_type_info['label']} entry" if journal_type_info else "journal entry"
        return context


def _resolve_prompt(form, field_name, model):
    pk = form[field_name].value()
    return model.objects.filter(pk=pk).first() if pk else None


def _form_date(form):
    value = form["date"].value()
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value or timezone.localdate()


class EntryFormMixin:
    model = Entry
    form_class = EntryForm
    template_name = "entries/entry_form.html"

    def get_queryset(self):
        return Entry.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.user = self.request.user
        return form

    def _journal_type_param(self):
        value = self.request.GET.get("type") or self.request.POST.get("type")
        return value if value in JOURNAL_TYPES else None

    def get_success_url(self):
        url = self.object.get_absolute_url()
        journal_type = self._journal_type_param()
        if journal_type:
            return f"{url}?saved=1&type={journal_type}"
        return f"{url}?saved=1"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stoic_prompt_obj"] = _resolve_prompt(context["form"], "stoic_prompt", StoicPrompt)
        context["devotional_prompt_obj"] = _resolve_prompt(context["form"], "devotional_prompt", DevotionalPrompt)
        context["form_date"] = _form_date(context["form"])
        context["introspection_prompt_obj"] = IntrospectionPrompt.for_date(context["form_date"])
        context["bible_attribution"] = settings.BIBLE_VERSION_ATTRIBUTION
        context["form_journal_type"] = self._journal_type_param()
        context["active_section"] = context["form_journal_type"] or "stoic"
        return context


class EntryCreateView(EntryFormMixin, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        initial["date"] = self.request.GET.get("date") or timezone.localdate()
        stoic = _next_stoic_prompt(self.request.user)
        devotional = _next_devotional_prompt(self.request.user)
        if stoic:
            initial["stoic_prompt"] = stoic
        if devotional:
            initial["devotional_prompt"] = devotional
        return initial


class EntryUpdateView(EntryFormMixin, UpdateView):
    pass


WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


MOOD_BANDS = [
    (2, 0),    # red: 1-2
    (5, 32),   # orange: 3-5
    (7, 52),   # yellow: 6-7
    (10, 125),  # green: 8-10
]

# Saturation scales with how many of the 4 dimensions have data, so a day
# with one lonely score reads as a faint hint rather than a fully-confident color.
MOOD_MIN_SATURATION = 40
MOOD_MAX_SATURATION = 75
MOOD_LIGHTNESS = 78


CALENDAR_METRICS = {
    "overall": ("Overall", None),
    "physical": ("Physical", "physical_score"),
    "mental": ("Mental", "mental_score"),
    "emotional": ("Emotional", "emotional_score"),
    "spiritual": ("Spiritual", "spiritual_score"),
}
DEFAULT_CALENDAR_METRIC = "overall"


def _mood_color(entry, metric=DEFAULT_CALENDAR_METRIC):
    _, field = CALENDAR_METRICS.get(metric, CALENDAR_METRICS[DEFAULT_CALENDAR_METRIC])
    if field is None:
        dimension_scores = [
            entry.mental_score,
            entry.physical_score,
            entry.emotional_score,
            entry.spiritual_score,
        ]
    else:
        dimension_scores = [getattr(entry, field)]
    present = [s for s in dimension_scores if s is not None]
    if not present:
        return None
    avg = sum(present) / len(present)
    hue = next(hue for ceiling, hue in MOOD_BANDS if avg <= ceiling)
    if len(dimension_scores) > 1:
        saturation = MOOD_MIN_SATURATION + (MOOD_MAX_SATURATION - MOOD_MIN_SATURATION) * (
            len(present) - 1
        ) / (len(dimension_scores) - 1)
    else:
        saturation = MOOD_MAX_SATURATION
    return f"hsl({hue}, {saturation:.0f}%, {MOOD_LIGHTNESS}%)"


def calendar_view(request, year=None, month=None):
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month

    metric = request.GET.get("metric", DEFAULT_CALENDAR_METRIC)
    if metric not in CALENDAR_METRICS:
        metric = DEFAULT_CALENDAR_METRIC

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    entries_by_day = {
        entry.date.day: entry
        for entry in Entry.objects.filter(user=request.user, date__year=year, date__month=month)
        .select_related("stoic_prompt", "devotional_prompt")
        .prefetch_related("goals")
    }

    weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):
        week_days = []
        for day in week:
            if day == 0:
                week_days.append(None)
                continue
            entry = entries_by_day.get(day)
            week_days.append(
                {
                    "day": day,
                    "date": date(year, month, day),
                    "entry": entry,
                    "is_today": date(year, month, day) == today,
                    "bg_color": _mood_color(entry, metric) if entry else None,
                }
            )
        weeks.append(week_days)

    context = {
        "year": year,
        "month": month,
        "month_name": date(year, month, 1).strftime("%B"),
        "weeks": weeks,
        "weekday_labels": WEEKDAY_LABELS,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "metric": metric,
        "metric_choices": [(key, label) for key, (label, _) in CALENDAR_METRICS.items()],
    }
    return render(request, "entries/calendar.html", context)


def _today_entry(user):
    entry, _ = Entry.objects.get_or_create(user=user, date=timezone.localdate())
    return entry


def _daily_quote_for(user, slot):
    """The day's motivational quote for a check-in slot, or None if the user hasn't opted in
    to that slot (master toggle + morning/evening toggle both required)."""
    profile = getattr(user, "profile", None)
    if not profile or not profile.quotes_enabled:
        return None
    enabled = profile.quote_morning_enabled if slot == 1 else profile.quote_evening_enabled
    if not enabled:
        return None
    return MotivationalQuote.for_date(timezone.localdate(), slot=slot)


def _daily_affirmation_for(user, slot):
    """The day's self-affirmation for a check-in slot, or None if the user hasn't opted in
    to that slot (master toggle + morning/evening toggle both required)."""
    profile = getattr(user, "profile", None)
    if not profile or not profile.affirmations_enabled:
        return None
    enabled = profile.affirmation_morning_enabled if slot == 1 else profile.affirmation_evening_enabled
    if not enabled:
        return None
    return SelfAffirmation.for_date(timezone.localdate(), slot=slot)


def _checkin_availability(now):
    """Morning check-in runs 12:01am-12:00pm; evening follow-up is the complement
    (12:01pm-12:00am), so the two windows never overlap and never gap."""
    minutes_since_midnight = now.hour * 60 + now.minute
    morning_available = 1 <= minutes_since_midnight <= 12 * 60
    return morning_available, not morning_available


def _local_now(timezone_name):
    """The current time in a user's own timezone (resolved from their zip code),
    falling back to the server's local time if the zone name is ever unusable."""
    try:
        return timezone.now().astimezone(ZoneInfo(timezone_name))
    except Exception:
        return timezone.localtime()


def checkin_view(request):
    _, _, _, timezone_name = weather_location_for_user(request.user)
    morning_available, _ = _checkin_availability(_local_now(timezone_name))
    return redirect("entries:checkin-morning" if morning_available else "entries:checkin-evening")


def checkin_morning_view(request):
    latitude, longitude, location_name, timezone_name = weather_location_for_user(request.user)
    now = _local_now(timezone_name)
    morning_available, evening_available = _checkin_availability(now)
    if not morning_available:
        return redirect("entries:checkin-evening")

    entry = _today_entry(request.user)
    if not entry.weather_summary:
        summary = get_current_weather(latitude, longitude)
        if summary:
            entry.weather_summary = summary
            entry.save(update_fields=["weather_summary"])

    if request.method == "POST":
        form = MorningCheckInForm(request.POST, instance=entry)
        goal_formset = GoalFormSet(request.POST, instance=entry, prefix="goals")
        if form.is_valid() and goal_formset.is_valid():
            form.save()
            goal_formset.save()
            return redirect(f"{reverse('entries:checkin-morning')}?saved=1")
    else:
        form = MorningCheckInForm(instance=entry)
        goal_formset = GoalFormSet(instance=entry, prefix="goals")

    return render(
        request,
        "entries/checkin_morning.html",
        {
            "entry": entry,
            "form": form,
            "goal_formset": goal_formset,
            "goal_visible_count": max(entry.goals.count(), 1),
            "now": now,
            "morning_available": morning_available,
            "evening_available": evening_available,
            "weather_location": location_name,
            "weather_animation": weather_animation_for_summary(entry.weather_summary),
            "today_prayer": Prayer.for_date(timezone.localdate()),
            "daily_quote": _daily_quote_for(request.user, slot=1),
            "daily_affirmation": _daily_affirmation_for(request.user, slot=1),
            "show_entry_saved_modal": request.GET.get("saved") == "1",
            "entry_saved_label": "morning check-in",
        },
    )


def checkin_evening_view(request):
    latitude, longitude, location_name, timezone_name = weather_location_for_user(request.user)
    now = _local_now(timezone_name)
    morning_available, evening_available = _checkin_availability(now)
    if not evening_available:
        return redirect("entries:checkin-morning")

    entry = _today_entry(request.user)
    if not entry.forecast_summary:
        summary = get_tomorrow_forecast(latitude, longitude)
        if summary:
            entry.forecast_summary = summary
            entry.save(update_fields=["forecast_summary"])

    if request.method == "POST":
        form = EveningCheckInForm(request.POST, instance=entry)
        goal_formset = GoalCompletionFormSet(request.POST, instance=entry, prefix="goals")
        if form.is_valid() and goal_formset.is_valid():
            form.save()
            goal_formset.save()
            return redirect(f"{reverse('entries:checkin-evening')}?saved=1")
    else:
        form = EveningCheckInForm(instance=entry)
        goal_formset = GoalCompletionFormSet(instance=entry, prefix="goals")

    goals = list(entry.goals.all())
    completed = sum(1 for goal in goals if goal.completed)
    percent_complete = round(completed / len(goals) * 100) if goals else None

    return render(
        request,
        "entries/checkin_evening.html",
        {
            "entry": entry,
            "form": form,
            "goal_formset": goal_formset,
            "percent_complete": percent_complete,
            "now": now,
            "morning_available": morning_available,
            "evening_available": evening_available,
            "weather_location": location_name,
            "forecast_animation": weather_animation_for_summary(entry.forecast_summary),
            "today_prayer": Prayer.for_date(timezone.localdate()),
            "daily_quote": _daily_quote_for(request.user, slot=2),
            "daily_affirmation": _daily_affirmation_for(request.user, slot=2),
            "show_entry_saved_modal": request.GET.get("saved") == "1",
            "entry_saved_label": "evening check-in",
        },
    )


def checkin_moment_view(request):
    if request.method == "POST":
        form = MomentCheckInForm(request.POST)
        if form.is_valid():
            MomentCheckIn.objects.create(
                user=request.user,
                emotions=",".join(form.cleaned_data["emotions"]),
                note=form.cleaned_data["note"],
                entry=Entry.objects.filter(user=request.user, date=timezone.localdate()).first(),
                deep_dive_why_1=form.cleaned_data["deep_dive_why_1"],
                deep_dive_why_2=form.cleaned_data["deep_dive_why_2"],
                deep_dive_why_3=form.cleaned_data["deep_dive_why_3"],
                deep_dive_why_4=form.cleaned_data["deep_dive_why_4"],
                deep_dive_why_5=form.cleaned_data["deep_dive_why_5"],
            )
            return redirect("entries:checkin-moment")
    else:
        form = MomentCheckInForm()

    _, _, _, timezone_name = weather_location_for_user(request.user)
    now = _local_now(timezone_name)
    morning_available, evening_available = _checkin_availability(now)

    return render(
        request,
        "entries/checkin_moment.html",
        {
            "form": form,
            "recent_moments": MomentCheckIn.objects.filter(user=request.user)[:10],
            "now": now,
            "morning_available": morning_available,
            "evening_available": evening_available,
            "today_prayer": Prayer.for_date(timezone.localdate()),
        },
    )


def _clean_journal_type(value):
    return value if value in JOURNAL_TYPES else None


class EntryExportSelectView(ListView):
    model = Entry
    context_object_name = "entries"
    template_name = "entries/export_select.html"

    def get_queryset(self):
        return _entries_for_journal_type(_clean_journal_type(self.request.GET.get("type")), self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["journal_types"] = JOURNAL_TYPES
        context["selected_type"] = _clean_journal_type(self.request.GET.get("type")) or ""
        return context


def export_pdf_view(request):
    ids = request.POST.getlist("ids") or request.GET.getlist("ids")
    journal_type = _clean_journal_type(request.POST.get("type") or request.GET.get("type"))
    entries = Entry.objects.filter(user=request.user, pk__in=ids).order_by("date")

    if not entries.exists():
        messages.error(request, "No entries selected to export.")
        return redirect("entries:export")

    html = render_to_string(
        "entries/pdf_export.html",
        {
            "entries": entries,
            "bible_attribution": settings.BIBLE_VERSION_ATTRIBUTION,
            "journal_type": journal_type,
        },
    )

    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)

    start, end = entries.first().date, entries.last().date
    type_prefix = f"{journal_type}_" if journal_type else ""
    filename = (
        f"journal_{type_prefix}{start.isoformat()}.pdf"
        if start == end
        else f"journal_{type_prefix}{start.isoformat()}_to_{end.isoformat()}.pdf"
    )

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
