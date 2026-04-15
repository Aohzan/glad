import calendar
import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from moneyed import Money

if TYPE_CHECKING:
    from property.models import Property


def add_months_safe(base_date: datetime.date, months: int = 1) -> datetime.date:
    """Add months to a date while clamping to the month last day when needed."""
    total_month = (base_date.year * 12 + (base_date.month - 1)) + months
    year = total_month // 12
    month = (total_month % 12) + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def add_years_safe(base_date: datetime.date, years: int = 1) -> datetime.date:
    """Add years to a date while keeping leap years safe."""
    try:
        return base_date.replace(year=base_date.year + years)
    except ValueError:
        return base_date.replace(month=2, day=28, year=base_date.year + years)


def month_start(value: datetime.date) -> datetime.date:
    """Return the first day of the month for a date."""
    return value.replace(day=1)


def month_end(value: datetime.date) -> datetime.date:
    """Return the last day of the month for a date."""
    last_day = calendar.monthrange(value.year, value.month)[1]
    return value.replace(day=last_day)


def iter_month_starts(
    start_month: datetime.date,
    end_month: datetime.date,
) -> list[datetime.date]:
    """Return first-of-month dates from start to end (inclusive)."""
    current = month_start(start_month)
    limit = month_start(end_month)
    months: list[datetime.date] = []
    while current <= limit:
        months.append(current)
        current = add_months_safe(current, 1)
    return months


def generate_recurring_occurrences(
    *,
    start_date: datetime.date,
    amount: Money,
    recurrence_type: str,
    recurrence_none: str,
    recurrence_monthly: str,
    recurrence_yearly: str,
    recurrence_end_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> list[dict]:
    """Generate occurrences for a one-time or recurring monetary item."""
    if recurrence_type == recurrence_none:
        return [
            {
                "date": start_date,
                "amount": amount,
                "is_recurring": False,
            }
        ]

    occurrences = []
    current = start_date
    max_date = end_date or recurrence_end_date or datetime.date.today()

    # Only process recurring types if valid
    is_valid_recurrence = recurrence_type in (
        recurrence_monthly,
        recurrence_yearly,
    )

    while current <= max_date:
        occurrences.append(
            {
                "date": current,
                "amount": amount,
                "is_recurring": is_valid_recurrence,  # Only true for valid recurring types
            }
        )

        if recurrence_type == recurrence_monthly:
            current = add_months_safe(current, 1)
            continue
        if recurrence_type == recurrence_yearly:
            current = add_years_safe(current, 1)
            continue
        break

    return (
        occurrences
        if occurrences
        else [
            {
                "date": start_date,
                "amount": amount,
                "is_recurring": False,
            }
        ]
    )


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
        return Decimal("0"), Decimal("0"), Decimal("0")

    monthly_rate = (annual_interest_rate / Decimal("100")) / Decimal("12")

    if monthly_rate == Decimal("0"):
        monthly_pi = (original_amount / Decimal(duration_months)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        # Standard French amortization: M = C * t(1+t)^n / ((1+t)^n - 1)
        factor = (Decimal("1") + monthly_rate) ** duration_months
        monthly_pi = (
            original_amount * monthly_rate * factor / (factor - Decimal("1"))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    monthly_insurance = Decimal("0")
    if annual_insurance_rate:
        monthly_insurance = (
            original_amount * annual_insurance_rate / Decimal("100") / Decimal("12")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total_monthly = monthly_pi + monthly_insurance
    return monthly_pi, monthly_insurance, total_monthly


def build_loan_monthly_maps(
    *,
    start_date: datetime.date,
    end_date: datetime.date,
    original_amount: Decimal,
    monthly_payment: Decimal,
    interest_rate: Decimal | None,
    insurance_amount: Decimal,
) -> tuple[
    dict[tuple[int, int], Decimal],
    dict[tuple[int, int], Decimal],
    dict[tuple[int, int], Decimal],
]:
    """Build monthly interest/principal/insurance maps for a loan amortization."""
    interest_by_month: dict[tuple[int, int], Decimal] = {}
    principal_by_month: dict[tuple[int, int], Decimal] = {}
    insurance_by_month: dict[tuple[int, int], Decimal] = {}

    monthly_rate = Decimal("0")
    if interest_rate:
        monthly_rate = (interest_rate / Decimal("100")) / Decimal("12")

    current = month_start(start_date)
    end_month = month_start(end_date)
    remaining_balance = original_amount
    months_count = (
        (end_month.year - current.year) * 12 + (end_month.month - current.month) + 1
    )

    for _ in range(max(0, months_count)):
        key = (current.year, current.month)

        interest_amount = remaining_balance * monthly_rate
        principal_amount = monthly_payment - interest_amount
        if principal_amount < Decimal("0"):
            principal_amount = Decimal("0")
        if principal_amount > remaining_balance:
            principal_amount = remaining_balance

        interest_by_month[key] = (
            interest_by_month.get(key, Decimal("0")) + interest_amount
        )
        principal_by_month[key] = (
            principal_by_month.get(key, Decimal("0")) + principal_amount
        )
        if insurance_amount:
            insurance_by_month[key] = (
                insurance_by_month.get(key, Decimal("0")) + insurance_amount
            )

        remaining_balance -= principal_amount
        if remaining_balance <= Decimal("0"):
            break
        current = add_months_safe(current, 1)

    return interest_by_month, principal_by_month, insurance_by_month


class PropertyProgression:
    progression: Decimal
    difference: Money
    css_class: str

    def __init__(
        self,
        current_value: Money,
        old_value: Money,
    ):
        if old_value.amount == 0:
            # If old value is zero, progression is 100% if current > 0, 0% if current = 0
            progression_value = 100.0 if current_value.amount > 0 else 0.0
        else:
            progression_value = round(
                ((current_value.amount - old_value.amount) / old_value.amount) * 100,
                2,
            )
        self.progression = Decimal(round(progression_value))
        self.difference = Money(
            float(round((current_value.amount - old_value.amount), 0)),
            current_value.currency,
        )

        if self.progression > 0:
            self.css_class = "text-success"
        elif self.progression < 0:
            self.css_class = "text-danger"
        else:
            self.css_class = "text-muted"

    def __str__(self) -> str:
        """Return a string representation of the AccountProgression."""
        return f"{self.progression}% ({self.difference.amount})"


class PropertyRentability:
    rentability_percent: Decimal
    css_class: str

    def __init__(self, property: "Property") -> None:
        raise NotImplementedError("PropertyRentability calculation not implemented yet")

    def __str__(self) -> str:
        """Return a string representation of the PropertyRentability."""
        return f"{self.rentability_percent}%"
