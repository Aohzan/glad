"""Custom widgets for the base app."""

from django.utils.html import format_html
from djmoney.forms.widgets import MoneyWidget

# Maximum width for the currency <select> inside the input-group.
# Keeps the amount input dominant and the currency selector compact.
_CURRENCY_SELECT_STYLE = "width: 70px; flex: 0 0 70px; min-width: 0;"


class BootstrapMoneyWidget(MoneyWidget):
    """A MoneyWidget that wraps its output in a Bootstrap input-group div.

    This ensures the amount input and currency select are rendered inline
    side by side instead of stacking vertically.  The currency <select> is
    constrained to 150 px so the amount input takes up the remaining space.

    Usage: assign this widget to a MoneyField, or use MoneyInputGroupMixin
    on any form that contains MoneyFields.
    """

    def render(self, name, value, attrs=None, renderer=None):
        # Inject a fixed width on the currency sub-widget so it stays compact.
        currency_widget = self.widgets[1]
        existing_style = currency_widget.attrs.get("style", "")
        if _CURRENCY_SELECT_STYLE not in existing_style:
            currency_widget.attrs["style"] = (
                f"{existing_style} {_CURRENCY_SELECT_STYLE}".strip()
            )
        rendered = super().render(name, value, attrs, renderer=renderer)
        return format_html(
            '<div class="input-group flex-wrap">{}</div>',
            rendered,
        )
