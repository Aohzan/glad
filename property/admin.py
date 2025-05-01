"""Admin interface for managing properties."""

from django.contrib import admin

from property.models import (
    Property,
    PropertyExpense,
    PropertyLoan,
    PropertyRevenue,
    PropertyValue,
)


class PropertyValueInline(admin.TabularInline):
    """Inline for PropertyValue in the admin interface."""

    model = PropertyValue
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class PropertyExpenseInline(admin.TabularInline):
    """Inline for PropertyExpense in the admin interface."""

    model = PropertyExpense
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class PropertyRevenueInline(admin.TabularInline):
    """Inline for PropertyRevenue in the admin interface."""

    model = PropertyRevenue
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class PropertyLoanInline(admin.TabularInline):
    """Inline for PropertyLoan in the admin interface."""

    model = PropertyLoan
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    """Admin interface for the Property model."""

    inlines = [
        PropertyValueInline,
        PropertyExpenseInline,
        PropertyRevenueInline,
        PropertyLoanInline,
    ]
    list_display = ("name", "property_type", "gross_value", "net_value", "is_active")


@admin.register(PropertyLoan)
class PropertyLoanAdmin(admin.ModelAdmin):
    """Admin interface for the PropertyLoan model."""

    list_display = (
        "property",
        "name",
        "start_date",
        "end_date",
        "original_amount",
        "monthly_payment",
        "remaining_balance",
    )
    list_filter = ("property", "start_date")
    search_fields = ("property__name", "name")
    readonly_fields = ("remaining_balance", "amount_paid", "created_at", "updated_at")
