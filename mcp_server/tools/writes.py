"""Write tools: values, deposits, accounts, holdings, trades, ledger
entries, checked occurrences, budget lines.

Each tool fills the form of the matching page of the application (restricted
to the changed fields for the updates), so the data goes through the same
validation; the form errors are sent back to the model. ``glad_tool(write=True)``
runs them in a transaction.
"""

import datetime
from decimal import Decimal
from typing import Literal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from djmoney.money import Money

from base.choices import AssetClass
from budget.forms import BudgetLineForm
from budget.models import BudgetCategory, BudgetLine, BudgetYear
from finance.forms import (
    InvestmentAccountCashForm,
    InvestmentAccountDepositForm,
    InvestmentAccountHoldingForm,
    InvestmentAccountHoldingHistoryForm,
    OtherAssetValueForm,
    SavingAccountDepositForm,
    SavingAccountValueForm,
)
from finance.models.base import DepositOrigin
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountValue,
)
from mcp_server.serializers import money, ref, to_json
from mcp_server.serializers import quantity as units
from mcp_server.server import ToolInputError, glad_tool
from property.forms import (
    PropertyLedgerEntryQuickCreateForm,
    PropertyValueQuickCreateForm,
)
from property.models import (
    ManagementCategory,
    Property,
    PropertyLedgerEntry,
    PropertyValue,
)
from property.services.checks import (
    actual_values_error,
    check_occurrence,
    is_occurrence,
)

FlowType = Literal["income", "expense"]
Recurrence = Literal["none", "monthly", "quarterly", "biannual", "yearly"]
Origin = Literal["unknown", "income", "transfer", "exceptional", "employer"]

#: Form, model and parent field of the value entries of each kind of account.
VALUES = {
    "saving": (SavingAccountValueForm, SavingAccount, SavingAccountValue, "account"),
    "investment": (
        InvestmentAccountCashForm,
        InvestmentAccount,
        InvestmentAccountCash,
        "account",
    ),
    "other": (OtherAssetValueForm, OtherAsset, OtherAssetValue, "asset"),
}
DEPOSITS = {
    "saving": (
        SavingAccountDepositForm,
        SavingAccount,
        SavingAccountDeposit,
        "update_account_value",
    ),
    "investment": (
        InvestmentAccountDepositForm,
        InvestmentAccount,
        InvestmentAccountDeposit,
        "update_account_cash",
    ),
}


def _save(form: forms.ModelForm):
    """Save *form*, or raise its errors for the model."""
    if not form.is_valid():
        raise ValidationError(
            {field: list(errors) for field, errors in form.errors.items()}
        )
    return form.save()


def _money_data(name: str, amount: Decimal, currency: str) -> dict:
    """Form data of a MoneyField (amount and currency sub-fields)."""
    return {f"{name}_0": str(amount), f"{name}_1": currency}


def _field_data(name: str, value) -> dict:
    """Form data of one model field value."""
    if isinstance(value, Money):
        return _money_data(name, value.amount, str(value.currency))
    if isinstance(value, bool):
        return {name: "on"} if value else {}
    if isinstance(value, datetime.date):
        return {name: value.isoformat()}
    return {name: "" if value is None else str(value)}


def _update(instance, fields: dict, form=forms.ModelForm):
    """Save *instance* with the new values of *fields* (None: unchanged)
    through a form of *form* restricted to those fields."""
    form_class = forms.modelform_factory(type(instance), form=form, fields=list(fields))
    data = {}
    for name, value in fields.items():
        data.update(
            _field_data(name, getattr(instance, name) if value is None else value)
        )
    return _save(form_class(data, instance=instance))


def _day(value: datetime.date) -> datetime.date:
    return value.date() if isinstance(value, datetime.datetime) else value


def _deposit(deposit) -> dict:
    return {
        "id": deposit.pk,
        "account": ref(deposit.account),
        "date": to_json(deposit.deposit_date),
        "amount": money(deposit.amount),
        "origin": DepositOrigin(deposit.origin).value,
        "source": deposit.source or "",
    }


@glad_tool(write=True)
def add_account_value(
    kind: Literal["saving", "investment", "other"],
    account_id: int,
    value: Decimal,
    date: datetime.date,
) -> dict:
    """Record the balance of a savings account, the cash balance of an
    investment account (its holdings are valued apart), or the value of an
    other asset, at *date*, in the currency of the account. The cash balance
    of an investment account has one value per date: a new one replaces it."""
    form_class, parent_model, model, parent_field = VALUES[kind]
    parent = parent_model.objects.get(pk=account_id)
    form = form_class(
        {
            **_money_data("value", value, parent.currency),
            "value_date": date.isoformat(),
        },
        instance=model(**{parent_field: parent}),
    )
    saved = _save(form)
    return {
        "id": saved.pk,
        "account": ref(parent),
        "date": to_json(saved.value_date),
        "value": money(saved.value),
    }


@glad_tool(write=True)
def add_account_deposit(
    kind: Literal["saving", "investment"],
    account_id: int,
    amount: Decimal,
    date: datetime.date,
    origin: Origin = "unknown",
    source: str = "",
    update_balance: bool = True,
) -> dict:
    """Record a deposit (negative: a withdrawal) on a savings or investment
    account. *origin* tells where the money comes from, for the budget
    (income, transfer between accounts, exceptional, employer). With
    *update_balance*, the account balance (savings) or cash (investment)
    gains the amount, as in the application. An account takes one deposit of
    a given amount per day: a second one is refused as a duplicate."""
    form_class, parent_model, model, update_field = DEPOSITS[kind]
    parent = parent_model.objects.get(pk=account_id)
    same = model.objects.filter(account=parent, amount=Money(amount, parent.currency))
    duplicate = next((d for d in same if _day(d.deposit_date) == date), None)
    if duplicate is not None:
        raise ToolInputError(
            f"Deposit {duplicate.pk} already has this amount on this day: "
            "check that this is not the same deposit, or change it with "
            "update_deposit."
        )
    data = {
        **_money_data("amount", amount, parent.currency),
        "deposit_date": date.isoformat(),
        "origin": origin,
        "source": source,
    }
    if update_balance:
        data[update_field] = "on"
    saved = _save(form_class(data, instance=model(account=parent)))
    return {**_deposit(saved), "account_value": money(parent.get_value())}


@glad_tool(write=True)
def update_deposit(
    kind: Literal["saving", "investment"],
    deposit_id: int,
    amount: Decimal | None = None,
    date: datetime.date | None = None,
    origin: Origin | None = None,
    source: str | None = None,
) -> dict:
    """Correct a deposit of a savings or investment account: the arguments
    left out keep their value. The balance (or cash) value that the deposit
    created when it was entered is not changed: correct it with
    add_account_value if needed."""
    form_class, _parent_model, model, _update_field = DEPOSITS[kind]
    deposit = model.objects.select_related("account").get(pk=deposit_id)
    saved = _update(
        deposit,
        {
            "amount": None
            if amount is None
            else Money(amount, deposit.account.currency),
            "deposit_date": date,
            "origin": origin,
            "source": source,
        },
        form=form_class,
    )
    return _deposit(saved)


@glad_tool(write=True, destructive=True)
def delete_deposit(
    kind: Literal["saving", "investment"], deposit_id: int, confirm: bool = False
) -> dict:
    """Delete a deposit entered by mistake. Without *confirm*, only describe
    the deposit that would be deleted: show it to the user and call again
    with confirm=true once they agree. The balance (or cash) value that the
    deposit created when it was entered is kept: correct it with
    add_account_value if needed."""
    _form_class, _parent_model, model, _update_field = DEPOSITS[kind]
    deposit = model.objects.select_related("account").get(pk=deposit_id)
    described = _deposit(deposit)
    if not confirm:
        return {"deleted": False, "deposit": described}
    deposit.delete()
    return {"deleted": True, "deposit": described}


@glad_tool(write=True)
def update_account(
    kind: Literal["saving", "investment", "other"],
    account_id: int,
    name: str | None = None,
    institution: str | None = None,
    notes: str | None = None,
    interest_rate: Decimal | None = None,
) -> dict:
    """Change the name, institution, notes or interest rate (savings
    accounts, in percent) of an account; the name and notes of an other
    asset. The arguments left out keep their value."""
    account = VALUES[kind][1].objects.get(pk=account_id)
    if isinstance(account, OtherAsset):
        if institution is not None or interest_rate is not None:
            raise ToolInputError("An other asset has only a name and notes.")
        fields = {"name": name, "notes": notes}
    else:
        fields = {"name": name, "institution": institution, "commentaire": notes}
        if isinstance(account, SavingAccount):
            fields["interest_rate"] = interest_rate
        elif interest_rate is not None:
            raise ToolInputError("Only a savings account has an interest rate.")
    saved = _update(account, fields)
    return {
        "id": saved.pk,
        "kind": kind,
        "name": str(saved),
        "institution": getattr(saved, "institution", None) or "",
        "notes": getattr(saved, "commentaire", None) or getattr(saved, "notes", ""),
        "interest_rate": to_json(getattr(saved, "interest_rate", None)),
    }


def update_holding(
    holding_id: int,
    name: str | None = None,
    isin: str | None = None,
    asset_class: str | None = None,
    initial_value: Decimal | None = None,
    initial_quantity: Decimal | None = None,
) -> dict:
    """Change a holding of an investment account: its name, ISIN, asset class
    (one of: {asset_classes}), or its initial value and quantity, from which
    the purchase price (PRU) and the gain are computed. The arguments left
    out keep their value."""
    holding = InvestmentAccountHolding.objects.select_related("account").get(
        pk=holding_id
    )
    saved = _update(
        holding,
        {
            "name": name,
            "isin": None if isin is None else isin.strip().upper(),
            "asset_class": asset_class,
            "initial_value": None
            if initial_value is None
            else Money(initial_value, holding.account.currency),
            "initial_quantity": initial_quantity,
            "auto_update_price": None,
        },
        form=InvestmentAccountHoldingForm,
    )
    return {
        "id": saved.pk,
        "account": ref(saved.account),
        "name": saved.name or "",
        "isin": saved.isin or "",
        "asset_class": saved.asset_class or "unclassified",
        "initial_value": money(saved.initial_value),
        "initial_quantity": units(saved.initial_quantity),
    }


# The asset classes are listed in the description the model reads.
update_holding.__doc__ = (update_holding.__doc__ or "").replace(
    "{asset_classes}", ", ".join(AssetClass.values)
)
glad_tool(write=True)(update_holding)


def _trade_time(date: datetime.date) -> datetime.datetime:
    """Time of a trade on *date*: now for today, else the end of that day,
    after the values entered on the same day."""
    if date == datetime.date.today():
        return datetime.datetime.now().replace(microsecond=0)
    return datetime.datetime.combine(date, datetime.time(23, 59, 59))


@glad_tool(write=True)
def record_trade(
    holding_id: int,
    side: Literal["buy", "sell"],
    quantity: Decimal,
    unit_price: Decimal,
    date: datetime.date,
    fees: Decimal = Decimal(0),
) -> dict:
    """Record a purchase or a sale of *quantity* units of an existing holding
    at *unit_price*, as the history page of the holding does: a new entry
    with the new quantity valued at *unit_price*, and the account cash
    debited of quantity × unit_price + fees (buy) or credited of
    quantity × unit_price − fees (sell). The purchase price (PRU, initial
    value) is left unchanged: correct it with update_holding if needed."""
    if quantity <= 0 or unit_price <= 0 or fees < 0:
        raise ToolInputError(
            "The quantity and the unit price must be positive, the fees not negative."
        )
    day = _day(date)
    if day > datetime.date.today():
        raise ToolInputError("A trade cannot be in the future.")
    holding = InvestmentAccountHolding.objects.select_related("account").get(
        pk=holding_id
    )
    if not holding.is_active:
        raise ToolInputError("This holding is closed.")
    at = _trade_time(day)
    if InvestmentAccountHoldingHistory.objects.filter(
        holding=holding, valuation_date__gt=at
    ).exists():
        raise ToolInputError(
            "The holding has values entered after this date: record the trades "
            "in date order."
        )
    held = holding.get_quantity(at)
    if held is None:
        raise ToolInputError(
            "The quantity held is unknown: set it with update_holding "
            "(initial_quantity) first."
        )
    if side == "sell" and quantity > held:
        raise ToolInputError(f"Only {units(held)} units are held.")
    new_quantity = held + quantity if side == "buy" else held - quantity
    amount = quantity * unit_price
    cash_used = amount + fees if side == "buy" else -(amount - fees)
    currency = holding.account.currency
    form = InvestmentAccountHoldingHistoryForm(
        {
            **_money_data("value", round(new_quantity * unit_price, 2), currency),
            "valuation_date": at.isoformat(),
            "quantity": str(new_quantity),
            **_money_data("cash_used", round(cash_used, 2), currency),
        },
        instance=InvestmentAccountHoldingHistory(holding=holding),
    )
    saved = _save(form)
    return {
        "id": saved.pk,
        "holding": ref(holding),
        "side": side,
        "date": to_json(saved.valuation_date),
        "quantity_before": units(held),
        "quantity_after": units(saved.quantity),
        "value": money(saved.value),
        "cash_change": money(-saved.cash_used),
        "cash_after": money(holding.account.get_cash_value(max_date=at)),
    }


@glad_tool(write=True)
def add_property_value(property_id: int, value: Decimal, date: datetime.date) -> dict:
    """Record an estimate of the market value of a property at *date*."""
    prop = Property.objects.get(pk=property_id)
    form = PropertyValueQuickCreateForm(
        {
            **_money_data("value", value, prop.currency),
            "valuation_date": date.isoformat(),
            "source": PropertyValue.Source.MANUAL,
        },
    )
    form.instance.property = prop
    saved = _save(form)
    return {
        "id": saved.pk,
        "property": ref(prop),
        "date": to_json(saved.valuation_date),
        "value": money(saved.value),
    }


def add_ledger_entry(
    property_id: int,
    flow_type: FlowType,
    management_category: str,
    amount: Decimal,
    entry_date: datetime.date,
    description: str = "",
    third_party: str = "",
    lease_id: int | None = None,
    recurrence_type: Recurrence = "none",
    recurrence_end_date: datetime.date | None = None,
    reference_period: datetime.date | None = None,
    is_recoverable: bool = False,
    notes: str = "",
) -> dict:
    """Add an income or expense to the ledger of a property, in the currency of
    the property. *amount* is positive, *flow_type* gives its direction.
    *management_category* is one of: {categories}. A recurring entry
    (monthly rent, quarterly co-ownership charges…) repeats from *entry_date*
    until *recurrence_end_date*. *is_recoverable* marks an expense the tenant
    pays back."""
    prop = Property.objects.get(pk=property_id)
    data = {
        **_money_data("amount", amount, prop.currency),
        "flow_type": flow_type,
        "management_category": management_category,
        "entry_date": entry_date.isoformat(),
        "description": description,
        "third_party": third_party,
        "lease": lease_id or "",
        "recurrence_type": recurrence_type,
        "recurrence_end_date": recurrence_end_date.isoformat()
        if recurrence_end_date
        else "",
        "reference_period": reference_period.isoformat() if reference_period else "",
        "notes": notes,
    }
    if is_recoverable:
        data["is_recoverable"] = "on"
    form = PropertyLedgerEntryQuickCreateForm(data, property_obj=prop)
    form.instance.property = prop
    entry = _save(form)
    return {
        "id": entry.pk,
        "property": ref(prop),
        "label": entry.display_label,
        "flow_type": entry.flow_type,
        "category": entry.management_category,
        "amount": money(entry.amount),
        "entry_date": entry.entry_date.isoformat(),
        "recurrence_type": entry.recurrence_type,
    }


# The categories are listed in the description the model reads.
add_ledger_entry.__doc__ = (add_ledger_entry.__doc__ or "").replace(
    "{categories}", ", ".join(category.value for category in ManagementCategory)
)
glad_tool(write=True)(add_ledger_entry)


@glad_tool(write=True)
def check_ledger_occurrence(
    entry_id: int,
    occurrence_date: datetime.date,
    actual_date: datetime.date | None = None,
    actual_amount: Decimal | None = None,
) -> dict:
    """Mark an occurrence of a recurring ledger entry as checked: a rent
    received, a charge actually paid. *occurrence_date* is its scheduled date
    (see get_pending_checks or get_property_ledger); give *actual_date* and
    *actual_amount* when they differ from the schedule (a partial rent, a late
    payment)."""
    entry = PropertyLedgerEntry.objects.select_related("property").get(pk=entry_id)
    if not is_occurrence(entry, occurrence_date):
        raise ToolInputError(
            f"{occurrence_date} is not a scheduled occurrence of entry {entry_id}."
        )
    actual_date = actual_date or occurrence_date
    amount = actual_amount if actual_amount is not None else entry.amount.amount
    if error := actual_values_error(actual_date, amount):
        raise ToolInputError(error)
    check_occurrence(
        entry,
        occurrence_date,
        actual_date,
        Money(amount.quantize(Decimal("0.01")), entry.amount.currency),
    )
    return {
        "entry_id": entry.pk,
        "property": ref(entry.property),
        "label": entry.display_label,
        "occurrence_date": occurrence_date.isoformat(),
        "actual_date": actual_date.isoformat(),
        "amount": money(Money(amount, entry.amount.currency)),
        "checked": True,
    }


@glad_tool()
def list_budget_categories() -> list[dict]:
    """The categories of the budget (id, name, kind, parent), to pick the
    category of a budget line."""
    return [
        {
            "id": category.pk,
            "name": category.name,
            "kind": category.kind,
            "parent_id": category.parent_id,
        }
        for category in BudgetCategory.objects.all()
    ]


@glad_tool(write=True)
def save_budget_line(
    year: int,
    category_id: int,
    label: str,
    amount: Decimal,
    person_id: int | None = None,
    notes: str = "",
    line_id: int | None = None,
) -> dict:
    """Add a line to the budget of *year*, or change the line *line_id*.
    *amount* is the yearly amount. *person_id* ties the line to a household
    member; without it, the line is shared. The budget of the year must
    exist (see get_budget)."""
    budget_year = BudgetYear.objects.filter(year=year).first()
    if budget_year is None:
        raise ToolInputError(f"No budget for {year}.")
    line = (
        BudgetLine.objects.get(pk=line_id, budget_year=budget_year)
        if line_id
        else BudgetLine(budget_year=budget_year)
    )
    currency = str(line.amount.currency) if line.pk else settings.DEFAULT_CURRENCY
    form = BudgetLineForm(
        {
            "category": category_id,
            "label": label,
            **_money_data("amount", amount, currency),
            "person": person_id or "",
            "notes": notes,
        },
        instance=line,
    )
    saved = _save(form)
    return {
        "id": saved.pk,
        "year": year,
        "category": ref(saved.category),
        "label": saved.label,
        "amount": money(saved.amount),
        "person": ref(saved.person),
    }
