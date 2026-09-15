from django.urls import path

from . import views
from . import vendeur_views
from . import comptable_views
from . import depense_views
from . import finance_views
from . import cloture_views
from orders import delivery_views


urlpatterns = [
    path("livreur/", delivery_views.livreur_dashboard, name="livreur_dashboard"),
    path("livraisons/", delivery_views.boutique_livraisons, name="boutique_livraisons"),
    path("comptable/clotures/", cloture_views.liste, name="comptable_clotures"),
    path("comptable/clotures/nouvelle/", cloture_views.formulaire, name="comptable_cloture_nouvelle"),
    path("comptable/clotures/export/", cloture_views.export, name="comptable_clotures_export"),
    path("comptable/clotures/<int:cloture_id>/", cloture_views.detail, name="comptable_cloture_detail"),
    path("comptable/clotures/<int:cloture_id>/modifier/", cloture_views.formulaire, name="comptable_cloture_modifier"),
    path("comptable/clotures/<int:cloture_id>/valider/", cloture_views.transition, {"target": "validee"}, name="comptable_cloture_valider"),
    path("comptable/clotures/<int:cloture_id>/annuler/", cloture_views.transition, {"target": "annulee"}, name="comptable_cloture_annuler"),
    path("comptable/clotures/<int:cloture_id>/justificatif/", cloture_views.justificatif, name="comptable_cloture_justificatif"),
    path("comptable/comptes/", finance_views.comptes, name="comptable_comptes"),
    path("comptable/comptes/nouveau/", finance_views.compte_form, name="comptable_compte_nouveau"),
    path("comptable/comptes/<int:compte_id>/", finance_views.journal, name="comptable_compte_detail"),
    path("comptable/comptes/<int:compte_id>/modifier/", finance_views.compte_form, name="comptable_compte_modifier"),
    path("comptable/comptes/<int:compte_id>/toggle/", finance_views.compte_toggle, name="comptable_compte_toggle"),
    path("comptable/mouvements/", finance_views.journal, name="comptable_mouvements"),
    path("comptable/mouvements/export/", finance_views.export, name="comptable_mouvements_export"),
    path("comptable/transferts/nouveau/", finance_views.operation, {"kind": "transfert"}, name="comptable_transfert_nouveau"),
    path("comptable/ajustements/nouveau/", finance_views.operation, {"kind": "ajustement"}, name="comptable_ajustement_nouveau"),
    path("comptable/regularisations/", finance_views.regularisations, name="comptable_regularisations"),
    path("comptable/regularisations/<int:mouvement_id>/affecter/", finance_views.affecter, name="comptable_regularisation_affecter"),

    path("comptable/depenses/", depense_views.comptable_depenses, name="comptable_depenses"),
    path("comptable/depenses/nouvelle/", depense_views.comptable_depense_nouvelle, name="comptable_depense_nouvelle"),
    path("comptable/depenses/export/", depense_views.comptable_depenses_export_csv, name="comptable_depenses_export_csv"),
    path("comptable/depenses/categories/", depense_views.comptable_depense_categories, name="comptable_depense_categories"),
    path("comptable/depenses/categories/<int:categorie_id>/toggle/", depense_views.comptable_depense_categorie_toggle, name="comptable_depense_categorie_toggle"),
    path("comptable/depenses/<int:depense_id>/", depense_views.comptable_depense_detail, name="comptable_depense_detail"),
    path("comptable/depenses/<int:depense_id>/modifier/", depense_views.comptable_depense_modifier, name="comptable_depense_modifier"),
    path("comptable/depenses/<int:depense_id>/valider/", depense_views.comptable_depense_valider, name="comptable_depense_valider"),
    path("comptable/depenses/<int:depense_id>/annuler/", depense_views.comptable_depense_annuler, name="comptable_depense_annuler"),
    path("comptable/depenses/<int:depense_id>/justificatif/", depense_views.comptable_depense_justificatif, name="comptable_depense_justificatif"),

    # =========================================================
    # ADMIN
    # =========================================================

    path(
        "",
        views.admin_dashboard_v2,
        name="admin_dashboard"
    ),

    path(
        "changer-role/<int:profile_id>/",
        views.changer_role_utilisateur,
        name="changer_role_utilisateur"
    ),

    path(
        "utilisateurs/",
        views.admin_utilisateurs,
        name="admin_utilisateurs"
    ),

    path(
        "vendeurs/",
        views.admin_vendeurs,
        name="admin_vendeurs"
    ),

    path(
        "vendeurs/performance/",
        views.admin_vendeurs_performance,
        name="admin_vendeurs_performance"
    ),

    path(
        "vendeurs/<int:profile_id>/performance/",
        views.admin_vendeur_performance_detail,
        name="admin_vendeur_performance_detail"
    ),

    path("alertes/", views.admin_alertes, name="admin_alertes"),
    path("activites/", views.admin_activites, name="admin_activites"),
    path("clients/", views.admin_clients, name="admin_clients"),
    path("parametres/", views.admin_parametres, name="admin_parametres"),

    path(
        "utilisateurs/<int:profile_id>/",
        views.admin_utilisateur_detail,
        name="admin_utilisateur_detail"
    ),

    path(
        "produits/",
        views.admin_produits,
        name="admin_produits"
    ),

    path(
        "categories/",
        views.admin_categories,
        name="admin_categories"
    ),

    path(
        "commandes/",
        views.admin_commandes,
        name="admin_commandes"
    ),

    path(
        "paiements/",
        views.admin_paiements,
        name="admin_paiements"
    ),

    path(
        "commandes/<int:commande_id>/statut/",
        views.admin_commande_statut,
        name="admin_commande_statut"
    ),

    path(
        "paiements/<int:paiement_id>/statut/",
        views.admin_paiement_statut,
        name="admin_paiement_statut"
    ),


    # =========================================================
    # VENDEUR — DASHBOARD
    # =========================================================

    path(
        "vendeur/",
        vendeur_views.vendeur_dashboard,
        name="vendeur_dashboard"
    ),


    # =========================================================
    # VENDEUR — VENTES DIRECTES / COMPTOIR
    # =========================================================

    path(
        "vendeur/enregistrer-vente/",
        vendeur_views.enregistrer_vente,
        name="enregistrer_vente"
    ),

    # Reçu d'une vente physique / comptoir
    path(
        "vendeur/ventes/<int:vente_id>/recu/",
        vendeur_views.vendeur_vente_recu,
        name="vendeur_vente_recu"
    ),

    path(
        "vendeur/historique/",
        vendeur_views.historique_ventes,
        name="historique_ventes"
    ),


    # =========================================================
    # VENDEUR — STOCK
    # =========================================================

    path(
        "vendeur/stock/",
        vendeur_views.vendeur_stock,
        name="vendeur_stock"
    ),


    # =========================================================
    # VENDEUR — COMMANDES CLIENTS / E-COMMERCE
    # =========================================================

    path(
        "vendeur/commandes/",
        vendeur_views.vendeur_commandes,
        name="vendeur_commandes"
    ),

    path(
        "vendeur/commandes/<int:commande_id>/",
        vendeur_views.vendeur_commande_detail,
        name="vendeur_commande_detail"
    ),

    # Confirmation / rejet / expédition / livraison / annulation
    path(
        "vendeur/commandes/<int:commande_id>/confirmer/",
        vendeur_views.confirmer_commande,
        name="confirmer_commande"
    ),


    # =========================================================
    # VENDEUR — CATÉGORIES
    # =========================================================

    # Création rapide d'une catégorie depuis le formulaire produit
    path(
        "vendeur/categories/ajouter/",
        vendeur_views.vendeur_ajouter_categorie,
        name="vendeur_ajouter_categorie"
    ),


    # =========================================================
    # VENDEUR — PRODUITS
    # =========================================================

    path(
        "vendeur/produits/",
        vendeur_views.vendeur_liste_produits,
        name="vendeur_liste_produits"
    ),

    path(
        "vendeur/produits/ajouter/",
        vendeur_views.vendeur_ajouter_produit,
        name="vendeur_ajouter_produit"
    ),

    path(
        "vendeur/produits/<int:produit_id>/modifier/",
        vendeur_views.vendeur_modifier_produit,
        name="vendeur_modifier_produit"
    ),

    path(
        "vendeur/produits/<int:produit_id>/toggle/",
        vendeur_views.vendeur_toggle_produit,
        name="vendeur_toggle_produit"
    ),


    # =========================================================
    # VENDEUR — PANIERS CLIENTS
    # =========================================================

    path(
        "vendeur/paniers/",
        vendeur_views.vendeur_paniers,
        name="vendeur_paniers"
    ),


    # =========================================================
    # COMPTABLE
    # =========================================================

    path(
        "comptable/",
        comptable_views.comptable_dashboard,
        name="comptable_dashboard"
    ),

    path(
        "comptable/transactions/",
        comptable_views.comptable_transactions,
        name="comptable_transactions"
    ),

    path(
        "comptable/transactions/export/",
        comptable_views.comptable_export_csv,
        name="comptable_export_csv"
    ),

    path(
        "comptable/transactions/<str:reference>/",
        comptable_views.comptable_transaction_detail,
        name="comptable_transaction_detail"
    ),

    path(
        "comptable/calculs/",
        comptable_views.comptable_calculs,
        name="comptable_calculs"
    ),
]
