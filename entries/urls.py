from django.urls import path

from . import views

app_name = "entries"

urlpatterns = [
    path("", views.checkin_view, name="home"),
    path("all/", views.EntryListView.as_view(), name="list"),
    path("all/<str:journal_type>/", views.JournalTypeListView.as_view(), name="journal-type"),
    path("new/", views.EntryCreateView.as_view(), name="create"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("calendar/<int:year>/<int:month>/", views.calendar_view, name="calendar"),
    path("checkin/", views.checkin_view, name="checkin"),
    path("checkin/morning/", views.checkin_morning_view, name="checkin-morning"),
    path("checkin/evening/", views.checkin_evening_view, name="checkin-evening"),
    path("checkin/moment/", views.checkin_moment_view, name="checkin-moment"),
    path("<int:pk>/", views.EntryDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.EntryUpdateView.as_view(), name="edit"),
]
