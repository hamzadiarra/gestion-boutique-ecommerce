from django.contrib import admin
from .models import Payment
from core.admin import FinancialReadOnlyAdmin


@admin.register(Payment)
class PaymentAdmin(FinancialReadOnlyAdmin):

    list_display = (
        "commande",
        "montant",
        "methode",
        "statut",
        "reference",
        "provider",
        "provider_reference",
        "provider_status",
        "date_creation",
    )

    list_filter = (
        "statut",
        "methode",
        "date_creation",
        "provider",
    )

    search_fields = (
        "reference",
        "=commande__id",
        "commande__utilisateur__username",
        "commande__utilisateur__email",
    )
    date_hierarchy = "date_creation"
    ordering = ("-date_creation",)
    list_select_related = ("commande", "commande__utilisateur")
    readonly_fields = ("commande", "montant", "reference", "provider", "provider_reference", "provider_status", "provider_payload", "date_creation", "date_paiement", "date_confirmation")
    list_per_page = 50
