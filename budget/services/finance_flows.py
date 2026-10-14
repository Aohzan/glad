"""Deposits and withdrawals of the saving and investment accounts over a year.

Each movement has an origin (see :class:`finance.models.base.DepositOrigin`):
the deposits from the income count as savings and the withdrawals for the
household as resources, the transfers between accounts are left out, the
exceptional deposits (sale, inheritance, gift) are kept apart, and the
deposits of the employer (profit-sharing, incentive, matching) are both income
and savings. An unknown origin is guessed: a movement matching a movement of
the opposite sign and the same amount on another account, a few days apart,
is a transfer; any other is income. The opening value of an account opened
during the year is a movement too, with the origin set on the account.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Prefetch
from django.urls import reverse

from base.services.ownership import HolderResolver
from budget.services.perspective import Perspective
from budget.services.property_flows import year_bounds
from finance.models.base import DepositOrigin
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountDeposit,
)
from finance.models.saving_account import SavingAccount, SavingAccountDeposit

#: Most days between the two movements of a guessed transfer.
TRANSFER_WINDOW_DAYS = 7

Account = SavingAccount | InvestmentAccount


def account_kind(account: Account) -> str:
    """ "saving" or "investment"."""
    return "saving" if isinstance(account, SavingAccount) else "investment"


def account_key(account: Account) -> str:
    """Identifier of an account, stable from one year to the next."""
    return f"account:{account_kind(account)}:{account.pk}"


def account_url(account: Account) -> str:
    """Detail page of an account."""
    if isinstance(account, SavingAccount):
        return reverse("finance:saving_detail", kwargs={"pk": account.pk})
    return reverse("finance:investment_detail", kwargs={"pk": account.pk})


@dataclass
class Movement:
    """A deposit, a withdrawal (negative) or the opening value of an account."""

    account: Account
    day: datetime.date
    amount: Decimal
    origin: str
    #: Origin guessed for an unknown one.
    guessed: str | None = None
    #: True for the opening value of an account opened during the year.
    opening: bool = False

    @property
    def effective_origin(self) -> str:
        """The origin set on the deposit, or the guessed one."""
        return self.guessed or self.origin

    @property
    def url(self) -> str:
        """Where the origin is set: the deposits, or the account for its opening value."""
        if self.opening:
            kind = account_kind(self.account)
            return reverse(f"finance:edit_{kind}", kwargs={"pk": self.account.pk})
        return account_url(self.account) + "#deposits-panel"


@dataclass(frozen=True)
class AccountFlows:
    """Money put into one account during a year, for the part of the perspective."""

    account: Account
    #: Deposits from the income minus withdrawals for the household.
    amount: Decimal
    #: Deposits of exceptional origin (sale, inheritance, gift).
    exceptional: Decimal = Decimal(0)
    #: Deposits of the employer (profit-sharing, incentive, matching).
    employer: Decimal = Decimal(0)

    @property
    def kind(self) -> str:
        """ "saving" or "investment"."""
        return account_kind(self.account)

    @property
    def key(self) -> str:
        """Identifier of the account, stable from one year to the next."""
        return account_key(self.account)

    @property
    def url(self) -> str:
        """Detail page of the account."""
        return account_url(self.account)


@dataclass(frozen=True)
class FinanceFlows:
    """Flows of the accounts in a year, and the movements whose origin was guessed."""

    accounts: list[AccountFlows] = field(default_factory=list)
    guesses: list[Movement] = field(default_factory=list)


def guess_origins(movements: list[Movement]) -> None:
    """Guess the origin of the movements of unknown origin, in place.

    In date order, an unknown movement is a transfer when another account has
    a movement of the opposite sign and the same amount, of unknown or
    transfer origin and not paired yet, at most TRANSFER_WINDOW_DAYS days
    apart (the closest one is paired); otherwise it is income.
    """
    candidates = [
        m
        for m in movements
        if m.origin in (DepositOrigin.UNKNOWN, DepositOrigin.TRANSFER) and m.amount
    ]
    paired: set[int] = set()
    window = datetime.timedelta(days=TRANSFER_WINDOW_DAYS)
    for movement in sorted(candidates, key=lambda m: m.day):
        if movement.origin != DepositOrigin.UNKNOWN or id(movement) in paired:
            continue
        key = account_key(movement.account)
        matches = [
            other
            for other in candidates
            if id(other) not in paired
            and other is not movement
            and account_key(other.account) != key
            and other.amount == -movement.amount
            and abs(other.day - movement.day) <= window
        ]
        if not matches:
            movement.guessed = DepositOrigin.INCOME
            continue
        other = min(matches, key=lambda m: abs(m.day - movement.day))
        paired.update((id(movement), id(other)))
        movement.guessed = DepositOrigin.TRANSFER
        if other.origin == DepositOrigin.UNKNOWN:
            other.guessed = DepositOrigin.TRANSFER


def _movements(
    first: datetime.date, last: datetime.date, currency: str
) -> list[Movement]:
    """Movements of the accounts in *currency* from *first* to *last*."""
    movements = []
    deposit_ranges = (
        (
            SavingAccount,
            SavingAccountDeposit,
            {
                "deposit_date__gte": datetime.datetime.combine(first, datetime.time()),
                "deposit_date__lt": datetime.datetime.combine(
                    last + datetime.timedelta(days=1), datetime.time()
                ),
            },
        ),
        (
            InvestmentAccount,
            InvestmentAccountDeposit,
            {"deposit_date__range": (first, last)},
        ),
    )
    for model, deposit_model, period in deposit_ranges:
        accounts = (
            model.objects.filter(opening_date__lte=last)
            .select_related("account_type")
            .prefetch_related(
                Prefetch("deposits", queryset=deposit_model.objects.filter(**period))
            )
            .order_by("name")
        )
        for account in accounts:
            if account.currency != currency:
                continue
            if first <= account.opening_date <= last and account.opening_amount.amount:
                movements.append(
                    Movement(
                        account=account,
                        day=account.opening_date,
                        amount=account.opening_amount.amount,
                        origin=account.opening_origin,
                        opening=True,
                    )
                )
            for deposit in account.deposits.all():
                if str(deposit.amount.currency) != currency:
                    continue
                day = deposit.deposit_date
                if isinstance(day, datetime.datetime):
                    day = day.date()
                movements.append(
                    Movement(
                        account=account,
                        day=day,
                        amount=deposit.amount.amount,
                        origin=deposit.origin,
                    )
                )
    return movements


def account_year_flows(
    year: int,
    perspective: Perspective,
    *,
    currency: str,
    resolver: HolderResolver | None = None,
) -> FinanceFlows:
    """Money put into each account in *year*, for the part of the perspective.

    The opening value of an account opened during the year counts as a
    deposit, as in the performance of the accounts, with the origin set on
    the account.
    Transfers between accounts and exceptional withdrawals (spent outside the
    budget, e.g. on a property purchase) are left out. Accounts in another
    currency than *currency* are left out.
    """
    first, last = year_bounds(year)
    window = datetime.timedelta(days=TRANSFER_WINDOW_DAYS)
    resolver = resolver or HolderResolver()
    # The movements just outside the year are read to pair the transfers
    # made around the new year.
    movements = _movements(first - window, last + window, currency)
    guess_origins(movements)

    # Per account: the account, the ratio of the perspective and the sums of
    # each origin counted.
    totals: dict[str, tuple[Account, Decimal, dict[str, Decimal]]] = {}
    guesses = []
    for movement in movements:
        if not first <= movement.day <= last:
            continue
        key = account_key(movement.account)
        if key not in totals:
            ratio = perspective.asset_ratio(resolver.rows(movement.account))
            totals[key] = (movement.account, ratio, {})
        _account, ratio, sums = totals[key]
        if not ratio:
            continue
        if movement.origin == DepositOrigin.UNKNOWN:
            guesses.append(movement)
        origin = movement.effective_origin
        # Exceptional and employer withdrawals mean nothing: they are left out.
        if origin == DepositOrigin.INCOME or (
            origin in (DepositOrigin.EXCEPTIONAL, DepositOrigin.EMPLOYER)
            and movement.amount > 0
        ):
            sums[origin] = sums.get(origin, Decimal(0)) + movement.amount * ratio
    accounts = [
        AccountFlows(
            account=account,
            amount=sums.get(DepositOrigin.INCOME, Decimal(0)),
            exceptional=sums.get(DepositOrigin.EXCEPTIONAL, Decimal(0)),
            employer=sums.get(DepositOrigin.EMPLOYER, Decimal(0)),
        )
        for account, _ratio, sums in totals.values()
        if any(sums.values())
    ]
    return FinanceFlows(accounts=accounts, guesses=sorted(guesses, key=lambda m: m.day))
