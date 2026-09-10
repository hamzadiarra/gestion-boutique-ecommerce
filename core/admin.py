from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User

# Les modèles SiteSetting et ContactMessage ne sont pas encore définis.
# Cet fichier est réservé pour de futurs enregistrements admin.


def user_role(user):
    """Retourne le rôle applicatif sans lever d'erreur pour un profil absent."""
    profile = getattr(user, "profile", None)
    return getattr(profile, "role", None)


def is_superuser(user):
    return bool(getattr(user, "is_superuser", False))


def is_admin_role(user):
    return is_superuser(user) or user_role(user) == "admin"


def is_financial_role(user):
    return is_admin_role(user) or user_role(user) == "comptable"


def admin_site_has_permission(request):
    """Bloque l'entrée /admin/ pour les comptes non autorisés côté serveur."""
    user = request.user
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    if is_superuser(user):
        return True
    return bool(getattr(user, "is_staff", False) and user_role(user) in {"admin", "comptable"})


# L'URL existante continue d'utiliser admin.site.urls : on durcit le site
# existant sans le remplacer ni modifier sa configuration visuelle.
admin.site.has_permission = admin_site_has_permission


class RoleRestrictedAdmin(admin.ModelAdmin):
    """Contrôle serveur commun aux ModelAdmin de l'application."""

    allowed_roles = ("admin",)

    def role_allowed(self, request):
        return is_superuser(request.user) or user_role(request.user) in self.allowed_roles

    def has_module_permission(self, request):
        return self.role_allowed(request)

    def has_view_permission(self, request, obj=None):
        return self.role_allowed(request)

    def has_add_permission(self, request):
        return self.role_allowed(request)

    def has_change_permission(self, request, obj=None):
        return self.role_allowed(request)

    def has_delete_permission(self, request, obj=None):
        return self.role_allowed(request)

    def get_queryset(self, request):
        return super().get_queryset(request)


class AdminOnlyAdmin(RoleRestrictedAdmin):
    allowed_roles = ("admin",)


class FinancialReadOnlyAdmin(RoleRestrictedAdmin):
    allowed_roles = ("admin", "comptable")

    def has_add_permission(self, request):
        return is_superuser(request.user)

    def has_change_permission(self, request, obj=None):
        return is_superuser(request.user) or user_role(request.user) == "admin"

    def has_delete_permission(self, request, obj=None):
        return is_superuser(request.user)


class RestrictedUserAdmin(AdminOnlyAdmin, UserAdmin):
    list_display = UserAdmin.list_display + ("admin_profile_role",)
    list_select_related = ("profile",)
    list_per_page = 50

    @admin.display(description="Rôle", ordering="profile__role")
    def admin_profile_role(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.get_role_display() if profile else "—"

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not is_superuser(request.user):
            fields.extend(field for field in ("is_staff", "is_superuser") if field not in fields)
        return tuple(fields)

    def has_delete_permission(self, request, obj=None):
        return is_superuser(request.user)


class RestrictedGroupAdmin(AdminOnlyAdmin, GroupAdmin):
    pass


if User in admin.site._registry:
    admin.site.unregister(User)
admin.site.register(User, RestrictedUserAdmin)
if Group in admin.site._registry:
    admin.site.unregister(Group)
admin.site.register(Group, RestrictedGroupAdmin)

