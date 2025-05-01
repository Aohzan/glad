"""Utils for finance-related calculations."""

from decimal import Decimal

from moneyed import Money


class AccountProgression:
    """Class representing the progression of an account."""

    gross_progression: Decimal
    gross_difference: Money
    net_progression: Decimal
    net_difference: Money
    css_class: str

    def __init__(
        self,
        current_value: Money,
        old_value: Money | None,
        deposits: Money | None = None,
    ):
        """Initialize the AccountProgression instance."""
        if not isinstance(current_value, Money):
            raise TypeError("current_value must be a Money")
        if old_value is not None and not isinstance(old_value, Money):
            raise TypeError("old_value must be a Money or None")
        if deposits is not None and not isinstance(deposits, Money):
            raise TypeError("deposits must be a Money or None")
        if old_value is None:
            old_value = current_value
        if deposits is None:
            deposits = Money(0, current_value.currency)

        # Calculate progression percentage (gross), avoiding division by zero
        if old_value.amount == 0:
            # If old value is zero, progression is 100% if current > 0, 0% if current = 0
            progression_value = 100.0 if current_value.amount > 0 else 0.0
        else:
            progression_value = round(
                ((current_value.amount - old_value.amount) / old_value.amount) * 100,
                2,
            )

        self.gross_progression = Decimal(progression_value)
        self.gross_difference = Money(
            float(round((current_value.amount - old_value.amount), 0)),
            current_value.currency,
        )

        # Calculate net progression (excluding deposits)
        net_difference_amount = (
            current_value.amount - old_value.amount - deposits.amount
        )
        self.net_difference = Money(
            float(round(net_difference_amount, 0)),
            current_value.currency,
        )

        if old_value.amount == 0:
            # When old value is 0, if we have positive net difference, progression is 100%
            net_progression_value = 100.0 if net_difference_amount > 0 else 0.0
        else:
            net_progression_value = round(
                (net_difference_amount / old_value.amount) * 100,
                2,
            )

        self.net_progression = Decimal(net_progression_value)

        # CSS class based on net progression by default (for backwards compatibility display)
        self.css_class = (
            "up"
            if self.net_difference.amount > 0
            else "down"
            if self.net_difference.amount < 0
            else "neutral"
        )

    def __str__(self) -> str:
        """Return a string representation of the AccountProgression."""
        return f"{self.net_progression}% ({self.net_difference.amount})"
