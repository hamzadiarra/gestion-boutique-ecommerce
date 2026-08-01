from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):

    list_display = (
        "nom",
        "categorie",
        "prix",
        "stock",
        "actif",
        "vedette",
    )

    list_filter = (
        "categorie",
        "actif",
        "vedette",
    )

    search_fields = (
        "nom",
        "marque",
    )

    list_editable = (
        "prix",
        "stock",
        "actif",
        "vedette",
    )

    prepopulated_fields = {
        "slug": ("nom",)
    }