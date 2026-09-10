from django.contrib import admin
from .models import Order, OrderItem
from core.admin import AdminOnlyAdmin, FinancialReadOnlyAdmin, is_superuser, user_role


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("produit", "quantite", "prix")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return is_superuser(request.user)

    def has_change_permission(self, request, obj=None):
        return is_superuser(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_superuser(request.user)


@admin.register(Order)
class OrderAdmin(AdminOnlyAdmin):
    list_display = (
        "id",
        "utilisateur",
        "statut",
        "mode_livraison",
        "admin_payment_status",
        "date_creation",
    )
    list_filter = ("statut", "mode_livraison", "date_creation")
    search_fields = (
        "=id",
        "utilisateur__username",
        "utilisateur__email",
        "adresse_livraison",
    )
    date_hierarchy = "date_creation"
    ordering = ("-date_creation",)
    list_select_related = ("utilisateur", "vendeur_confirmateur", "payment")
    readonly_fields = (
        "date_creation",
        "date_confirmation",
        "date_expedition",
        "date_livraison",
        "date_annulation",
        "vendeur_confirmateur",
    )
    inlines = (OrderItemInline,)
    list_per_page = 50

    @admin.display(description="Paiement")
    def admin_payment_status(self, obj):
        try:
            payment = obj.payment
        except Order.payment.RelatedObjectDoesNotExist:
            payment = None
        return payment.get_statut_display() if payment else "Aucun"

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        # Les transitions métier (confirmation, expédition, livraison,
        # annulation et leurs dates/stock) restent pilotées par l'espace vendeur.
        # Seul le superuser garde le pouvoir de correction exceptionnelle.
        if not is_superuser(request.user):
            fields.append("statut")
        return tuple(fields)
