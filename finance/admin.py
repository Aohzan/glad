"""Admin conf for Finance."""

from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
    InvestmentAccountType,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountBalance,
    SavingAccountDeposit,
    SavingAccountType,
)

admin.site.register(SavingAccount)
admin.site.register(SavingAccountType)
admin.site.register(SavingAccountBalance)
admin.site.register(SavingAccountDeposit)
admin.site.register(InvestmentAccount)
admin.site.register(InvestmentAccountType)
admin.site.register(InvestmentAccountHolding)
admin.site.register(InvestmentAccountHoldingHistory)
admin.site.register(InvestmentAccountCash)
admin.site.register(InvestmentAccountDeposit)


class SavingAccountBalanceInline(GenericTabularInline):
    """Inline for SavingAccountBalance in the admin interface."""

    model = SavingAccountBalance
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class SavingAccountDepositInline(GenericTabularInline):
    """Inline for SavingAccountDeposit in the admin interface."""

    model = SavingAccountDeposit
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class InvestmentAccountHoldingHistoryInline(admin.TabularInline):
    """Inline for InvestmentAccountHoldingHistory in the admin interface."""

    model = InvestmentAccountHoldingHistory
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class InvestmentAccountCashInline(admin.TabularInline):
    """Inline for InvestmentAccountCash in the admin interface."""

    model = InvestmentAccountCash
    extra = 0
    readonly_fields = ("created_at", "updated_at")
