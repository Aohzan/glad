"""Properties: values, loans, cash flow, ledger and LMNP taxes."""

import datetime
from typing import Any

from mcp_server.serializers import decimal, money, ref, to_json
from mcp_server.server import ToolInputError, glad_tool
from property.models import Lease, Property, PropertyLedgerEntry, PropertyLoan
from property.services import tax_lmnp
from property.services.cashflow import ledger_totals_by_category
from property.services.loans import loan_rows
from property.services.monthly_flows import monthly_flows

#: Most ledger occurrences returned by one call.
MAX_OCCURRENCES = 500


def _summary(prop: Property, today: datetime.date) -> dict:
    return {
        "id": prop.pk,
        "name": prop.name,
        "type": prop.get_property_type_display(),
        "city": prop.city,
        "is_active": prop.is_active,
        "tax_regime": prop.tax_regime,
        "value": money(prop.get_value()),
        "remaining_loans": money(prop.total_remaining_loans),
        "net_value": money(prop.net_value),
        "monthly_cashflow": (
            decimal(monthly_flows(prop, today).cashflow) if prop.is_active else None
        ),
    }


@glad_tool()
def list_properties(include_sold: bool = False) -> list[dict]:
    """Properties with their value, remaining loans, net value and median
    monthly cash flow over the last 12 months."""
    today = datetime.date.today()
    queryset = (
        Property.objects.all()
        if include_sold
        else Property.objects.filter(is_active=True)
    )
    return [_summary(prop, today) for prop in queryset]


@glad_tool()
def get_property(property_id: int) -> dict:
    """One property: purchase, address, energy rating, loans with their
    remaining balance, median monthly flows, leases, and the ledger totals by
    category of the current year."""
    today = datetime.date.today()
    prop = Property.objects.get(pk=property_id)
    loans = (
        PropertyLoan.objects.filter(property=prop)
        .select_related("property")
        .prefetch_related("amortization_entries")
        .order_by("start_date")
    )
    totals = ledger_totals_by_category(prop, datetime.date(today.year, 1, 1), today)
    return {
        **_summary(prop, today),
        "address": prop.full_address,
        "buying_date": to_json(prop.buying_date),
        "buying_value": money(prop.buying_value),
        "fees": {
            "notary": money(prop.notary_fees),
            "agency": money(prop.agency_fees),
            "other": money(prop.other_fees),
            "credit": money(prop.credit_fees),
        },
        "selling_date": to_json(prop.selling_date),
        "selling_value": money(prop.selling_value),
        "floor_area": to_json(prop.floor_area),
        "rooms": prop.number_of_rooms,
        "dpe_rating": prop.dpe_rating,
        "dpe_date": to_json(prop.dpe_date),
        "lmnp_start_date": to_json(prop.lmnp_start_date),
        "monthly_flows": to_json(monthly_flows(prop, today)),
        "loans": [
            {
                "id": row.loan.pk,
                "name": str(row.loan),
                "lender": row.loan.lender,
                "start_date": row.loan.start_date.isoformat(),
                "end_date": row.loan.end_date.isoformat(),
                "original_amount": money(row.loan.original_amount),
                "interest_rate": to_json(row.loan.interest_rate),
                "monthly_payment": money(row.monthly_payment),
                "monthly_insurance": money(row.monthly_insurance),
                "remaining_balance": money(row.remaining_balance),
                "capital_paid": money(row.capital_paid),
                "interest_paid": money(row.interest_paid),
                "total_cost": money(row.total_cost),
                "is_running": row.is_running,
            }
            for row in loan_rows(loans, today)
        ],
        "leases": [
            {
                "id": lease.pk,
                "name": lease.name,
                "status": lease.status,
                "start_date": lease.start_date.isoformat(),
                "end_date": to_json(lease.end_date),
                "rent": money(lease.rent_amount),
                "charges": money(lease.charges_amount),
            }
            for lease in Lease.objects.filter(property=prop).order_by("-start_date")
        ],
        "ledger_this_year": {
            "from": f"{today.year}-01-01",
            "to": today.isoformat(),
            "income": to_json(totals.income),
            "expenses": to_json(totals.expenses),
        },
    }


@glad_tool()
def get_property_ledger(
    property_id: int, date_from: datetime.date, date_to: datetime.date
) -> dict:
    """Income and expenses of a property between two dates: the totals by
    management category (cerfa 2033-B lines) and every occurrence, recurring
    entries expanded, with whether it was checked (rent received, expense
    paid)."""
    if date_to < date_from:
        raise ToolInputError("date_to is before date_from.")
    prop = Property.objects.get(pk=property_id)
    entries = (
        PropertyLedgerEntry.objects.filter(property=prop, entry_date__lte=date_to)
        .prefetch_related("exceptions")
        .select_related("lease")
    )
    occurrences: list[dict[str, Any]] = []
    for entry in entries:
        for occurrence in entry.generate_occurrences(end_date=date_to):
            if date_from <= occurrence["date"] <= date_to:
                occurrences.append(
                    {
                        "entry_id": entry.pk,
                        "date": occurrence["date"].isoformat(),
                        "label": occurrence.get("description_override")
                        or entry.display_label,
                        "flow_type": entry.flow_type,
                        "category": entry.management_category,
                        "amount": money(occurrence["amount"]),
                        "lease": ref(entry.lease),
                        "is_recurring": entry.recurrence_type != entry.NONE,
                        "is_checked": occurrence.get("is_checked"),
                    }
                )
    occurrences.sort(key=lambda o: o["date"])
    totals = ledger_totals_by_category(prop, date_from, date_to)
    return {
        "property": ref(prop),
        "income_by_category": to_json(totals.income),
        "expenses_by_category": to_json(totals.expenses),
        "occurrences": occurrences[:MAX_OCCURRENCES],
        "truncated": len(occurrences) > MAX_OCCURRENCES,
    }


@glad_tool()
def get_lmnp_summary(property_id: int, year: int) -> dict:
    """LMNP (furnished rental, réel regime) tax figures of a property for a
    year: income, deductible expenses, depreciation, taxable result, deferred
    depreciation and the cerfa boxes, plus the completeness checklist of the
    tax return."""
    prop = Property.objects.get(pk=property_id)
    if prop.tax_regime != Property.TaxRegime.LMNP_REEL:
        raise ToolInputError("This property is not under the LMNP réel regime.")
    return {
        "property": ref(prop),
        "year": year,
        "summary": to_json(tax_lmnp.get_lmnp_summary(prop.pk, year)),
        "checklist": to_json(tax_lmnp.get_lmnp_checklist([prop], year)),
    }
