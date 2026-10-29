"""Emails sent to the tenants, written from the templates of ``rental/emails/``.

A template holds the subject on its first line, then a blank line, then the
body. The emails are written in French: the tenants are under French law.
"""

import datetime
from dataclasses import dataclass

from django.template.loader import render_to_string
from django.utils import formats, translation
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from base.services.pdf import money
from property.models import Lease
from rental.models import ChargesReconciliation
from rental.services.landlord import landlord_of
from rental.services.payments import PARTIAL, UNPAID, Period, arrears

#: Kind of the emails holding a receipt.
RECEIPT = "receipt"
RENT_CALL = "rent_call"
CHARGES = "charges_reconciliation"


@dataclass(frozen=True)
class EmailKind:
    key: str
    label: str | Promise
    #: The email is about one rent period, chosen with ``?period=YYYY-MM``.
    needs_period: bool = False
    #: The email sends a charges reconciliation, chosen with ``?reconciliation=``.
    needs_reconciliation: bool = False
    #: The guarantors are copied.
    copy_guarantors: bool = False


KINDS = {
    kind.key: kind
    for kind in (
        EmailKind(RENT_CALL, _("Rent notice"), needs_period=True),
        EmailKind(RECEIPT, _("Rent receipt"), needs_period=True),
        EmailKind("reminder", _("Friendly reminder")),
        EmailKind("formal_notice", _("Formal notice"), copy_guarantors=True),
        EmailKind("rent_revision", _("Rent revision letter")),
        EmailKind("insurance_request", _("Insurance certificate request")),
        EmailKind(CHARGES, _("Charges reconciliation"), needs_reconciliation=True),
    )
}


def _date(day: datetime.date | None, fmt: str = "j F Y") -> str:
    return formats.date_format(day, fmt) if day else ""


def recipients(lease: Lease) -> list[str]:
    return [tenant.email for tenant in lease.tenants if tenant.email]


def copies(lease: Lease, kind: EmailKind) -> list[str]:
    if not kind.copy_guarantors:
        return []
    return [g.email for g in lease.guarantors if g.email]


def render(
    kind: EmailKind,
    lease: Lease,
    periods: list[Period],
    period: Period | None = None,
    today: datetime.date | None = None,
    reconciliation: ChargesReconciliation | None = None,
) -> tuple[str, str]:
    """Subject and body of an email of *kind* about *lease*."""
    today = today or datetime.date.today()
    landlord = landlord_of(lease.property)
    late = sorted(
        (p for p in periods if p.status in (PARTIAL, UNPAID)), key=lambda p: p.start
    )
    with translation.override("fr"):
        context = {
            "lease": lease,
            "tenants": " et ".join(t.name for t in lease.tenants),
            "landlord": landlord,
            "address": lease.property.full_address or lease.property.name,
            "today": _date(today),
            "rent": money(lease.rent_amount.amount),
            "charges": money(lease.charges_amount.amount),
            "total": money(lease.total_rent().amount),
            "late": [
                {
                    "label": _date(p.start, "F Y"),
                    "due": _date(p.due_date),
                    "balance": money(p.balance),
                }
                for p in late
            ],
            "arrears": money(arrears(periods)),
            "revision_date": _date(lease.last_rent_revision_date),
        }
        if period is not None:
            context["period"] = {
                "label": _date(period.start, "F Y"),
                "start": _date(period.start),
                "end": _date(period.end),
                "due": _date(period.due_date),
                "rent": money(period.rent),
                "charges": money(period.charges),
                "total": money(period.expected),
                "paid": money(period.paid),
                "is_full": period.paid >= period.expected,
            }
        if reconciliation is not None:
            balance = reconciliation.balance
            context["reconciliation"] = {
                "start": _date(reconciliation.period_start),
                "end": _date(reconciliation.period_end),
                "actual": money(reconciliation.actual),
                "provisions": money(reconciliation.provisions),
                "balance": money(abs(balance)),
                "owed": balance > 0,
                "refund": balance < 0,
            }
        text = render_to_string(f"rental/emails/{kind.key}.txt", context)
    subject, _sep, body = text.strip().partition("\n")
    return subject.strip(), body.strip() + "\n"
