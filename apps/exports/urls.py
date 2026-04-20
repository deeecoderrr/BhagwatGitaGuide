from django.urls import path

from apps.exports import views

app_name = "exports"

urlpatterns = [
    path("<int:pk>/pdf/", views.export_pdf, name="create"),
    path("<int:pk>/exports/<int:export_id>/download/", views.download_export, name="download"),
]
