"""Property utils package — re-exports all utilities for backward-compatible imports."""

from property.utils.date_utils import (
    add_months_safe,
    add_years_safe,
    days360,
    iter_month_starts,
    month_end,
    month_start,
)
from property.utils.loan_utils import (
    Installment,
    LoanCosts,
    Schedule,
    build_loan_amortization_balance,
    build_loan_maps_from_loan_obj,
    build_loan_monthly_maps,
    build_schedule,
    calculate_monthly_payment,
    count_installments,
    due_date,
    schedule_from_table,
)
from property.utils.progression import PropertyProgression, PropertyRentability
from property.utils.recurrence_utils import generate_recurring_occurrences

__all__ = [
    # value classes
    "Installment",
    "LoanCosts",
    "PropertyProgression",
    "PropertyRentability",
    "Schedule",
    # date helpers
    "add_months_safe",
    "add_years_safe",
    "build_loan_amortization_balance",
    "build_loan_maps_from_loan_obj",
    "build_loan_monthly_maps",
    "build_schedule",
    # loan math
    "calculate_monthly_payment",
    "count_installments",
    "days360",
    "due_date",
    # recurrence
    "generate_recurring_occurrences",
    "iter_month_starts",
    "month_end",
    "month_start",
    "schedule_from_table",
]
