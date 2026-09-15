from django.urls import path
from . import views
from . import delivery_views


urlpatterns = [
    path("<int:order_id>/livraison/", delivery_views.order_delivery, name="order_delivery"),
    path("<int:order_id>/livraison/initialiser/", delivery_views.initialiser, name="livraison_initialiser"),
    path("livraisons/<int:livraison_id>/", delivery_views.detail, name="livraison_detail"),
    path("livraisons/<int:livraison_id>/affecter/", delivery_views.affecter, name="livraison_affecter"),
    path("livraisons/<int:livraison_id>/action/", delivery_views.action, name="livraison_action"),
    path("livraisons/<int:livraison_id>/message/", delivery_views.message, name="livraison_message"),

    path(
        "create/",
        views.create_order,
        name="create_order"
    ),

    path(
        "my-orders/",
        views.my_orders,
        name="my_orders"
    ),

    # Reçu officiel d'une commande confirmée
    path(
        "<int:id>/receipt/",
        views.order_receipt,
        name="order_receipt"
    ),

    path(
        "<int:id>/",
        views.order_detail,
        name="order_detail"
    ),

]
