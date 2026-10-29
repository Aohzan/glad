"""Yearly reconciliation of the charges of a lease (régularisation des charges).

The provisions paid are the checked charges occurrences of the lease. The
actual charges are the recoverable expenses of the property over the period,
prorated to the days the lease covered, plus manual adjustments (the
recoverable share of the co-ownership charges, the household waste tax…).
The statement is written in French: it is sent to the tenant.
"""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import formats, translation
from django.utils.translation import gettext as _
from djmoney.money import Money

from base.services.pdf import BasePdf, money
from property.models import Lease, PropertyLedgerEntry
from property.models.ledger import ManagementCategory
from property.services.rent_revision import split_series
from rental.models import ChargesReconciliation
from rental.services.landlord import landlord_of
from rental.services.payments import CHARGES, PERIOD_MONTHS

CENT = Decimal("0.01")
#: Average number of days in a month, to turn a period into months.
MONTH_DAYS = Decimal("30.4375")


def default_period(
    lease: Lease, today: datetime.date
) -> tuple[datetime.date, datetime.date]:
    """The last calendar year, within the lease (this year when it started since)."""
    start = datetime.date(today.year - 1, 1, 1)
    end = datetime.date(today.year - 1, 12, 31)
    if lease.start_date > end:
        start, end = lease.start_date, today
    start = max(start, lease.start_date)
    if lease.end_date:
        end = min(end, lease.end_date)
    return start, end


def _days(start: datetime.date, end: datetime.date) -> int:
    return max((end - start).days + 1, 0)


def occupancy_ratio(lease: Lease, start: datetime.date, end: datetime.date) -> Decimal:
    """Share of the period the lease covered."""
    covered = _days(max(start, lease.start_date), min(end, lease.end_date or end))
    return Decimal(covered) / Decimal(_days(start, end))


def _provisions(lease: Lease, start: datetime.date, end: datetime.date) -> Decimal:
    reconciled = ChargesReconciliation.objects.exclude(ledger_entry=None).values(
        "ledger_entry"
    )
    entries = (
        PropertyLedgerEntry.objects.filter(
            lease=lease,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=CHARGES,
        )
        .exclude(pk__in=reconciled)
        .prefetch_related("exceptions")
    )
    total = Decimal(0)
    for entry in entries:
        for occurrence in entry.generate_occurrences(end_date=end):
            day = occurrence.get("occurrence_date") or occurrence["date"]
            paid = occurrence.get("is_checked", True)
            if start <= day <= end and paid:
                total += occurrence["amount"].amount
    return total


def _expenses(lease: Lease, start: datetime.date, end: datetime.date) -> list[dict]:
    ratio = occupancy_ratio(lease, start, end)
    entries = PropertyLedgerEntry.objects.filter(
        property=lease.property,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        is_recoverable=True,
    ).prefetch_related("exceptions")
    lines = []
    for entry in entries:
        label = entry.description or entry.get_management_category_display()
        for occurrence in entry.generate_occurrences(end_date=end):
            if not start <= occurrence["date"] <= end:
                continue
            amount = occurrence["amount"].amount
            lines.append(
                {
                    "label": label,
                    "date": occurrence["date"].isoformat(),
                    "amount": str(amount),
                    "share": str((amount * ratio).quantize(CENT, ROUND_HALF_UP)),
                }
            )
    return sorted(lines, key=lambda line: line["date"])


def compute(reconciliation: ChargesReconciliation) -> ChargesReconciliation:
    """Fill the provisions and the expenses of the period; the adjustments stay."""
    lease = reconciliation.lease
    start, end = reconciliation.period_start, reconciliation.period_end
    reconciliation.provisions = _provisions(lease, start, end)
    reconciliation.expenses = _expenses(lease, start, end)
    reconciliation.save()
    return reconciliation


def create(
    lease: Lease, start: datetime.date, end: datetime.date
) -> ChargesReconciliation:
    return compute(
        ChargesReconciliation(lease=lease, period_start=start, period_end=end)
    )


@transaction.atomic
def record_balance(reconciliation: ChargesReconciliation) -> PropertyLedgerEntry | None:
    """The balance in the ledger: charges collected, or a refund to the tenant."""
    balance = reconciliation.balance
    if reconciliation.ledger_entry_id or not balance:
        return None
    lease = reconciliation.lease
    owed = balance > 0
    entry = PropertyLedgerEntry.objects.create(
        property=lease.property,
        lease=lease,
        flow_type=(
            PropertyLedgerEntry.FlowType.INCOME
            if owed
            else PropertyLedgerEntry.FlowType.EXPENSE
        ),
        management_category=(
            CHARGES if owed else ManagementCategory.MISC_DEDUCTIBLE.value
        ),
        amount=Money(abs(balance), lease.charges_amount.currency),
        entry_date=datetime.date.today(),
        third_party=lease.name,
        description=_("Charges reconciliation %(start)s – %(end)s")
        % {"start": reconciliation.period_start, "end": reconciliation.period_end},
    )
    reconciliation.ledger_entry = entry
    reconciliation.save(update_fields=["ledger_entry", "updated_at"])
    return entry


def suggested_provision(reconciliation: ChargesReconciliation) -> Decimal | None:
    """Provision per payment matching the actual charges of the period."""
    lease = reconciliation.lease
    start = max(reconciliation.period_start, lease.start_date)
    end = min(reconciliation.period_end, lease.end_date or reconciliation.period_end)
    months = Decimal(_days(start, end)) / MONTH_DAYS
    if months <= 0:
        return None
    per_month = reconciliation.actual / months
    return (per_month * PERIOD_MONTHS.get(lease.periodicity, 1)).quantize(
        Decimal(1), ROUND_HALF_UP
    )


@transaction.atomic
def update_provision(
    lease: Lease, amount: Decimal, effective_date: datetime.date
) -> int:
    """Set the provision of *lease* and its recurring charges from *effective_date*."""
    new_amount = Money(amount, lease.charges_amount.currency)
    entries = PropertyLedgerEntry.objects.filter(
        lease=lease, management_category=CHARGES, entry_date__lte=effective_date
    ).exclude(recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE)
    updated = 0
    for entry in entries:
        if entry.recurrence_end_date and entry.recurrence_end_date < effective_date:
            continue
        updated += split_series(entry, effective_date, new_amount)
    lease.charges_amount = new_amount
    lease.save(update_fields=["charges_amount", "updated_at"])
    return updated


def _date(day: datetime.date) -> str:
    with translation.override("fr"):
        return formats.date_format(day, "j F Y")


def statement_pdf(reconciliation: ChargesReconciliation) -> bytes:
    """The statement of the reconciliation sent to the tenant."""
    lease = reconciliation.lease
    landlord = landlord_of(lease.property)
    ratio = occupancy_ratio(
        lease, reconciliation.period_start, reconciliation.period_end
    )
    pdf = BasePdf()
    pdf.add_page()
    pdf.heading("Régularisation des charges locatives")
    pdf.paragraph(
        f"Période du {_date(reconciliation.period_start)} au "
        f"{_date(reconciliation.period_end)}\n"
        f"Logement : {lease.property.full_address or lease.property.name}\n"
        f"Bailleur : {landlord.name}\n"
        f"Locataire : {', '.join(t.name for t in lease.tenants)}"
    )
    if ratio < 1:
        pdf.note(
            f"Le bail couvre {ratio * 100:.0f} % de la période : les dépenses sont "
            "réparties au prorata de la durée d'occupation."
        )
    rows = [
        [
            line["label"],
            datetime.date.fromisoformat(line["date"]).strftime("%d/%m/%Y"),
            money(line["amount"]),
            money(line["share"]),
        ]
        for line in reconciliation.expenses
    ]
    rows += [
        [line["label"], "", "", money(line["amount"])]
        for line in reconciliation.adjustments
    ]
    rows.append(["Total des charges dues", "", "", money(reconciliation.actual)])
    pdf.subheading("Dépenses récupérables")
    pdf.simple_table(
        ["Dépense", "Date", "Montant", "Part locataire"],
        rows,
        [80, 30, 35, 35],
        bold_rows={len(rows) - 1},
        text_columns=2,
    )
    balance = reconciliation.balance
    pdf.simple_table(
        ["Solde", "Montant"],
        [
            ["Charges dues", money(reconciliation.actual)],
            ["Provisions versées", money(reconciliation.provisions)],
            [
                "Reste à payer par le locataire"
                if balance >= 0
                else "Trop-perçu remboursé au locataire",
                money(abs(balance)),
            ],
        ],
        [145, 35],
        bold_rows={2},
    )
    pdf.note(
        "Régularisation annuelle prévue à l'article 23 de la loi n° 89-462 du 6 "
        "juillet 1989. Les pièces justificatives sont tenues à la disposition du "
        "locataire pendant six mois à compter de l'envoi de ce décompte."
    )
    return pdf.render()
