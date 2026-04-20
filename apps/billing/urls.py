from django.urls import path

from apps.billing import views

app_name = "billing"

urlpatterns = [
    path("checkout/", views.checkout_pro, name="checkout"),
    path("success/", views.payment_success, name="payment_success"),
    path("webhook/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
]
