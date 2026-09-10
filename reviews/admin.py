from django.contrib import admin
from .models import Review
from core.admin import AdminOnlyAdmin


@admin.register(Review)
class ReviewAdmin(AdminOnlyAdmin):
    list_display = ("produit", "utilisateur", "note", "date_creation")
    list_filter = ("note", "date_creation")
    search_fields = ("produit__nom", "utilisateur__username", "commentaire")
    list_select_related = ("produit", "utilisateur")
    readonly_fields = ("date_creation",)
