from django.urls import path

from apps.reviews import views

app_name = "reviews"

urlpatterns = [
    path("<int:pk>/", views.review_document, name="review"),
]
