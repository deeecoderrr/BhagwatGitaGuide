from django.urls import path

from apps.support_chat import views

app_name = "support_chat"

urlpatterns = [
    path("", views.thread_list, name="list"),
    path("new/", views.thread_new, name="new"),
    path("<int:pk>/", views.thread_detail, name="thread"),
    path("<int:pk>/poll/", views.thread_poll, name="thread_poll"),
    path("staff/inbox/", views.staff_inbox, name="staff_inbox"),
    path("staff/<int:pk>/", views.staff_thread, name="staff_thread"),
]
