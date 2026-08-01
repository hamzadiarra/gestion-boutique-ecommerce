from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        "commande",
        "montant",
        "methode",
        "statut",
        "date_creation",
    )

    list_filter = (
        "statut",
        "methode",
    )