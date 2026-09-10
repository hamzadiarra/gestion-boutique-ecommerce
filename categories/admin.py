from django.contrib import admin
from .models import Category
from core.admin import AdminOnlyAdmin


@admin.register(Category)
class CategoryAdmin(AdminOnlyAdmin):
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
    list_per_page = 50
