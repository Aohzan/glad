"""Admin interface for managing accounts."""

from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for UserProfile."""

    list_display = ("user", "notify_on_login", "live_data_enabled")
    search_fields = ("user__username",)
