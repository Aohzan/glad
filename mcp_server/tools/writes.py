"""Write tools: values, deposits, ledger entries, checked occurrences, budget lines.

Each tool fills the form of the matching page of the application, so the
data goes through the same validation; the form errors are sent back to the
model. ``glad_tool(write=True)`` runs them in a transaction.
"""

import datetime
from decimal import Decimal
from typing import Literal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from djmoney.money import Money

from budget.forms import BudgetLineForm
from budget.models import BudgetCategory, BudgetLine, BudgetYear
from finance.forms import (
    InvestmentAccountCashForm,
    InvestmentAccountDepositForm,
    OtherAssetValueForm,
    SavingAccountDepositForm,
    SavingAccountValueForm,
)
from finance.models.base import DepositOrigin
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
)
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountValue,
)
from mcp_server.serializers import money, ref, to_json
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


@glad_tool(write=True)
def add_account_value(
    kind: Literal["saving", "investment", "other"],
    account_id: int,
    value: Decimal,
    date: datetime.date,
) -> dict:
    """Record the balance of a savings account, the cash balance of an
    investment account (its holdings are valued apart), or the value of an
    other asset, at *date*, in the currency of the account."""
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
    gains the amount, as in the application."""
    form_class, parent_model, model, update_field = DEPOSITS[kind]
    parent = parent_model.objects.get(pk=account_id)
    data = {
        **_money_data("amount", amount, parent.currency),
        "deposit_date": date.isoformat(),
        "origin": origin,
        "source": source,
    }
    if update_balance:
        data[update_field] = "on"
    saved = _save(form_class(data, instance=model(account=parent)))
    return {
        "id": saved.pk,
        "account": ref(parent),
        "date": to_json(saved.deposit_date),
        "amount": money(saved.amount),
        "origin": DepositOrigin(saved.origin).value,
        "account_value": money(parent.get_value()),
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
