"""Loan math utilities: monthly payment and amortization schedule."""

import bisect
import datetime
import itertools
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from property.utils.date_utils import add_months_safe

CENT = Decimal("0.01")
#: Day count of the broken first period (actual/365, the French legal basis).
DAYS_PER_YEAR = Decimal(365)


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_monthly_payment(
    *,
    original_amount: Decimal,
    annual_interest_rate: Decimal,
    annual_insurance_rate: Decimal | None,
    duration_months: int,
) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate the monthly payment for a loan using the French amortization formula.

    Returns a tuple of (monthly_principal_and_interest, monthly_insurance, total_monthly).
    When interest_rate is 0, the payment is simply capital / duration.
    """
    if duration_months <= 0:
        return Decimal(0), Decimal(0), Decimal(0)

    monthly_rate = (annual_interest_rate / Decimal(100)) / Decimal(12)

    if monthly_rate == Decimal(0):
        monthly_pi = (original_amount / Decimal(duration_months)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        # Standard French amortization: M = C * t(1+t)^n / ((1+t)^n - 1)
        factor = (Decimal(1) + monthly_rate) ** duration_months
        monthly_pi = (
            original_amount * monthly_rate * factor / (factor - Decimal(1))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    monthly_insurance = Decimal(0)
    if annual_insurance_rate:
        monthly_insurance = (
            original_amount * annual_insurance_rate / Decimal(100) / Decimal(12)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total_monthly = monthly_pi + monthly_insurance
    return monthly_pi, monthly_insurance, total_monthly


def due_date(
    disbursement_date: datetime.date,
    first_payment_date: datetime.date | None,
    index: int,
) -> datetime.date:
    """Date of the installment number *index* (0 for the first one).

    The first installment falls on *first_payment_date*, or one month after
    the disbursement when it is unknown. Every date is computed from that
    anchor rather than from the previous installment, so a loan debited on
    the 31st comes back to the 31st after a shorter month.
    """
    if first_payment_date is not None:
        return add_months_safe(first_payment_date, index)
    return add_months_safe(disbursement_date, index + 1)


def count_installments(
    disbursement_date: datetime.date,
    first_payment_date: datetime.date | None,
    end_date: datetime.date,
) -> int:
    """Number of monthly installments from the first one to *end_date* included."""
    first = due_date(disbursement_date, first_payment_date, 0)
    return (end_date.year - first.year) * 12 + end_date.month - first.month + 1


@dataclass(frozen=True)
class LoanCosts:
    """Principal, interest and insurance paid over some installments."""

    principal: Decimal = Decimal(0)
    interest: Decimal = Decimal(0)
    insurance: Decimal = Decimal(0)

    @property
    def total(self) -> Decimal:
        return self.principal + self.interest + self.insurance

    def __add__(self, other: LoanCosts) -> LoanCosts:
        return LoanCosts(
            self.principal + other.principal,
            self.interest + other.interest,
            self.insurance + other.insurance,
        )

    def __sub__(self, other: LoanCosts) -> LoanCosts:
        return LoanCosts(
            self.principal - other.principal,
            self.interest - other.interest,
            self.insurance - other.insurance,
        )


@dataclass(frozen=True)
class Installment:
    """One monthly installment of a loan, and the capital owed after it."""

    date: datetime.date
    principal: Decimal
    interest: Decimal
    insurance: Decimal
    balance: Decimal

    @property
    def payment(self) -> Decimal:
        """Principal and interest, without the insurance."""
        return self.principal + self.interest

    @property
    def costs(self) -> LoanCosts:
        return LoanCosts(self.principal, self.interest, self.insurance)


class Schedule:
    """The installments of a loan, queried by date.

    Nothing is owed before the disbursement, the whole capital is owed until
    the first installment, and nothing is owed after *closed_on* (the date the
    property was sold and the loan repaid), whose later installments are
    dropped.
    """

    def __init__(
        self,
        *,
        capital: Decimal,
        disbursement_date: datetime.date,
        installments: Iterable[Installment],
        closed_on: datetime.date | None = None,
    ) -> None:
        kept = sorted(installments, key=lambda installment: installment.date)
        if closed_on is not None:
            kept = [i for i in kept if i.date <= closed_on]
        self.capital = capital
        self.disbursement_date = disbursement_date
        self.closed_on = closed_on
        self.installments: tuple[Installment, ...] = tuple(kept)
        self._dates = [i.date for i in self.installments]
        # _paid[k] holds the costs of the first k installments.
        self._paid = list(
            itertools.accumulate(
                (i.costs for i in self.installments), initial=LoanCosts()
            )
        )

    def __iter__(self) -> Iterator[Installment]:
        return iter(self.installments)

    def __len__(self) -> int:
        return len(self.installments)

    @property
    def last_date(self) -> datetime.date | None:
        return self._dates[-1] if self._dates else None

    @property
    def total(self) -> LoanCosts:
        """Costs of every installment."""
        return self._paid[-1]

    def balance_at(self, day: datetime.date) -> Decimal:
        """Capital owed at the end of *day*."""
        if day < self.disbursement_date or (
            self.closed_on is not None and day > self.closed_on
        ):
            return Decimal(0)
        count = bisect.bisect_right(self._dates, day)
        return self.installments[count - 1].balance if count else self.capital

    def paid_to(self, day: datetime.date) -> LoanCosts:
        """Costs of the installments dated up to *day* included."""
        return self._paid[bisect.bisect_right(self._dates, day)]

    def paid_between(
        self, first_day: datetime.date, last_day: datetime.date
    ) -> LoanCosts:
        """Costs of the installments dated from *first_day* to *last_day* included."""
        start = bisect.bisect_left(self._dates, first_day)
        end = bisect.bisect_right(self._dates, last_day)
        if end <= start:
            return LoanCosts()
        return self._paid[end] - self._paid[start]

    def next_installment(self, day: datetime.date) -> Installment | None:
        """The first installment dated on or after *day*, if any is left."""
        index = bisect.bisect_left(self._dates, day)
        return self.installments[index] if index < len(self.installments) else None

    def by_month(self) -> dict[tuple[int, int], LoanCosts]:
        """Costs of the installments grouped by ``(year, month)``."""
        months: dict[tuple[int, int], LoanCosts] = {}
        for installment in self.installments:
            key = (installment.date.year, installment.date.month)
            months[key] = months.get(key, LoanCosts()) + installment.costs
        return months


def build_schedule(
    *,
    capital: Decimal,
    annual_rate: Decimal,
    count: int,
    disbursement_date: datetime.date,
    first_payment_date: datetime.date | None = None,
    monthly_payment: Decimal | None = None,
    monthly_insurance: Decimal = Decimal(0),
    closed_on: datetime.date | None = None,
) -> Schedule:
    """French amortization schedule of a loan repaid in *count* installments.

    The installments are constant: each month pays the interest of the
    capital still owed (annual rate / 12) and repays the rest of
    *monthly_payment* (the annuity by default). When the first installment
    does not fall one month after the disbursement (broken period), only its
    interest changes, by the interest of the extra or missing days at the
    actual/365 day count, as banks do; its principal and every later
    installment stay the standard ones. The last installment repays whatever
    capital the rounding left, and a stored payment above the annuity ends
    the loan early.
    """
    installments: list[Installment] = []
    if count > 0 and capital > 0:
        rate = annual_rate / Decimal(100)
        monthly_rate = rate / Decimal(12)
        if monthly_payment is None:
            monthly_payment = calculate_monthly_payment(
                original_amount=capital,
                annual_interest_rate=annual_rate,
                annual_insurance_rate=None,
                duration_months=count,
            )[0]
        first_due = due_date(disbursement_date, first_payment_date, 0)
        broken_days = (first_due - add_months_safe(disbursement_date, 1)).days
        balance = capital
        for index in range(count):
            standard_interest = _cents(balance * monthly_rate)
            interest = standard_interest
            if index == 0 and broken_days:
                interest = _cents(
                    max(
                        Decimal(0),
                        balance * monthly_rate
                        + balance * rate * broken_days / DAYS_PER_YEAR,
                    )
                )
            principal = max(Decimal(0), monthly_payment - standard_interest)
            if index == count - 1 or principal >= balance:
                principal = balance
            balance -= principal
            installments.append(
                Installment(
                    date=due_date(disbursement_date, first_payment_date, index),
                    principal=principal,
                    interest=interest,
                    insurance=monthly_insurance,
                    balance=balance,
                )
            )
            if balance == 0:
                break
    return Schedule(
        capital=capital,
        disbursement_date=disbursement_date,
        installments=installments,
        closed_on=closed_on,
    )


def schedule_from_table(
    *,
    capital: Decimal,
    disbursement_date: datetime.date,
    rows: Iterable[tuple[datetime.date, Decimal, Decimal, Decimal]],
    monthly_insurance: Decimal = Decimal(0),
    closed_on: datetime.date | None = None,
) -> Schedule:
    """Schedule of a loan read from its amortization table.

    *rows* are ``(date, principal, interest, remaining balance)`` tuples as
    printed by the bank. The table has no insurance column, so the fixed
    monthly insurance of the loan is added to every row.
    """
    return Schedule(
        capital=capital,
        disbursement_date=disbursement_date,
        installments=(
            Installment(
                date=date,
                principal=principal,
                interest=interest,
                insurance=monthly_insurance,
                balance=balance,
            )
            for date, principal, interest, balance in rows
        ),
        closed_on=closed_on,
    )
