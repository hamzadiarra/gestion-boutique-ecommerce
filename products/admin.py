from django.contrib import admin
from .models import Product
from core.admin import AdminOnlyAdmin


@admin.action(description="Activer les produits sélectionnés")
def activer_produits(modeladmin, request, queryset):
    queryset.update(actif=True)


@admin.action(description="Désactiver les produits sélectionnés")
def desactiver_produits(modeladmin, request, queryset):
    queryset.update(actif=False)


class ProductAdmin(AdminOnlyAdmin):

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
    list_select_related = ("categorie",)
    readonly_fields = ("quantite_vendue", "date_creation", "date_modification")
    list_per_page = 50
    actions = (activer_produits, desactiver_produits)

    prepopulated_fields = {
        "slug": ("nom",)
    }


admin.site.register(Product, ProductAdmin)
