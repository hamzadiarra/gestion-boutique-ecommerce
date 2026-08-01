from django.contrib import admin
from .models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        'nom',
        'active',
        'date_creation',
    )

    prepopulated_fields = {
        'slug': ('nom',)
    }

    search_fields = (
        'nom',
    )

    list_filter = (
        'active',
    )