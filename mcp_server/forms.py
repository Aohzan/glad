"""Form of the API key settings."""

from django import forms
from django.utils.translation import gettext_lazy as _


class ApiKeyForm(forms.Form):
    """A new API key."""

    name = forms.CharField(
        label=_("Name"),
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": _("Claude Code on my laptop")}),
    )
    can_write = forms.BooleanField(
        label=_("Allow writing"),
        required=False,
        help_text=_(
            "Without it, the key only reads the data. With it, the client can "
            "also enter values, expenses, received rents and budget lines."
        ),
    )
