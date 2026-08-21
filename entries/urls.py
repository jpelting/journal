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
