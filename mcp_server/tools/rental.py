"""Leases: rent periods, arrears and checklist."""

import datetime

from mcp_server.serializers import decimal, money, ref, to_json
from mcp_server.server import glad_tool
from property.models import Lease
from rental.services.compliance import issues, lease_checks
from rental.services.dashboard import lease_rows
from rental.services.payments import arrears, lease_periods

#: Rent periods returned by get_lease.
PERIODS = 12


def _period(period) -> dict:
    return {
        "period": period.key,
        "due_date": to_json(period.due_date),
        "rent": decimal(period.rent),
        "charges": decimal(period.charges),
        "paid": decimal(period.paid),
        "paid_date": to_json(period.paid_date),
        "balance": decimal(period.balance),
        "status": period.status,
        "days_late": period.days_late,
    }


@glad_tool()
def list_leases() -> list[dict]:
    """Current leases (upcoming, running or under notice) of the active
    properties, with their rent, arrears and checklist issues. Leases managed
    by an agency have no checklist."""
    today = datetime.date.today()
    return [
        {
            "id": row.lease.pk,
            "name": row.lease.name,
            "property": ref(row.lease.property),
            "status": row.lease.status,
            "start_date": row.lease.start_date.isoformat(),
            "rent": money(row.lease.rent_amount),
            "charges": money(row.lease.charges_amount),
            "managed_by_agency": row.mandate is not None,
            "arrears": decimal(arrears(row.periods)),
            "issues": to_json(row.issues),
        }
        for row in lease_rows(today)
    ]


@glad_tool()
def get_lease(lease_id: int) -> dict:
    """One lease: terms, tenants and guarantors, the latest rent periods with
    what was paid, the arrears and the checklist (documents, insurance,
    deposit, rent revision…)."""
    today = datetime.date.today()
    lease = Lease.objects.select_related("property").get(pk=lease_id)
    periods = lease_periods(lease, today)
    managed = lease.mandate_on(today) is not None
    checks = [] if managed else lease_checks(lease, today=today)
    return {
        "id": lease.pk,
        "name": lease.name,
        "property": ref(lease.property),
        "type": lease.lease_type,
        "status": lease.status,
        "start_date": lease.start_date.isoformat(),
        "end_date": to_json(lease.end_date),
        "notice_date": to_json(lease.notice_date),
        "duration_months": lease.duration_months,
        "periodicity": lease.periodicity,
        "payment_day": lease.payment_day,
        "rent": money(lease.rent_amount),
        "charges": money(lease.charges_amount),
        "charges_mode": lease.charges_mode,
        "deposit": money(lease.deposit_amount),
        "last_rent_revision_date": to_json(lease.last_rent_revision_date),
        "tenants": [str(party) for party in lease.tenants],
        "guarantors": [str(party) for party in lease.guarantors],
        "notes": lease.notes,
        "managed_by_agency": managed,
        "arrears": decimal(arrears(periods)),
        "periods": [_period(period) for period in periods[:PERIODS]],
        "checklist": to_json(checks),
        "issues": to_json(issues(checks)),
    }
