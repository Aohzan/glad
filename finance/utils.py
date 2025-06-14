"""Utils for finance-related calculations."""

from moneyed import Money


class AccountProgression:
    """Class representing the progression of an account."""

    progression: Money
    difference: Money
    css_class: str

    def __init__(self, current_balance: Money, old_balance: Money | None):
        """Initialize the AccountProgression instance."""
        if not isinstance(current_balance, Money):
            raise TypeError("current_balance must be a Money")
        if old_balance is not None and not isinstance(old_balance, Money):
            raise TypeError("old_balance must be a Money or None")
        if not old_balance:
            old_balance = current_balance

        self.progression = Money(
            round(
                ((current_balance.amount - old_balance.amount) / old_balance.amount)
                * 100,
                2,
            ),
            current_balance.currency,
        )
        self.difference = Money(
            float(round((current_balance.amount - old_balance.amount), 0)),
            current_balance.currency,
        )
        self.css_class = (
            "positive"
            if self.difference.amount > 0
            else "negative"
            if self.difference.amount < 0
            else "neutral"
        )

    def __str__(self) -> str:
        """Return a string representation of the AccountProgression."""
        return f"{self.progression}% ({self.difference.amount})"
