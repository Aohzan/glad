"""Value progression helpers for property assets."""

from decimal import Decimal
from typing import TYPE_CHECKING

from moneyed import Money

if TYPE_CHECKING:
    from property.models import Property


class PropertyProgression:
    """Encapsulates the value progression of a property between two dates."""

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
        """Return a string representation of the PropertyProgression."""
        return f"{self.progression}% ({self.difference.amount})"


class PropertyRentability:
    """Placeholder for future rentability calculation.

    TODO: Implement rentability calculation (rendement locatif brut/net).
    """

    rentability_percent: Decimal
    css_class: str

    def __init__(self, property: "Property") -> None:
        raise NotImplementedError("PropertyRentability calculation not implemented yet")

    def __str__(self) -> str:
        """Return a string representation of the PropertyRentability."""
        return f"{self.rentability_percent}%"
