"""Shared form utilities for the base app."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import cast

from django import forms
from django.utils.translation import gettext_lazy as _
from djmoney.forms.fields import MoneyField

from base.models import Ownership, display_name, household_members
from base.services.ownership import (
    MIN_SHARE,
    NoShareLeftError,
    OwnersPlan,
    apply_owners,
    ownerships_of,
    plan_owners,
    plan_shares,
)
from base.widgets import BootstrapMoneyWidget, PeoplePicker


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
        form = cast(forms.BaseForm, self)
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


class PeopleField(forms.ModelMultipleChoiceField):
    """One or several household members, picked as toggle buttons."""

    widget = PeoplePicker

    def __init__(self, **kwargs):
        super().__init__(queryset=household_members(), **kwargs)

    def label_from_instance(self, obj) -> str:
        return display_name(obj)


def _share_text(share: Decimal) -> str:
    """A share as typed in its input: ``50`` or ``33.33``."""
    text = f"{share.quantize(MIN_SHARE):f}"
    return text.rstrip("0").rstrip(".")


class OwnersFormMixin:
    """Form mixin choosing the household members who own the saved assets.

    Apply it before ``forms.ModelForm``. At least one owner is required. Each
    chosen member gets a share, an equal split by default; the shares are
    left to :func:`plan_owners` when an asset carries a dismembered right,
    which is set on the owners page. *owners_after* names the field the owners
    are shown after.
    """

    owners_after: str | None = None

    def owned_assets(self) -> list:
        """Assets whose owners the form sets: the edited instance by default."""
        return [cast(forms.BaseModelForm, self).instance]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form = cast(forms.BaseModelForm, self)
        self.owner_rows = [
            (asset, ownerships_of(asset) if asset.pk else [])
            for asset in self.owned_assets()
        ]
        self.owners_plans: list[tuple[object, OwnersPlan]] = []
        if not self.owner_rows:
            return
        rows = [row for _asset, asset_rows in self.owner_rows for row in asset_rows]
        self.owners_with_shares = all(row.right == Ownership.Right.FULL for row in rows)
        users = list({row.user_id: row.user for row in rows}.values())  # ty: ignore[unresolved-attribute]
        name = form.add_prefix("owners")
        if form.is_bound:
            shares = {
                key.removeprefix(f"{name}_share_"): value
                for key, value in form.data.items()
                if key.startswith(f"{name}_share_")
            }
        else:
            # The shares are shown when every asset splits them the same way.
            splits = {
                frozenset((row.user_id, row.share) for row in asset_rows)  # ty: ignore[unresolved-attribute]
                for _asset, asset_rows in self.owner_rows
            }
            shares = (
                {str(pk): _share_text(share) for pk, share in splits.pop()}
                if len(splits) == 1
                else {}
            )
        owners = PeopleField(
            label=_("Owners"),
            initial=users,
            widget=PeoplePicker(with_shares=self.owners_with_shares, shares=shares),
            help_text=_(
                "Share of each owner, in percent; the rest is held outside the household."
            )
            if self.owners_with_shares
            else _(
                "New owners share the full ownership equally; set the shares of a "
                "dismembered asset on the owners page."
            ),
            error_messages={"required": _("Choose at least one owner.")},
        )
        fields = list(form.fields.items())
        names = [field_name for field_name, _field in fields]
        position = (
            names.index(self.owners_after) + 1
            if self.owners_after in names
            else len(fields)
        )
        fields.insert(position, ("owners", owners))
        form.fields = dict(fields)

    def _posted_shares(self, owners) -> dict | None:
        """Share typed for each owner, None when none is typed."""
        form = cast(forms.BaseModelForm, self)
        name = form.add_prefix("owners")
        texts = {
            user: str(form.data.get(f"{name}_share_{user.pk}", "")).strip()
            for user in owners
        }
        if not any(texts.values()):
            return None
        shares = {}
        for user, text in texts.items():
            try:
                share = Decimal(text.replace(",", ".")).quantize(MIN_SHARE)
            except InvalidOperation:
                raise forms.ValidationError(
                    _("Enter the share of every owner, between 0.01 and 100.")
                ) from None
            if not MIN_SHARE <= share <= 100:
                raise forms.ValidationError(
                    _("Enter the share of every owner, between 0.01 and 100.")
                )
            shares[user] = share
        if sum(shares.values()) > 100:
            raise forms.ValidationError(_("The shares of the owners exceed 100 %."))
        return shares

    def clean_owners(self):
        owners = cast(forms.BaseModelForm, self).cleaned_data["owners"]
        shares = self._posted_shares(owners) if self.owners_with_shares else None
        try:
            self.owners_plans = [
                (
                    asset,
                    plan_owners(rows, owners)
                    if shares is None
                    else plan_shares(rows, shares),
                )
                for asset, rows in self.owner_rows
            ]
        except NoShareLeftError:
            raise forms.ValidationError(
                _(
                    "The other rights leave no share to the new owners: set the "
                    "shares on the owners page."
                )
            ) from None
        return owners

    def _save_m2m(self):
        super()._save_m2m()  # ty: ignore[unresolved-attribute]
        for asset, plan in self.owners_plans:
            apply_owners(asset, plan)


class OwnershipForm(forms.ModelForm):
    """Add or update the share of an asset held by a household member."""

    user = UserChoiceField(
        queryset=household_members(),
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


class PeopleFilterForm(forms.Form):
    """Household members whose part of the assets is shown (all by default)."""

    people = PeopleField(label=_("Owners"), required=False)

    def selected(self) -> set[int] | None:
        """Primary keys of the chosen members, None for the whole household."""
        if not self.is_valid():
            return None
        chosen = {user.pk for user in self.cleaned_data["people"]}
        members = {user.pk for user in self.fields["people"].queryset}  # ty: ignore[unresolved-attribute]
        return chosen if chosen and chosen != members else None


class BirthDateForm(forms.Form):
    """Birth date of the current user, used to value a life usufruct."""

    birth_date = forms.DateField(
        label=_("My birth date"),
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
        ),
    )
