from django.urls import path

from apps.documents import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("beta-try/", views.beta_try_upload, name="beta_try"),
    path("upload/", views.document_upload, name="upload"),
    path("<int:pk>/", views.document_detail, name="detail"),
    path("<int:pk>/status/", views.document_status, name="status"),
    path("<int:pk>/reprocess/", views.document_reprocess, name="reprocess"),
]
