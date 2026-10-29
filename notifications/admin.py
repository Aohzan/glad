"""Admin of the notifications (the channel URLs stay hidden)."""

from django.contrib import admin

from notifications.models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "type_key", "level", "created_at", "read_at")
    list_filter = ("type_key", "level")
    search_fields = ("title", "body")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "type_key", "enabled")
    list_filter = ("type_key", "enabled")
