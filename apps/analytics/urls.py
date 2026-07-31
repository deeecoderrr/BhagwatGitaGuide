from django.urls import path

from apps.analytics import views

app_name = "analytics"

urlpatterns = [
    path("event/", views.record_event, name="record_event"),
]
