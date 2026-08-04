from django.urls import path

from . import views

app_name = "entries"

urlpatterns = [
    path("", views.EntryListView.as_view(), name="list"),
    path("new/", views.EntryCreateView.as_view(), name="create"),
    path("<int:pk>/", views.EntryDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.EntryUpdateView.as_view(), name="edit"),
]
