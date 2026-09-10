from django.contrib import admin
from .models import Vente, JournalActivite
from core.admin import FinancialReadOnlyAdmin, is_superuser


@admin.register(Vente)
class VenteAdmin(FinancialReadOnlyAdmin):
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
    ordering = ("-date_vente",)
    readonly_fields = ("date_vente",)
    list_select_related = ("vendeur", "produit")
    list_per_page = 50


@admin.register(JournalActivite)
class JournalActiviteAdmin(FinancialReadOnlyAdmin):
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
    list_select_related = ("utilisateur",)
    list_per_page = 50

    def has_add_permission(self, request):
        return is_superuser(request.user)

    def has_change_permission(self, request, obj=None):
        return is_superuser(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_superuser(request.user)
