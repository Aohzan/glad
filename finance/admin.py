"""Admin conf for Finance."""

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin import helpers
from django.utils.translation import gettext_lazy as _

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
    SavingAccountDeposit,
    SavingAccountType,
    SavingAccountValue,
)

admin.site.register(SavingAccountType)
admin.site.register(InvestmentAccountType)


class InvestmentAccountHoldingInline(admin.TabularInline):
    """Inline for InvestmentAccountHolding in the admin interface."""

    model = InvestmentAccountHolding
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class InvestmentAccountDepositInline(admin.TabularInline):
    """Inline for InvestmentAccountDeposit in the admin interface."""

    model = InvestmentAccountDeposit
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "deposit_date",
        "amount",
        "source",
        "update_account_cash",
        "created_at",
        "updated_at",
    )


class InvestmentAccountCashInline(admin.TabularInline):
    """Inline for InvestmentAccountCash in the admin interface."""

    model = InvestmentAccountCash
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(InvestmentAccount)
class InvestmentAccountAdmin(admin.ModelAdmin):
    """Admin interface for InvestmentAccount."""

    inlines = [
        InvestmentAccountHoldingInline,
        InvestmentAccountDepositInline,
        InvestmentAccountCashInline,
    ]


class InvestmentAccountHoldingHistoryInline(admin.TabularInline):
    """Inline for InvestmentAccountHoldingHistory in the admin interface."""

    model = InvestmentAccountHoldingHistory
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "valuation_date",
        "value",
        "quantity",
        "cash_used",
        "created_at",
        "updated_at",
    )


@admin.register(InvestmentAccountHolding)
class InvestmentAccountHoldingAdmin(admin.ModelAdmin):
    """Admin interface for InvestmentAccountHolding."""

    inlines = [
        InvestmentAccountHoldingHistoryInline,
    ]


class SavingAccountValueInline(admin.TabularInline):
    """Inline for SavingAccountValue in the admin interface."""

    model = SavingAccountValue
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class SavingAccountDepositInline(admin.TabularInline):
    """Inline for SavingAccountDeposit in the admin interface."""

    model = SavingAccountDeposit
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "deposit_date",
        "amount",
        "source",
        "update_account_value",
        "created_at",
        "updated_at",
    )


@admin.register(SavingAccount)
class SavingAccountAdmin(admin.ModelAdmin):
    """Admin interface for SavingAccount."""

    inlines = [
        SavingAccountValueInline,
        SavingAccountDepositInline,
    ]


@admin.register(SavingAccountDeposit)
class SavingAccountDepositAdmin(admin.ModelAdmin):
    """Admin interface for SavingAccountDeposit."""

    list_display = ("account", "amount", "deposit_date", "update_account_value")
    list_filter = ("deposit_date", "update_account_value", "account")
    fields = ("account", "amount", "deposit_date", "source", "update_account_value")


@admin.register(InvestmentAccountDeposit)
class InvestmentAccountDepositAdmin(admin.ModelAdmin):
    """Admin interface for InvestmentAccountDeposit."""

    list_display = ("account", "amount", "deposit_date", "update_account_cash")
    list_filter = ("deposit_date", "update_account_cash", "account")
    fields = ("account", "amount", "deposit_date", "source", "update_account_cash")


@admin.register(InvestmentAccountHoldingHistory)
class InvestmentAccountHoldingHistoryAdmin(admin.ModelAdmin):
    """Admin interface for InvestmentAccountHoldingHistory."""

    list_display = (
        "holding",
        "value",
        "quantity",
        "valuation_date",
        "cash_used",
    )
    list_filter = ("valuation_date", "holding__account")
    fields = ("holding", "value", "quantity", "valuation_date", "cash_used")
    actions = ["bulk_update_valuation_date"]

    @admin.action(description=_("Bulk update valuation date"))
    def bulk_update_valuation_date(self, request, queryset):
        """Bulk update valuation date for selected items."""
        if "apply" in request.POST:
            new_date = request.POST.get("new_valuation_date")
            if new_date:
                count = queryset.update(valuation_date=new_date)
                messages.success(
                    request,
                    _("Successfully updated valuation date for %(count)d items.")
                    % {"count": count},
                )
                return None

        # Show intermediate page with date input
        from django.shortcuts import render
        from django.utils import timezone

        return render(
            request,
            "admin/bulk_update_date.html",
            {
                "queryset": queryset,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                "opts": self.model._meta,
                "action_name": "bulk_update_valuation_date",
                "title": _("Bulk update valuation date"),
                "date_field_name": "new_valuation_date",
                "date_field_label": _("New valuation date"),
                "now": timezone.now(),
            },
        )


@admin.register(SavingAccountValue)
class SavingAccountValueAdmin(admin.ModelAdmin):
    """Admin interface for SavingAccountValue."""

    list_display = (
        "account",
        "value",
        "value_date",
    )
    list_filter = ("value_date", "account")
    ordering = ("-value_date", "account")
    fields = ("account", "value", "value_date")
    actions = ["bulk_update_value_date"]

    @admin.action(description=_("Bulk update value date"))
    def bulk_update_value_date(self, request, queryset):
        """Bulk update value date for selected items."""
        if "apply" in request.POST:
            new_date = request.POST.get("new_value_date")
            if new_date:
                count = queryset.update(value_date=new_date)
                messages.success(
                    request,
                    _("Successfully updated value date for %(count)d items.")
                    % {"count": count},
                )
                return None

        # Show intermediate page with date input
        from django.shortcuts import render
        from django.utils import timezone

        return render(
            request,
            "admin/bulk_update_date.html",
            {
                "queryset": queryset,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                "opts": self.model._meta,
                "action_name": "bulk_update_value_date",
                "title": _("Bulk update value date"),
                "date_field_name": "new_value_date",
                "date_field_label": _("New value date"),
                "now": timezone.now(),
            },
        )
