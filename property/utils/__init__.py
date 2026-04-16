"""Property utils package — re-exports all utilities for backward-compatible imports."""

from property.utils.date_utils import (
    add_months_safe,
    add_years_safe,
    iter_month_starts,
    month_end,
    month_start,
)
from property.utils.loan_utils import (
    build_loan_amortization_balance,
    build_loan_monthly_maps,
    calculate_monthly_payment,
)
from property.utils.progression import PropertyProgression, PropertyRentability
from property.utils.recurrence_utils import generate_recurring_occurrences

__all__ = [
    # date helpers
    "add_months_safe",
    "add_years_safe",
    "iter_month_starts",
    "month_end",
    "month_start",
    # loan math
    "calculate_monthly_payment",
    "build_loan_amortization_balance",
    "build_loan_monthly_maps",
    # recurrence
    "generate_recurring_occurrences",
    # value classes
    "PropertyProgression",
    "PropertyRentability",
]
