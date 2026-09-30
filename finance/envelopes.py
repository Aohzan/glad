"""French savings envelope rules: deposit ceilings, tax milestones and liquidity.

Rules are keyed by the account type ``code`` (see ``finance/fixtures``). Account
types without a known code get the default rule: no ceiling, no milestone and a
conditional liquidity.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from base.choices import Liquidity


@dataclass(frozen=True)
class Milestone:
    """A tax or contractual date reached a number of years after the opening."""

    years: int
    label: str | Promise


@dataclass(frozen=True)
class EnvelopeRule:
    """Regulatory rules of a savings envelope."""

    #: Maximum amount of deposits (opening value included), None when unlimited.
    deposit_ceiling: Decimal | None = None
    #: True when withdrawals free up room under the ceiling (regulated savings
    #: books), False when only the deposits count (PEA).
    withdrawals_free_ceiling: bool = True
    milestones: tuple[Milestone, ...] = field(default=())
    liquidity: str = Liquidity.CONDITIONAL
    #: Interest computed per fortnight ("règle des quinzaines").
    fortnight_interest: bool = False


DEFAULT_RULE = EnvelopeRule()

_PEA_MILESTONES = (
    Milestone(
        5,
        _("Withdrawals no longer close the plan and gains are exempt from income tax"),
    ),
)
_EMPLOYEE_SAVINGS_MILESTONES = (Milestone(5, _("First contributions can be released")),)

ENVELOPE_RULES: dict[str, EnvelopeRule] = {
    # Saving accounts
    "CPT": EnvelopeRule(liquidity=Liquidity.IMMEDIATE),
    "LA": EnvelopeRule(
        deposit_ceiling=Decimal(22950),
        liquidity=Liquidity.IMMEDIATE,
        fortnight_interest=True,
    ),
    "LJ": EnvelopeRule(
        deposit_ceiling=Decimal(1600),
        liquidity=Liquidity.IMMEDIATE,
        fortnight_interest=True,
    ),
    "LDDS": EnvelopeRule(
        deposit_ceiling=Decimal(12000),
        liquidity=Liquidity.IMMEDIATE,
        fortnight_interest=True,
    ),
    "LEP": EnvelopeRule(
        deposit_ceiling=Decimal(10000),
        liquidity=Liquidity.IMMEDIATE,
        fortnight_interest=True,
    ),
    "CEL": EnvelopeRule(
        deposit_ceiling=Decimal(15300),
        liquidity=Liquidity.IMMEDIATE,
        fortnight_interest=True,
    ),
    "PEL": EnvelopeRule(
        deposit_ceiling=Decimal(61200),
        withdrawals_free_ceiling=False,
        milestones=(
            Milestone(2, _("Closing no longer reduces the interest rate")),
            Milestone(10, _("Deposits are no longer allowed")),
            Milestone(15, _("Interest stops, the plan becomes a savings account")),
        ),
    ),
    "DIV": EnvelopeRule(liquidity=Liquidity.IMMEDIATE),
    # Investment accounts
    "PEA": EnvelopeRule(
        deposit_ceiling=Decimal(150000),
        withdrawals_free_ceiling=False,
        milestones=_PEA_MILESTONES,
    ),
    "PEA-PME": EnvelopeRule(
        # Shared with the PEA: PEA + PEA-PME deposits cannot exceed 225,000 €.
        deposit_ceiling=Decimal(225000),
        withdrawals_free_ceiling=False,
        milestones=_PEA_MILESTONES,
    ),
    "AV": EnvelopeRule(
        milestones=(
            Milestone(
                8,
                _(
                    "Yearly allowance on gains (4,600 € single, 9,200 € couple) "
                    "and reduced tax rate"
                ),
            ),
        ),
    ),
    "CTO": EnvelopeRule(liquidity=Liquidity.IMMEDIATE),
    "PER": EnvelopeRule(liquidity=Liquidity.LOCKED),
    "PERCOL": EnvelopeRule(liquidity=Liquidity.LOCKED),
    "PEI": EnvelopeRule(
        liquidity=Liquidity.LOCKED, milestones=_EMPLOYEE_SAVINGS_MILESTONES
    ),
    "PEE": EnvelopeRule(
        liquidity=Liquidity.LOCKED, milestones=_EMPLOYEE_SAVINGS_MILESTONES
    ),
}


def get_rule(code: str | None) -> EnvelopeRule:
    """Return the rule of an account type code, or the default rule."""
    return ENVELOPE_RULES.get(code or "", DEFAULT_RULE)


@dataclass(frozen=True)
class CeilingUsage:
    """How much of a deposit ceiling is used."""

    ceiling: Decimal
    contributed: Decimal
    currency: str

    @property
    def remaining(self) -> Decimal:
        """Room left under the ceiling (never negative)."""
        return max(Decimal(0), self.ceiling - self.contributed)

    @property
    def percent(self) -> float:
        """Usage percentage, capped at 100."""
        if not self.ceiling:
            return 100.0
        return min(100.0, float(self.contributed / self.ceiling * 100))

    @property
    def is_reached(self) -> bool:
        """True when no more deposit fits under the ceiling."""
        return self.contributed >= self.ceiling


@dataclass(frozen=True)
class MilestoneStatus:
    """A milestone of a given account, dated from its opening date."""

    date: datetime.date
    label: str | Promise
    years: int

    @property
    def is_reached(self) -> bool:
        """True once the milestone date is today or in the past."""
        return self.date <= datetime.date.today()

    @property
    def days_left(self) -> int:
        """Days until the milestone (0 once reached)."""
        return max(0, (self.date - datetime.date.today()).days)


def milestone_statuses(
    rule: EnvelopeRule, opening_date: datetime.date
) -> list[MilestoneStatus]:
    """Date the milestones of *rule* from *opening_date*."""
    return [
        MilestoneStatus(
            date=opening_date + relativedelta(years=m.years),
            label=m.label,
            years=m.years,
        )
        for m in rule.milestones
    ]
