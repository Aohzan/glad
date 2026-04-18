"""Admin interface for managing properties."""

from django.contrib import admin

from property.models import (
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyLoanSchedule,
    PropertyValue,
)


class PropertyValueInline(admin.TabularInline):
    model = PropertyValue
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class PropertyLedgerEntryInline(admin.TabularInline):
    model = PropertyLedgerEntry
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "flow_type",
        "amount",
        "entry_date",
        "management_category",
        "description",
    )


class PropertyLoanScheduleInline(admin.TabularInline):
    model = PropertyLoanSchedule
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = ("order", "count", "amount", "created_at", "updated_at")
    ordering = ("order",)


class PropertyLoanInline(admin.TabularInline):
    model = PropertyLoan
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class LeaseInline(admin.TabularInline):
    model = Lease
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "lease_type",
        "status",
        "start_date",
        "end_date",
        "rent_amount",
        "charges_amount",
    )


class ManagementMandateInline(admin.TabularInline):
    model = ManagementMandate
    extra = 0
    readonly_fields = ("is_active", "created_at", "updated_at")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    inlines = [
        PropertyValueInline,
        PropertyLedgerEntryInline,
        PropertyLoanInline,
        LeaseInline,
        ManagementMandateInline,
    ]
    list_display = (
        "name",
        "property_type",
        "is_furnished",
        "gross_value",
        "net_value",
        "is_active",
    )
    list_filter = ("property_type", "is_active", "is_furnished")
    search_fields = ("name", "address")


@admin.register(PropertyLoan)
class PropertyLoanAdmin(admin.ModelAdmin):
    inlines = [PropertyLoanScheduleInline]
    list_display = (
        "property",
        "name",
        "start_date",
        "end_date",
        "original_amount",
        "monthly_payment",
        "remaining_balance",
        "is_smoothed",
    )
    list_filter = ("property", "start_date")
    search_fields = ("property__name", "name")
    readonly_fields = (
        "remaining_balance",
        "amount_paid",
        "is_smoothed",
        "created_at",
        "updated_at",
    )


@admin.register(PropertyLoanSchedule)
class PropertyLoanScheduleAdmin(admin.ModelAdmin):
    list_display = ("loan", "order", "count", "amount")
    list_filter = ("loan__property",)
    search_fields = ("loan__name", "loan__property__name")
    ordering = ("loan", "order")


@admin.register(PropertyLedgerEntry)
class PropertyLedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "flow_type",
        "amount",
        "entry_date",
        "management_category",
        "description",
    )
    list_filter = (
        "flow_type",
        "management_category",
        "recurrence_type",
    )
    search_fields = ("property__name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "lease_type",
        "status",
        "start_date",
        "end_date",
        "rent_amount",
    )
    list_filter = ("status", "lease_type", "periodicity")
    search_fields = ("property__name", "tenant_first_name", "tenant_last_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ManagementMandate)
class ManagementMandateAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "manager_name",
        "start_date",
        "end_date",
        "fee_type",
        "is_active",
    )
    list_filter = ("fee_type",)
    search_fields = ("property__name", "manager_name")
    readonly_fields = ("is_active", "created_at", "updated_at")
