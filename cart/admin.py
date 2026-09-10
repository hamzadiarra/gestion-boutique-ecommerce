from django.contrib import admin
from .models import Cart, CartItem
from core.admin import AdminOnlyAdmin


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(AdminOnlyAdmin):
    list_display = (
        "utilisateur",
        "date_creation",
    )

    inlines = [CartItemInline]
    list_select_related = ("utilisateur",)
    list_per_page = 50


@admin.register(CartItem)
class CartItemAdmin(AdminOnlyAdmin):
    list_display = (
        "panier",
        "produit",
        "quantite",
        "prix",
    )
    list_select_related = ("panier", "produit")
