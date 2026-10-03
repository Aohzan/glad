"""Custom widgets for the base app."""

from django import forms
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


class PeoplePicker(forms.CheckboxSelectMultiple):
    """Checkboxes rendered as a row of toggle buttons, one per person.

    With *with_shares*, each chosen person also gets a share input named
    ``<name>_share_<pk>``, prefilled from *shares* (keyed by primary key).
    """

    template_name = "widgets/people_picker.html"

    def __init__(self, attrs=None, choices=(), *, with_shares=False, shares=None):
        super().__init__(attrs, choices)
        self.with_shares = with_shares
        self.shares = shares or {}

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["with_shares"] = self.with_shares
        return context

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        option["share"] = self.shares.get(str(value), "")
        return option


class SuggestionsTextInput(forms.TextInput):
    """Free text input suggesting the values already stored in the database.

    *sources* are ``(model, field_name)`` pairs. Their distinct non-blank
    values are read when the widget renders and offered through an HTML
    ``<datalist>``, so existing spellings are easy to reuse while any new
    value can still be typed.
    """

    template_name = "widgets/suggestions_input.html"

    def __init__(self, sources, attrs=None):
        super().__init__({"autocomplete": "off", **(attrs or {})})
        self.sources = sources

    def suggestions(self) -> list[str]:
        """Distinct stored values of every source, sorted case-insensitively."""
        values: set[str] = set()
        for model, field in self.sources:
            values.update(
                model._default_manager.exclude(**{f"{field}__isnull": True})
                .values_list(field, flat=True)
                .distinct()
            )
        return sorted({v.strip() for v in values} - {""}, key=str.casefold)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget = context["widget"]
        widget["list_id"] = f"{widget['attrs'].get('id') or name}_suggestions"
        widget["attrs"]["list"] = widget["list_id"]
        widget["suggestions"] = self.suggestions()
        return context
