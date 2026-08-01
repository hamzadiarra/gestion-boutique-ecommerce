from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "message", "lu", "date_creation")
    list_filter = ("lu", "date_creation")
    search_fields = ("utilisateur__username", "message")
