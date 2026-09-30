"""Interest estimate of French regulated savings books ("règle des quinzaines").

The year is split into 24 fortnights (1st–15th and 16th–end of each month).
A deposit earns interest from the fortnight following its date, a withdrawal
stops earning from the start of the fortnight in which it happens. Interest is
computed on each fortnight balance at a 1/24th of the yearly rate and credited
on 31 December.
"""

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from finance.models.saving_account import SavingAccount

FORTNIGHTS_PER_YEAR = 24
CENT = Decimal("0.01")


def fortnight_index(day: datetime.date) -> int:
    """Index (0–23) of the fortnight containing *day* in its year."""
    return (day.month - 1) * 2 + (0 if day.day <= 15 else 1)


def fortnight_start(index: int, year: int) -> datetime.date:
    """First day of the fortnight *index* of *year*."""
    return datetime.date(year, index // 2 + 1, 1 if index % 2 == 0 else 16)


def effective_fortnight(day: datetime.date, amount: Decimal) -> int:
    """First fortnight index in which a movement of *amount* on *day* counts.

    Deposits count from the next fortnight (24 means next year), withdrawals
    from the current one.
    """
    index = fortnight_index(day)
    return index + 1 if amount > 0 else index


@dataclass(frozen=True)
class InterestEstimate:
    """Interest of a year: earned on elapsed fortnights and projected on Dec 31."""

    year: int
    rate: Decimal
    currency: str
    earned_to_date: Decimal
    projected_year_end: Decimal
    elapsed_fortnights: int


def estimate_interest(
    start_balance: Decimal,
    movements: list[tuple[datetime.date, Decimal]],
    rate: Decimal,
    year: int,
    today: datetime.date,
    currency: str,
) -> InterestEstimate:
    """Estimate the interest of *year* from the balance on 1 January and the movements.

    Movements outside *year* are ignored. Future fortnights keep the last known
    balance, so the projection assumes no further movement.
    """
    deltas = [Decimal(0)] * (FORTNIGHTS_PER_YEAR + 1)
    for day, amount in movements:
        if day.year == year:
            deltas[effective_fortnight(day, amount)] += amount

    if today.year < year:
        elapsed = 0
    elif today.year > year:
        elapsed = FORTNIGHTS_PER_YEAR
    else:
        # A fortnight is elapsed once the next one has started.
        elapsed = fortnight_index(today)

    balance = start_balance
    earned = Decimal(0)
    projected = Decimal(0)
    for index in range(FORTNIGHTS_PER_YEAR):
        balance += deltas[index]
        interest = max(Decimal(0), balance) * rate / 100 / FORTNIGHTS_PER_YEAR
        projected += interest
        if index < elapsed:
            earned += interest

    return InterestEstimate(
        year=year,
        rate=rate,
        currency=currency,
        earned_to_date=earned.quantize(CENT, rounding=ROUND_HALF_UP),
        projected_year_end=projected.quantize(CENT, rounding=ROUND_HALF_UP),
        elapsed_fortnights=elapsed,
    )


def estimate_account_interest(
    account: SavingAccount, today: datetime.date | None = None
) -> InterestEstimate | None:
    """Estimate this year's interest of a fortnight-based saving account.

    Returns None for closed accounts, envelopes that do not follow the
    fortnight rule and accounts without interest rate. The balance on 1 January comes from the value
    history; the deposits of the year are the movements. An account opened
    during the year starts at zero and its opening value counts as a deposit.
    """
    if (
        not account.is_active
        or not account.envelope_rule.fortnight_interest
        or not account.interest_rate
    ):
        return None
    today = today or datetime.date.today()
    year = today.year
    movements = [
        (d.deposit_date.date(), d.amount.amount)
        for d in account.deposits.filter(deposit_date__year=year)
    ]
    if account.opening_date.year == year:
        start_balance = Decimal(0)
        movements.append((account.opening_date, account.opening_value.amount))
    else:
        start_balance = account.get_value(
            max_date=datetime.datetime(year - 1, 12, 31, 23, 59, 59)
        ).amount
    return estimate_interest(
        start_balance=start_balance,
        movements=movements,
        rate=account.interest_rate,
        year=year,
        today=today,
        currency=account.currency,
    )
