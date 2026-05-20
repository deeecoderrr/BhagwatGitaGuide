from django.urls import path

from apps.billing import views

app_name = "billing"

urlpatterns = [
    path("checkout/<str:bundle>/", views.checkout_bundle, name="checkout_bundle"),
    path("success/", views.payment_success, name="payment_success"),
    path("webhook/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
    path("guest-checkout/", views.guest_checkout, name="guest_checkout"),
    path("guest-success/", views.guest_payment_success, name="guest_payment_success"),
]
