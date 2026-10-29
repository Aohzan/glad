"""Daily job of the rental management: rent calls and receipts sent by email."""

import datetime

from dateutil.relativedelta import relativedelta
from django.utils.translation import gettext_lazy as _

from base.scheduler import Job, register
from rental import emails
from rental.models import RentReceipt
from rental.services.dashboard import current_leases
from rental.services.payments import PAID, UPCOMING, lease_periods
from rental.services.sending import already_sent, send_lease_email

#: Rent calls are sent this many days before the due date.
RENT_CALL_DAYS = 7
#: Receipts are sent automatically for the periods of the last months only, so
#: that enabling the option does not send the whole history.
RECEIPT_MONTHS = 2


def send_rent_emails(today: datetime.date | None = None) -> str:
    """Send the due rent calls and receipts of the leases that enabled them."""
    today = today or datetime.date.today()
    calls = receipts = 0
    oldest_receipt = today.replace(day=1) - relativedelta(months=RECEIPT_MONTHS)
    for lease in current_leases():
        if not (lease.send_rent_calls or lease.send_receipts):
            continue
        to = emails.recipients(lease)
        if not to or lease.mandate_on(today) is not None:
            continue
        periods = lease_periods(lease, today)
        sent_receipts = set(
            RentReceipt.objects.filter(lease=lease, sent_at__isnull=False).values_list(
                "period_start", flat=True
            )
        )
        for period in periods:
            if (
                lease.send_rent_calls
                and period.status == UPCOMING
                and period.due_date is not None
                and 0 <= (period.due_date - today).days <= RENT_CALL_DAYS
                and not already_sent(lease, emails.RENT_CALL, period.key)
            ):
                kind = emails.KINDS[emails.RENT_CALL]
            elif (
                lease.send_receipts
                and period.status == PAID
                and period.expected > 0
                and period.start >= oldest_receipt
                and period.start not in sent_receipts
            ):
                kind = emails.KINDS[emails.RECEIPT]
            else:
                continue
            subject, body = emails.render(kind, lease, periods, period, today)
            send_lease_email(
                lease,
                kind,
                to=to,
                cc=emails.copies(lease, kind),
                subject=subject,
                body=body,
                period=period,
            )
            if kind.key == emails.RENT_CALL:
                calls += 1
            else:
                receipts += 1
    return f"{calls} rent call(s), {receipts} receipt(s) sent"


def register_jobs() -> None:
    register(
        Job(
            name="rental_daily",
            func="rental.jobs.send_rent_emails",
            label=_("Send the rent calls and receipts"),
            at=datetime.time(7, 30),
        )
    )
