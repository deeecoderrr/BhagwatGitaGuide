from django.urls import path

from apps.marketing import views

app_name = "marketing"

urlpatterns = [
    path("", views.home, name="home"),
    path("pricing/", views.pricing, name="pricing"),
    path("book-appointment/", views.appointment_book, name="appointment_book"),
]
