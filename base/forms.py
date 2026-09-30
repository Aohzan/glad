"""Shared form utilities for the base app."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, cast

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from djmoney.forms.fields import MoneyField

from base.models import Ownership, display_name
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


def date_field(with_class: bool = False) -> forms.DateField:
    """Return a DateField using a date picker widget."""
    attrs: dict[str, str] = {"type": "date"}
    if with_class:
        attrs["class"] = "form-control"
    return forms.DateField(
        widget=forms.DateInput(attrs=attrs, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label=_("Date"),
    )


def recurrence_end_field(with_class: bool = False) -> forms.DateField:
    """Return an optional DateField for a recurrence end date."""
    attrs: dict[str, str] = {"type": "date"}
    if with_class:
        attrs["class"] = "form-control"
    return forms.DateField(
        required=False,
        widget=forms.DateInput(attrs=attrs, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label=_("Recurrence End Date"),
    )


class MonthlyExpensesForm(forms.Form):
    """Monthly household expenses used to size the emergency fund."""

    monthly_expenses = forms.DecimalField(
        label=_("Monthly expenses"),
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "10"}),
    )


class UserChoiceField(forms.ModelChoiceField):
    """Active users, shown by their full name."""

    def label_from_instance(self, obj) -> str:
        return display_name(obj)


class OwnershipForm(forms.ModelForm):
    """Add or update the share of an asset held by a household member."""

    user = UserChoiceField(
        queryset=get_user_model().objects.filter(is_active=True),
        label=_("Owner"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Ownership
        fields = [
            "user",
            "share",
            "right",
            "usufructuary_birth_date",
            "usufruct_end_date",
        ]
        widgets = {
            "share": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "right": forms.Select(attrs={"class": "form-select"}),
            "usufructuary_birth_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
            ),
            "usufruct_end_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, others=(), dismemberable=True, **kwargs):
        """*others* are the other ownership rows of the asset."""
        super().__init__(*args, **kwargs)
        self.others = list(others)
        if not dismemberable:
            for name in ("right", "usufructuary_birth_date", "usufruct_end_date"):
                del self.fields[name]

    def clean(self):
        cleaned = super().clean() or {}
        right = cleaned.get("right", Ownership.Right.FULL)
        share = cleaned.get("share")
        if right != Ownership.Right.FULL and not (
            cleaned.get("usufruct_end_date")
            or cleaned.get("usufructuary_birth_date")
            or (
                right == Ownership.Right.USUFRUCT
                and getattr(
                    getattr(cleaned.get("user"), "profile", None), "birth_date", None
                )
            )
        ):
            raise forms.ValidationError(
                _(
                    "A dismembered right needs the usufruct end date or the birth "
                    "date of the usufructuary."
                )
            )
        if share is not None:
            totals = {right_: Decimal(0) for right_ in Ownership.Right.values}
            for other in self.others:
                totals[other.right] += other.share
            totals[right] += share
            held = totals[Ownership.Right.FULL] + max(
                totals[Ownership.Right.BARE], totals[Ownership.Right.USUFRUCT]
            )
            if held > 100:
                raise forms.ValidationError(_("The shares of the owners exceed 100 %."))
        return cleaned


class BirthDateForm(forms.Form):
    """Birth date of the current user, used to value a life usufruct."""

    birth_date = forms.DateField(
        label=_("My birth date"),
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
        ),
    )
