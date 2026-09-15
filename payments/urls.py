from django.urls import path
from . import views


urlpatterns = [
    path("online/start/<int:order_id>/", views.start_online_payment, name="start_online_payment"),
    path("online/return/", views.online_payment_return, name="online_payment_return"),
    path("online/cancel/", views.online_payment_cancel, name="online_payment_cancel"),
    path("webhooks/flutterwave/", views.online_payment_webhook, name="online_payment_webhook"),
    path("webhooks/cinetpay/", views.cinetpay_webhook, name="cinetpay_webhook"),

    path("wave/success/<int:order_id>/", views.wave_payment_success, name="wave_payment_success"),
    path("wave/error/<int:order_id>/", views.wave_payment_error, name="wave_payment_error"),

    path(
        "<int:order_id>/",
        views.payment_form,
        name="payment_form"
    ),
    path(
        "moov/callback/<int:order_id>/",
        views.moov_money_callback,
        name="moov_money_callback",
    ),
    path(
        "webhooks/moov-money/",
        views.moov_money_webhook,
        name="moov_money_webhook",
    ),

]
