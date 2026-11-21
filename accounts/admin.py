"""Admin interface for managing accounts."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .forms import ChildForm, child_username
from .models import Child, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for UserProfile."""

    list_display = (
        "user",
        "is_child",
        "birth_date",
        "live_data_enabled",
    )
    list_filter = ("is_child",)
    search_fields = ("user__username", "user__first_name")


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    """Children of the household: owners of assets who cannot log in."""

    form = ChildForm
    list_display = ("first_name", "last_name", "birth_date")
    search_fields = ("first_name", "last_name")
    ordering = ("first_name",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("profile")

    @admin.display(description=_("Birth date"), ordering="profile__birth_date")
    def birth_date(self, obj):
        return obj.profile.birth_date

    def save_model(self, request, obj, form, change):
        if not change:
            obj.username = child_username(obj.first_name)
            obj.set_unusable_password()
        obj.is_staff = obj.is_superuser = False
        super().save_model(request, obj, form, change)
        profile, _created = UserProfile.objects.get_or_create(user=obj)
        profile.is_child = True
        profile.birth_date = form.cleaned_data.get("birth_date")
        profile.save()
