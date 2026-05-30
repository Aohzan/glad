"""Loan math utilities: amortization, monthly payment, and monthly map builders."""

import calendar
import datetime
from decimal import ROUND_HALF_UP, Decimal

from property.utils.date_utils import add_months_safe, month_start


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


def build_loan_amortization_balance(
    *,
    original_amount: Decimal,
    interest_rate: Decimal | None,
    payment_sequence: list[Decimal],
    months_elapsed: int,
    disbursement_date: datetime.date | None = None,
    first_payment_date: datetime.date | None = None,
) -> Decimal:
    """Simulate real amortization and return the remaining balance after N months.

    Works for both standard loans (uniform payment_sequence) and smoothed loans
    (prêt lisseur, variable payment_sequence).

    Args:
        original_amount: Initial loan capital.
        interest_rate: Annual interest rate in percent (e.g. Decimal("3.5")).
        payment_sequence: Ordered list of monthly payment amounts.
        months_elapsed: How many months have passed since loan start.
        disbursement_date: Date the loan was disbursed. Used together with
            first_payment_date to compute a prorated first-period interest.
        first_payment_date: Date of the first bank debit. When provided alongside
            disbursement_date, the first period's interest is calculated using the
            actual number of days (actual/365) to match the bank's table.

    Returns:
        Remaining capital balance as a Decimal (≥ 0).
    """
    annual_rate = Decimal("0")
    monthly_rate = Decimal("0")
    if interest_rate:
        annual_rate = interest_rate / Decimal("100")
        monthly_rate = annual_rate / Decimal("12")

    use_prorated_first = (
        disbursement_date is not None
        and first_payment_date is not None
        and first_payment_date != disbursement_date
    )

    balance = original_amount
    for i in range(min(months_elapsed, len(payment_sequence))):
        if use_prorated_first and i == 0:
            days = Decimal((first_payment_date - disbursement_date).days)  # type: ignore[operator]
            days_in_month = Decimal(
                calendar.monthrange(disbursement_date.year, disbursement_date.month)[1]
            )  # type: ignore[union-attr]
            interest_amount = (balance * monthly_rate * days / days_in_month).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            interest_amount = (balance * monthly_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        principal_amount = payment_sequence[i] - interest_amount
        if principal_amount < Decimal("0"):
            principal_amount = Decimal("0")
        if principal_amount > balance:
            principal_amount = balance
        balance -= principal_amount
        if balance <= Decimal("0"):
            return Decimal("0")

    return max(Decimal("0"), balance)


def build_loan_monthly_maps(
    *,
    start_date: datetime.date,
    end_date: datetime.date,
    original_amount: Decimal,
    monthly_payment: Decimal | None = None,
    interest_rate: Decimal | None,
    insurance_amount: Decimal,
    payment_sequence: list[Decimal] | None = None,
    disbursement_date: datetime.date | None = None,
    first_payment_date: datetime.date | None = None,
) -> tuple[
    dict[tuple[int, int], Decimal],
    dict[tuple[int, int], Decimal],
    dict[tuple[int, int], Decimal],
]:
    """Build monthly interest/principal/insurance maps for a loan amortization.

    Supports both standard loans (uniform monthly_payment) and smoothed loans
    (prêt lisseur) via payment_sequence.

    Args:
        start_date: Disbursement date (used as loop start when first_payment_date
            is not provided, for backwards compatibility).
        end_date: Last payment date.
        original_amount: Initial loan capital.
        monthly_payment: Fixed monthly payment (used when payment_sequence is None).
        interest_rate: Annual interest rate in percent.
        insurance_amount: Fixed monthly insurance amount.
        payment_sequence: Ordered list of monthly payment amounts (smoothed loans).
            When provided, takes precedence over monthly_payment.
        disbursement_date: Date the loan was disbursed. Used together with
            first_payment_date to compute a prorated first-period interest.
        first_payment_date: Date of the first bank debit. When provided, the monthly
            map loop starts from this date's month, and the first period's interest
            is computed using the actual number of days (actual/365).
    """
    interest_by_month: dict[tuple[int, int], Decimal] = {}
    principal_by_month: dict[tuple[int, int], Decimal] = {}
    insurance_by_month: dict[tuple[int, int], Decimal] = {}

    annual_rate = Decimal("0")
    monthly_rate = Decimal("0")
    if interest_rate:
        annual_rate = interest_rate / Decimal("100")
        monthly_rate = annual_rate / Decimal("12")

    loop_start_date = (
        first_payment_date if first_payment_date is not None else start_date
    )
    use_prorated_first = (
        disbursement_date is not None
        and first_payment_date is not None
        and first_payment_date != disbursement_date
    )

    current = month_start(loop_start_date)
    end_month = month_start(end_date)
    remaining_balance = original_amount
    months_count = (
        (end_month.year - current.year) * 12 + (end_month.month - current.month) + 1
    )

    for step in range(max(0, months_count)):
        key = (current.year, current.month)

        # Determine payment for this month
        if payment_sequence is not None:
            if step < len(payment_sequence):
                payment = payment_sequence[step]
            else:
                break
        elif monthly_payment is not None:
            payment = monthly_payment
        else:
            break

        if use_prorated_first and step == 0:
            days = Decimal((first_payment_date - disbursement_date).days)  # type: ignore[operator]
            days_in_month = Decimal(
                calendar.monthrange(disbursement_date.year, disbursement_date.month)[1]
            )  # type: ignore[union-attr]
            interest_amount = (
                remaining_balance * monthly_rate * days / days_in_month
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            interest_amount = (remaining_balance * monthly_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        principal_amount = payment - interest_amount
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


def build_loan_maps_from_loan_obj(
    loan,
    insurance_amount: Decimal,
) -> tuple[
    dict[tuple[int, int], Decimal],
    dict[tuple[int, int], Decimal],
    dict[tuple[int, int], Decimal],
]:
    """Build monthly maps for a PropertyLoan model object.

    Convenience wrapper around build_loan_monthly_maps that reads
    the required fields from the loan object directly.
    """
    monthly_payment_amount = (
        loan.monthly_payment.amount
        if loan.monthly_payment is not None
        else Decimal("0")
    )
    return build_loan_monthly_maps(
        start_date=loan.start_date,
        end_date=loan.end_date,
        original_amount=loan.original_amount.amount,
        monthly_payment=monthly_payment_amount,
        interest_rate=loan.interest_rate,
        insurance_amount=insurance_amount,
        disbursement_date=loan.start_date,
        first_payment_date=loan.first_payment_date,
    )
