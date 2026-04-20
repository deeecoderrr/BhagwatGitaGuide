from django.urls import path

from apps.comments import views

app_name = "comments"

urlpatterns = [
    path("post/", views.post_comment, name="post"),
]
