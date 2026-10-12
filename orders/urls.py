from django.urls import path
from . import views
from . import delivery_views, proof_views


urlpatterns = [
    path("livraisons/tarifs/", proof_views.tarifs, name="livraison_tarifs"),
    path("livraisons/tarifs/<int:tarif_id>/decision/", proof_views.decision_tarif, name="livraison_decision_tarif"),
    path("livraisons/offres/", proof_views.offres, name="livraison_offres"),
    path("livraisons/supervision/", proof_views.supervision, name="livraison_supervision"),
    path("livraisons/derogations/<int:demande_id>/decision/", proof_views.decision_derogation, name="livraison_decision_derogation"),
    path("livraisons/<int:livraison_id>/signature/", proof_views.signature, name="livraison_signature"),
    path("livraisons/<int:livraison_id>/preuve/", proof_views.preuve, name="livraison_preuve"),
    path("livraisons/<int:livraison_id>/derogation/", proof_views.derogation, name="livraison_derogation"),
    path("livraisons/<int:livraison_id>/retour/", proof_views.retour, name="livraison_retour"),
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
