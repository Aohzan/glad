"""Admin interface for managing accounts."""

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .models import Child, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for UserProfile."""

    list_display = (
        "user",
        "is_child",
        "birth_date",
        "notify_on_login",
        "live_data_enabled",
    )
    list_filter = ("is_child",)
    search_fields = ("user__username", "user__first_name")


def child_username(first_name: str) -> str:
    """Unique username for a child, built from the first name (never used to log in)."""
    base = f"child-{slugify(first_name) or 'member'}"[:140]
    taken = set(
        get_user_model()
        .objects.filter(username__startswith=base)
        .values_list("username", flat=True)
    )
    username, number = base, 1
    while username in taken:
        number += 1
        username = f"{base}-{number}"
    return username


class ChildForm(forms.ModelForm):
    """A child only needs a first name: the other fields are optional."""

    birth_date = forms.DateField(
        label=_("Birth date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    class Meta:
        model = Child
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        profile = getattr(self.instance, "profile", None)
        if profile is not None:
            self.fields["birth_date"].initial = profile.birth_date


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
        profile.notify_on_login = False
        profile.save()
