from django.contrib import admin
from .models import Notification
from core.admin import AdminOnlyAdmin


@admin.register(Notification)
class NotificationAdmin(AdminOnlyAdmin):
    list_display = ("utilisateur", "titre", "type_notification", "lu", "date_creation")
    list_filter = ("type_notification", "lu", "date_creation")
    search_fields = ("utilisateur__username", "utilisateur__email", "titre", "message")
    list_select_related = ("utilisateur",)
    readonly_fields = ("date_creation",)
    list_per_page = 50
