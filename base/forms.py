"""Shared form utilities for the base app."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from djmoney.forms.fields import MoneyField

from base.widgets import BootstrapMoneyWidget

if TYPE_CHECKING:
    from django.forms import BaseForm


class MoneyInputGroupMixin:
    """Form mixin that replaces every MoneyField widget with BootstrapMoneyWidget.

    Apply as the *first* base class so its __init__ runs before the form's own
    __init__ finishes building the field list:

        class MyForm(MoneyInputGroupMixin, forms.ModelForm):
            ...

    The mixin preserves the existing amount/currency sub-widgets (including any
    custom attrs like ``step``, ``class``, etc.) and only swaps the outer
    MoneyWidget for a BootstrapMoneyWidget that wraps the output in
    ``<div class="input-group">``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form = cast("BaseForm", self)
        for field in form.fields.values():
            if isinstance(field, MoneyField):
                old_widget = field.widget
                field.widget = BootstrapMoneyWidget(
                    amount_widget=old_widget.widgets[0],
                    currency_widget=old_widget.widgets[1],
                    default_currency=old_widget.default_currency,
                )
