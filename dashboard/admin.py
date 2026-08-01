from django.contrib import admin
from .models import Vente, JournalActivite


@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vendeur",
        "produit",
        "quantite",
        "prix_unitaire",
        "montant_total",
        "methode_paiement",
        "reference_client",
        "date_vente",
    )

    list_filter = (
        "vendeur",
        "methode_paiement",
        "date_vente",
    )

    search_fields = (
        "vendeur__username",
        "produit__nom",
        "reference_client",
    )

    date_hierarchy = "date_vente"
    readonly_fields = ("date_vente",)


@admin.register(JournalActivite)
class JournalActiviteAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "utilisateur",
        "action",
        "niveau",
        "details",
        "adresse_ip",
    )

    list_filter = (
        "action",
        "niveau",
        "utilisateur",
        "date",
    )

    search_fields = (
        "utilisateur__username",
        "details",
        "adresse_ip",
    )

    date_hierarchy = "date"
    readonly_fields = ("date", "utilisateur", "action", "details", "adresse_ip", "niveau")
