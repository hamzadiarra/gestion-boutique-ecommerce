from django.urls import path
from . import views
from . import vendeur_views
from . import comptable_views

urlpatterns = [
    # Admin Dashboard
    path("", views.admin_dashboard, name="admin_dashboard"),
    path("changer-role/<int:profile_id>/", views.changer_role_utilisateur, name="changer_role_utilisateur"),
    path("utilisateurs/", views.admin_utilisateurs, name="admin_utilisateurs"),
    path("vendeurs/", views.admin_vendeurs, name="admin_vendeurs"),
    path("utilisateurs/<int:profile_id>/", views.admin_utilisateur_detail, name="admin_utilisateur_detail"),
    path("produits/", views.admin_produits, name="admin_produits"),
    path("categories/", views.admin_categories, name="admin_categories"),
    path("commandes/", views.admin_commandes, name="admin_commandes"),
    path("paiements/", views.admin_paiements, name="admin_paiements"),
    path("commandes/<int:commande_id>/statut/", views.admin_commande_statut, name="admin_commande_statut"),
    path("paiements/<int:paiement_id>/statut/", views.admin_paiement_statut, name="admin_paiement_statut"),

    # Dashboard vendeur — Ventes directes
    path("vendeur/", vendeur_views.vendeur_dashboard, name="vendeur_dashboard"),
    path("vendeur/enregistrer-vente/", vendeur_views.enregistrer_vente, name="enregistrer_vente"),
    path("vendeur/historique/", vendeur_views.historique_ventes, name="historique_ventes"),
    path("vendeur/stock/", vendeur_views.vendeur_stock, name="vendeur_stock"),

    # Dashboard vendeur — Gestion des commandes clients
    path("vendeur/commandes/", vendeur_views.vendeur_commandes, name="vendeur_commandes"),
    path("vendeur/commandes/<int:commande_id>/", vendeur_views.vendeur_commande_detail, name="vendeur_commande_detail"),
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
    path("comptable/transactions/", comptable_views.comptable_transactions, name="comptable_transactions"),
    path("comptable/transactions/export/", comptable_views.comptable_export_csv, name="comptable_export_csv"),
    path("comptable/transactions/<str:reference>/", comptable_views.comptable_transaction_detail, name="comptable_transaction_detail"),
    path("comptable/calculs/", comptable_views.comptable_calculs, name="comptable_calculs"),
]
