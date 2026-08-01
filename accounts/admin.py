from django.contrib import admin
from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):

    list_display = (
        "utilisateur",
        "role",
        "telephone",
        "ville",
        "date_creation",
    )

    search_fields = (
        "utilisateur__username",
        "utilisateur__email",
        "telephone",
        "ville",
    )

    list_filter = (
        "role",
        "ville",
        "date_creation",
    )

    list_editable = ("role",)
