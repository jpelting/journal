from django.urls import path

from . import views

app_name = "entries"

urlpatterns = [
    path("", views.checkin_view, name="home"),
    path("all/", views.EntryListView.as_view(), name="list"),
    path("all/<str:journal_type>/", views.JournalTypeListView.as_view(), name="journal-type"),
    path("export/", views.EntryExportSelectView.as_view(), name="export"),
    path("export/pdf/", views.export_pdf_view, name="export-pdf"),
    path("new/", views.EntryCreateView.as_view(), name="create"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("calendar/<int:year>/<int:month>/", views.calendar_view, name="calendar"),
    path("checkin/", views.checkin_view, name="checkin"),
    path("checkin/morning/", views.checkin_morning_view, name="checkin-morning"),
    path("checkin/evening/", views.checkin_evening_view, name="checkin-evening"),
    path("checkin/moment/", views.checkin_moment_view, name="checkin-moment"),
    path("account/", views.account_view, name="account"),
    path("account/delete/", views.account_delete_view, name="account-delete"),
    path("feedback/", views.feedback_view, name="feedback"),
    path("community/", views.community_list_view, name="community-list"),
    path("community/admin-agreement/", views.community_admin_agreement_view, name="community-admin-agreement"),
    path("community/user-agreement/", views.community_user_agreement_view, name="community-user-agreement"),
    path("community/create/", views.community_create_view, name="community-create"),
    path("community/join/", views.community_join_view, name="community-join"),
    path("community/enter-code/", views.community_enter_code_view, name="community-enter-code"),
    path("community/<int:pk>/", views.community_detail_view, name="community-detail"),
    path("community/<int:pk>/leave/", views.community_leave_view, name="community-leave"),
    path(
        "community/<int:pk>/accept-user-agreement/",
        views.community_accept_user_agreement_view,
        name="community-accept-user-agreement",
    ),
    path("community/<int:pk>/add-member/", views.community_add_member_view, name="community-add-member"),
    path(
        "community/<int:pk>/requests/<int:membership_id>/approve/",
        views.community_approve_view,
        name="community-approve",
    ),
    path(
        "community/<int:pk>/requests/<int:membership_id>/reject/",
        views.community_reject_view,
        name="community-reject",
    ),
    path(
        "community/<int:pk>/prayer-settings/",
        views.community_prayer_settings_view,
        name="community-prayer-settings",
    ),
    path("prayer-request/", views.prayer_request_create_view, name="prayer-request-create"),
    path("announcements/dismiss/", views.dismiss_announcements_view, name="dismiss-announcements"),
    path("survey/", views.survey_view, name="survey"),
    path("survey/decline/", views.survey_decline_view, name="survey-decline"),
    path("sw.js", views.service_worker_view, name="service-worker"),
    path("push/subscribe/", views.push_subscribe_view, name="push-subscribe"),
    path("push/test/", views.push_test_view, name="push-test"),
    path(
        "internal/send-due-quote-notifications/",
        views.send_due_notifications_view,
        name="send-due-quote-notifications",
    ),
    path("<int:pk>/", views.EntryDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.EntryUpdateView.as_view(), name="edit"),
]
