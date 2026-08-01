from django.urls import path
from . import views
from . import vendeur_views
from . import comptable_views

urlpatterns = [
    # Admin Dashboard
    path("", views.admin_dashboard, name="admin_dashboard"),
    path("changer-role/<int:profile_id>/", views.changer_role_utilisateur, name="changer_role_utilisateur"),

    # Dashboard vendeur — Ventes directes
    path("vendeur/", vendeur_views.vendeur_dashboard, name="vendeur_dashboard"),
    path("vendeur/enregistrer-vente/", vendeur_views.enregistrer_vente, name="enregistrer_vente"),
    path("vendeur/historique/", vendeur_views.historique_ventes, name="historique_ventes"),

    # Dashboard vendeur — Gestion des commandes clients
    path("vendeur/commandes/", vendeur_views.vendeur_commandes, name="vendeur_commandes"),
    path("vendeur/commandes/<int:commande_id>/confirmer/", vendeur_views.confirmer_commande, name="confirmer_commande"),

    # Dashboard vendeur — Gestion des produits
    path("vendeur/produits/", vendeur_views.vendeur_liste_produits, name="vendeur_liste_produits"),
    path("vendeur/produits/ajouter/", vendeur_views.vendeur_ajouter_produit, name="vendeur_ajouter_produit"),
    path("vendeur/produits/<int:produit_id>/modifier/", vendeur_views.vendeur_modifier_produit, name="vendeur_modifier_produit"),
    path("vendeur/produits/<int:produit_id>/toggle/", vendeur_views.vendeur_toggle_produit, name="vendeur_toggle_produit"),

    # Dashboard vendeur — Paniers clients
    path("vendeur/paniers/", vendeur_views.vendeur_paniers, name="vendeur_paniers"),

    # Dashboard Comptable
    path("comptable/", comptable_views.comptable_dashboard, name="comptable_dashboard"),
    path("comptable/calculs/", comptable_views.comptable_calculs, name="comptable_calculs"),
]
