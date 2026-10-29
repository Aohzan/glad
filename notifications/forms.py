"""Forms of the notification settings."""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from notifications.registry import NotificationType


class ChannelForm(forms.Form):
    """A new notification channel."""

    name = forms.CharField(label=_("Name"), max_length=100)
    url = forms.CharField(
        label=_("Apprise URL"),
        max_length=2000,
        widget=forms.TextInput(attrs={"placeholder": "ntfy://ntfy.sh/my-topic"}),
        help_text=_(
            "For example ntfy://, gotify://, tgram://, discord:// or mailto://."
        ),
    )

    def clean_url(self) -> str:
        url = self.cleaned_data["url"].strip()
        import apprise  # imported when checking: the library is large

        if not apprise.Apprise().add(url):
            raise ValidationError(_("This is not a valid Apprise URL."))
        return url


def clean_preferences(
    data, notification_types: list[NotificationType], channel_ids: set[int]
) -> tuple[dict[str, dict], dict[str, str]]:
    """Read the submitted preferences of every type.

    Returns the cleaned values (``enabled``, ``params``, ``channels``) by type
    key, and the errors by field name.
    """
    cleaned: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for notification_type in notification_types:
        key = notification_type.key
        params = {}
        for param in notification_type.params:
            field = f"{key}-{param.key}"
            try:
                params[param.key] = param.clean(data.get(field, ""))
            except ValidationError as exc:
                errors[field] = " ".join(exc.messages)
        channels = set()
        for raw in data.getlist(f"{key}-channels"):
            try:
                channel_id = int(raw)
            except ValueError:
                continue
            if channel_id in channel_ids:
                channels.add(channel_id)
        cleaned[key] = {
            "enabled": data.get(f"{key}-enabled") == "on",
            "params": params,
            "channels": channels,
        }
    return cleaned, errors
