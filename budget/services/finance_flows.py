"""Deposits and withdrawals of the saving and investment accounts over a year."""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Prefetch
from django.urls import reverse

from base.services.ownership import HolderResolver
from budget.services.perspective import Perspective
from budget.services.property_flows import year_bounds
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountDeposit,
)
from finance.models.saving_account import SavingAccount, SavingAccountDeposit


@dataclass(frozen=True)
class AccountFlows:
    """Net amount put into one account during a year (negative when withdrawn)."""

    account: SavingAccount | InvestmentAccount
    amount: Decimal

    @property
    def key(self) -> str:
        """Identifier of the account, stable from one year to the next."""
        kind = "saving" if isinstance(self.account, SavingAccount) else "investment"
        return f"account:{kind}:{self.account.pk}"

    @property
    def url(self) -> str:
        """Detail page of the account."""
        if isinstance(self.account, SavingAccount):
            return reverse("finance:saving_detail", kwargs={"pk": self.account.pk})
        return reverse("finance:investment_detail", kwargs={"pk": self.account.pk})


def account_year_flows(
    year: int,
    perspective: Perspective,
    *,
    currency: str,
    resolver: HolderResolver | None = None,
) -> list[AccountFlows]:
    """Net deposits of each account in *year*, for the part of the perspective.

    The opening value of an account opened during the year counts as a
    deposit, as in the performance of the accounts. Accounts in another
    currency than *currency* are left out.
    """
    first, last = year_bounds(year)
    resolver = resolver or HolderResolver()
    flows = []
    for model, deposit_model in (
        (SavingAccount, SavingAccountDeposit),
        (InvestmentAccount, InvestmentAccountDeposit),
    ):
        accounts = (
            model.objects.filter(opening_date__lte=last)
            .select_related("account_type")
            .prefetch_related(
                Prefetch(
                    "deposits",
                    queryset=deposit_model.objects.filter(deposit_date__year=year),
                )
            )
            .order_by("name")
        )
        for account in accounts:
            if account.currency != currency:
                continue
            amount = sum(
                (
                    deposit.amount.amount
                    for deposit in account.deposits.all()
                    if str(deposit.amount.currency) == currency
                ),
                Decimal(0),
            )
            if first <= account.opening_date <= last:
                amount += account.opening_amount.amount
            amount *= perspective.asset_ratio(resolver.rows(account))
            if amount:
                flows.append(AccountFlows(account=account, amount=amount))
    return flows
