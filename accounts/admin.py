from django.contrib import admin
from .models import Profile
from core.admin import AdminOnlyAdmin, is_superuser


@admin.register(Profile)
class ProfileAdmin(AdminOnlyAdmin):

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

    list_select_related = ("utilisateur",)
    readonly_fields = ("utilisateur", "date_creation", "date_modification")
    list_per_page = 50

    def has_delete_permission(self, request, obj=None):
        return is_superuser(request.user)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        utilisateur = obj.utilisateur
        if not utilisateur.is_superuser:
            utilisateur.is_staff = obj.role == "admin"
            utilisateur.save(update_fields=("is_staff",))
