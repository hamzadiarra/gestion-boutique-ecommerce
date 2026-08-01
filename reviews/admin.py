from django.contrib import admin
from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("produit", "utilisateur", "note", "date_creation")
    list_filter = ("note", "date_creation")
    search_fields = ("produit__nom", "utilisateur__username", "commentaire")
