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
        "date_creation",
    )

    list_filter = (
        "statut",
        "methode",
        "date_creation",
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
    readonly_fields = ("commande", "montant", "reference", "date_creation", "date_paiement")
    list_per_page = 50
