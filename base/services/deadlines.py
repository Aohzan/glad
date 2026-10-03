"""Upcoming deadlines gathered from every asset for the dashboard.

Deadlines come from the envelope milestones of the accounts, the end of the
property loans, the rent revisions and ends of the leases, the DPE rental bans
and expiries, and the end of the SCPI dismemberments.
"""

import datetime
from dataclasses import dataclass
from itertools import chain

from django.urls import reverse
from django.utils.functional import Promise
from django.utils.translation import gettext as _

from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount
from property.models import Lease, Property, PropertyLoan
from property.models.scpi import SCPIInvestment
from property.services.rent_revision import get_rent_revision

#: Deadlines passed for less than this are still shown.
PAST_DAYS = 30
#: Deadlines are shown this many days in advance.
AHEAD_DAYS = 365
#: A future deadline closer than this is highlighted.
SOON_DAYS = 30


@dataclass(frozen=True)
class Deadline:
    """A dated event worth anticipating."""

    date: datetime.date
    title: str
    detail: str | Promise
    url: str
    icon: str
    today: datetime.date

    @property
    def days_left(self) -> int:
        """Days until the deadline, negative once passed."""
        return (self.date - self.today).days

    @property
    def days_ago(self) -> int:
        """Days since the deadline passed (0 when still ahead)."""
        return max(0, -self.days_left)

    @property
    def months_left(self) -> int:
        """Rounded number of months until the deadline."""
        return round(self.days_left / 30.4)

    @property
    def is_soon(self) -> bool:
        """Due within SOON_DAYS and not passed yet."""
        return 0 <= self.days_left <= SOON_DAYS

    @property
    def month(self) -> datetime.date:
        """First day of the month of the deadline, for grouping."""
        return self.date.replace(day=1)

    @property
    def level(self) -> str:
        """``secondary`` when passed, ``warning`` when soon, else ``info``."""
        if self.days_left < 0:
            return "secondary"
        if self.days_left <= SOON_DAYS:
            return "warning"
        return "info"


def _account_deadlines(today: datetime.date):
    for model, url_name, icon in (
        (SavingAccount, "finance:saving_detail", "piggy-bank"),
        (InvestmentAccount, "finance:investment_detail", "chart-line"),
    ):
        for account in model.objects.active().select_related("account_type"):
            for milestone in account.milestones:
                yield Deadline(
                    date=milestone.date,
                    title=str(account),
                    detail=milestone.label,
                    url=reverse(url_name, kwargs={"pk": account.pk}),
                    icon=icon,
                    today=today,
                )


def _loan_deadlines(today: datetime.date):
    for loan in PropertyLoan.objects.filter(property__is_active=True).select_related(
        "property"
    ):
        label = loan.name or loan.lender
        yield Deadline(
            date=loan.end_date,
            title=f"{loan.property} — {label}" if label else str(loan.property),
            detail=_("End of the loan"),
            url=reverse("property:detail", kwargs={"pk": loan.property.pk}),
            icon="landmark",
            today=today,
        )


def _lease_deadlines(today: datetime.date):
    leases = Lease.objects.filter(
        property__is_active=True,
        status__in=[Lease.Status.ACTIVE, Lease.Status.NOTICE_PERIOD],
    ).select_related("property")
    for lease in leases:
        url = reverse("property:detail", kwargs={"pk": lease.property.pk})
        title = f"{lease.property} — {lease.name}"
        revision = get_rent_revision(lease, today=today)
        if revision is not None and not revision.frozen:
            yield Deadline(
                date=revision.due_date,
                title=title,
                detail=_("Rent revision (IRL)"),
                url=url,
                icon="percent",
                today=today,
            )
        if lease.end_date:
            yield Deadline(
                date=lease.end_date,
                title=title,
                detail=_("End of the lease"),
                url=url,
                icon="key-round",
                today=today,
            )


def _dpe_deadlines(today: datetime.date):
    rented = set(
        Lease.objects.filter(
            status__in=[
                Lease.Status.ACTIVE,
                Lease.Status.NOTICE_PERIOD,
                Lease.Status.UPCOMING,
            ]
        ).values_list("property_id", flat=True)
    )
    for prop in Property.objects.filter(is_active=True).exclude(dpe_rating=""):
        status = prop.dpe_status
        if status is None:
            continue
        url = reverse("property:detail", kwargs={"pk": prop.pk})
        if status.ban_date and prop.pk in rented:
            yield Deadline(
                date=status.ban_date,
                title=str(prop),
                detail=_("Rental ban for DPE %(rating)s housing")
                % {"rating": status.rating},
                url=url,
                icon="thermometer-sun",
                today=today,
            )
        if status.expires_on:
            yield Deadline(
                date=status.expires_on,
                title=str(prop),
                detail=_("DPE expiry"),
                url=url,
                icon="thermometer-sun",
                today=today,
            )


def _scpi_deadlines(today: datetime.date):
    investments = SCPIInvestment.objects.filter(
        sold_date__isnull=True, dismemberment_end_date__isnull=False
    ).select_related("scpi")
    for investment in investments:
        assert investment.dismemberment_end_date is not None
        yield Deadline(
            date=investment.dismemberment_end_date,
            title=str(investment.scpi),
            detail=_("End of the dismemberment"),
            url=reverse(
                "property:scpi_fund_detail", kwargs={"scpi_pk": investment.scpi.pk}
            ),
            icon="building",
            today=today,
        )


def upcoming_deadlines(
    today: datetime.date | None = None, limit: int | None = None
) -> list[Deadline]:
    """Deadlines from PAST_DAYS ago to AHEAD_DAYS ahead, soonest first."""
    today = today or datetime.date.today()
    start = today - datetime.timedelta(days=PAST_DAYS)
    end = today + datetime.timedelta(days=AHEAD_DAYS)
    deadlines = [
        deadline
        for deadline in chain(
            _account_deadlines(today),
            _loan_deadlines(today),
            _lease_deadlines(today),
            _dpe_deadlines(today),
            _scpi_deadlines(today),
        )
        if start <= deadline.date <= end
    ]
    deadlines.sort(key=lambda d: (d.date, d.title))
    return deadlines[:limit] if limit else deadlines
