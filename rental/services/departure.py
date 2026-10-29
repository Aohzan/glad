"""Departure of a tenant: notice, exit inventory, deposit return and closing.

The deposit statement is written in French: it is sent to the tenant.
"""

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q
from django.utils import formats, translation
from django.utils.translation import gettext as _
from djmoney.money import Money

from property.models import Lease, PropertyLedgerEntry
from property.models.ledger import ManagementCategory
from rental import rules
from rental.models import DepositSettlement, Inventory, InventoryItem
from rental.services.landlord import landlord_of
lazy from base.services.pdf import BasePdf, money

CENT = Decimal("0.01")
TENANT = "tenant"
LANDLORD = "landlord"

#: Worse conditions have a higher rank.
_RANK: dict[str, int] = {
    InventoryItem.Condition.NEW: 0,
    InventoryItem.Condition.GOOD: 1,
    InventoryItem.Condition.WORN: 2,
    InventoryItem.Condition.POOR: 3,
    InventoryItem.Condition.DAMAGED: 4,
}


# ── Notice ──────────────────────────────────────────────────────────────────


def notice_end(
    lease: Lease, notice_date: datetime.date, by: str
) -> datetime.date | None:
    """End of the lease after a notice received on *notice_date*."""
    if by == TENANT:
        return notice_date + relativedelta(months=rules.tenant_notice_months(lease))
    return rules.term_end(lease, notice_date)


def give_notice(lease: Lease, notice_date: datetime.date, by: str) -> Lease:
    """Record a notice: the lease ends at the end of the notice period."""
    lease.notice_date = notice_date
    lease.notice_by = by
    lease.status = Lease.Status.NOTICE_PERIOD
    lease.end_date = notice_end(lease, notice_date, by) or lease.end_date
    lease.save(
        update_fields=["notice_date", "notice_by", "status", "end_date", "updated_at"]
    )
    return lease


def landlord_notice_deadline(
    lease: Lease, today: datetime.date
) -> datetime.date | None:
    """Last day for the landlord to give notice before the end of the term."""
    months = rules.LANDLORD_NOTICE_MONTHS.get(lease.lease_type)
    end = rules.term_end(lease, today)
    if months is None or end is None:
        return None
    return end + datetime.timedelta(days=1) - relativedelta(months=months)


# ── Exit inventory ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Comparison:
    room: str
    item: str
    entry: str
    exit: str
    comment: str

    @property
    def is_worse(self) -> bool:
        if not self.entry or not self.exit:
            return False
        return _RANK[self.exit] > _RANK[self.entry]


def compare(lease: Lease) -> list[Comparison]:
    """Each element of the exit inventory with its condition at the entry."""
    inventories = {
        inventory.kind: inventory
        for inventory in Inventory.objects.filter(lease=lease).prefetch_related(
            "rooms__items"
        )
    }
    entry, exit_ = (
        inventories.get(Inventory.Kind.ENTRY),
        inventories.get(Inventory.Kind.EXIT),
    )
    if entry is None or exit_ is None:
        return []
    before = {}
    for room in entry.rooms.all():  # ty: ignore[unresolved-attribute]
        for item in room.items.all():
            before[room.name, item.name] = item.condition
    rows = []
    for room in exit_.rooms.all():  # ty: ignore[unresolved-attribute]
        for item in room.items.all():
            rows.append(
                Comparison(
                    room=room.name,
                    item=item.name,
                    entry=before.get((room.name, item.name), ""),
                    exit=item.condition,
                    comment=item.comment,
                )
            )
    return rows


# ── Deposit ─────────────────────────────────────────────────────────────────


def return_deadline(settlement: DepositSettlement) -> datetime.date:
    months = (
        rules.DEPOSIT_RETURN_MONTHS
        if settlement.exit_matches_entry
        else rules.DEPOSIT_RETURN_MONTHS_DAMAGED
    )
    return settlement.keys_returned_date + relativedelta(months=months)


def months_late(settlement: DepositSettlement, on: datetime.date) -> int:
    """Started months of delay after the deadline on *on*."""
    deadline = return_deadline(settlement)
    months = 0
    while deadline + relativedelta(months=months) < on:
        months += 1
    return months


def penalty(settlement: DepositSettlement, on: datetime.date) -> Decimal:
    rent = settlement.lease.rent_amount.amount
    return (rent * rules.DEPOSIT_LATE_PENALTY * months_late(settlement, on)).quantize(
        CENT, ROUND_HALF_UP
    )


def deposit_back(settlement: DepositSettlement) -> Decimal:
    """The part of the deposit given back, before any late penalty."""
    kept = settlement.deducted + settlement.coownership_withholding
    return max(settlement.deposit - kept, Decimal(0))


def to_pay(settlement: DepositSettlement, on: datetime.date) -> Decimal:
    return deposit_back(settlement) + penalty(settlement, on)


def _entry(lease: Lease, flow: str, category: str, amount: Decimal, day, label: str):
    return PropertyLedgerEntry.objects.create(
        property=lease.property,
        lease=lease,
        flow_type=flow,
        management_category=category,
        amount=Money(amount, lease.deposit_amount.currency),
        entry_date=day,
        third_party=lease.name,
        description=label,
    )


@transaction.atomic
def settle(settlement: DepositSettlement, returned_date: datetime.date) -> None:
    """Record the deposit returned, the amounts kept and the penalty in the ledger."""
    lease = settlement.lease
    income = PropertyLedgerEntry.FlowType.INCOME
    expense = PropertyLedgerEntry.FlowType.EXPENSE
    back = deposit_back(settlement)
    if back:
        _entry(
            lease,
            expense,
            ManagementCategory.DEPOSIT_OUT.value,
            back,
            returned_date,
            _("Deposit returned"),
        )
    deducted = min(settlement.deducted, settlement.deposit)
    if deducted:
        _entry(
            lease,
            income,
            ManagementCategory.OTHER_INCOME.value,
            deducted,
            returned_date,
            _("Kept from the deposit"),
        )
    late = penalty(settlement, returned_date)
    if late:
        _entry(
            lease,
            expense,
            ManagementCategory.NON_DEDUCTIBLE.value,
            late,
            returned_date,
            _("Penalty for the late return of the deposit"),
        )
    settlement.status = DepositSettlement.Status.RETURNED
    settlement.returned_date = returned_date
    settlement.save(update_fields=["status", "returned_date", "updated_at"])


@transaction.atomic
def close_lease(lease: Lease, end_date: datetime.date) -> int:
    """End the lease and its recurring entries; the number of series ended."""
    lease.status = Lease.Status.ENDED
    lease.end_date = end_date
    lease.save(update_fields=["status", "end_date", "updated_at"])
    return (
        PropertyLedgerEntry.objects.filter(lease=lease)
        .exclude(recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE)
        .filter(
            Q(recurrence_end_date__isnull=True) | Q(recurrence_end_date__gt=end_date)
        )
        .update(recurrence_end_date=end_date)
    )


def _date(day: datetime.date) -> str:
    with translation.override("fr"):
        return formats.date_format(day, "j F Y")


def statement_pdf(
    settlement: DepositSettlement, today: datetime.date | None = None
) -> bytes:
    """The statement of the deposit return sent to the tenant."""
    today = today or datetime.date.today()
    on = settlement.returned_date or today
    lease = settlement.lease
    landlord = landlord_of(lease.property)
    pdf = BasePdf()
    pdf.add_page()
    pdf.heading("Restitution du dépôt de garantie")
    pdf.paragraph(
        f"Logement : {lease.property.full_address or lease.property.name}\n"
        f"Bailleur : {landlord.name}\n"
        f"Locataire : {', '.join(t.name for t in lease.tenants)}\n"
        f"Remise des clés : {_date(settlement.keys_returned_date)}"
    )
    rows = [["Dépôt de garantie versé", money(settlement.deposit)]]
    rows += [
        [f"Retenue : {line['label']}", f"- {money(line['amount'])}"]
        for line in settlement.deductions
    ]
    if settlement.coownership_withholding:
        rows.append(
            [
                "Provision conservée dans l'attente de l'arrêté des comptes de copropriété",
                f"- {money(settlement.coownership_withholding)}",
            ]
        )
    late = penalty(settlement, on)
    if late:
        rows.append(["Majoration pour restitution tardive", money(late)])
    rows.append(["Montant restitué", money(to_pay(settlement, on))])
    pdf.simple_table(["Détail", "Montant"], rows, [140, 40], bold_rows={len(rows) - 1})
    pdf.note(
        f"Délai de restitution : {_date(return_deadline(settlement))} "
        f"({'un mois' if settlement.exit_matches_entry else 'deux mois'} après la "
        "remise des clés, article 22 de la loi n° 89-462 du 6 juillet 1989). Les "
        "retenues sont justifiées par l'état des lieux de sortie comparé à celui "
        "d'entrée, ou par les factures et devis tenus à disposition du locataire."
    )
    return pdf.render()
