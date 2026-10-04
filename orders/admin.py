from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "utilisateur",
        "statut",
        "date_creation",
    )

    list_filter = (
        "statut",
        "date_creation",
    )

    search_fields = (
        "utilisateur__username",
        "id",
    )

    list_editable = (
        "statut",
    )

    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "commande",
        "produit",
        "quantite",
        "prix",
    )

    list_editable = (
        "quantite",
        "prix",
    )
