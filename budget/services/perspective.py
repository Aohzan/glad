"""Whose part of a budget is shown: the whole household or one of its members."""

from dataclasses import dataclass
from decimal import Decimal

from accounts.models import is_child
from base.models import Ownership, household_members
from base.services.ownership import flow_ratio


@dataclass(frozen=True)
class Perspective:
    """The household as a whole, or one member and their part of the budget.

    For one member, the items named for them count in full, the items of the
    whole household (budget lines without person, assets without owner) are
    split equally between the adults, and the items named for another member
    do not count. A child therefore only gets the items named for them.
    """

    person_id: int | None
    members: frozenset[int]
    adults: int
    person_is_child: bool = False

    @classmethod
    def build(cls, person=None) -> Perspective:
        """Perspective of *person*, or of the whole household when None."""
        members = list(household_members())
        return cls(
            person_id=person.pk if person is not None else None,
            members=frozenset(m.pk for m in members),
            adults=sum(1 for m in members if not is_child(m)),
            person_is_child=person is not None and is_child(person),
        )

    @property
    def is_household(self) -> bool:
        """True for the whole household."""
        return self.person_id is None

    @property
    def shared_ratio(self) -> Decimal:
        """Part of an item of the whole household."""
        if self.is_household:
            return Decimal(1)
        if self.person_is_child or not self.adults:
            return Decimal(0)
        return Decimal(1) / self.adults

    def line_ratio(self, person_id: int | None) -> Decimal:
        """Part of a budget line assigned to *person_id* (None for the household)."""
        if self.is_household:
            return Decimal(1)
        if person_id is None:
            return self.shared_ratio
        return Decimal(1) if person_id == self.person_id else Decimal(0)

    def asset_ratio(self, rows: list[Ownership], *, capital: bool = False) -> Decimal:
        """Part of the flows of an asset held through the ownership *rows*.

        *capital* selects the bare owner's side of a dismembered asset (loan
        installments, purchases) instead of the usufructuary's (income and
        running costs).
        """
        if not rows:
            return self.shared_ratio
        people = set(self.members) if self.person_id is None else {self.person_id}
        return flow_ratio(rows, people, capital=capital)
