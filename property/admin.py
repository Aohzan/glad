"""Admin interface for managing properties."""

from django.contrib import admin

from property.models import (
    Lease,
    LeaseTenant,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyManager,
    PropertyValue,
    Tenant,
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
        "tax_category",
        "management_category",
        "description",
    )


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


@admin.register(PropertyLedgerEntry)
class PropertyLedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "flow_type",
        "amount",
        "entry_date",
        "tax_category",
        "management_category",
        "description",
    )
    list_filter = (
        "flow_type",
        "tax_category",
        "management_category",
        "recurrence_type",
    )
    search_fields = ("property__name", "description")
    readonly_fields = ("created_at", "updated_at")


class LeaseTenantInline(admin.TabularInline):
    model = LeaseTenant
    extra = 0


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email", "phone")
    search_fields = ("last_name", "first_name", "email")


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    inlines = [LeaseTenantInline]
    list_display = (
        "property",
        "lease_type",
        "status",
        "start_date",
        "end_date",
        "rent_amount",
    )
    list_filter = ("status", "lease_type", "periodicity")
    search_fields = ("property__name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(PropertyManager)
class PropertyManagerAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "siret")
    search_fields = ("name", "siret")


@admin.register(ManagementMandate)
class ManagementMandateAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "manager",
        "start_date",
        "end_date",
        "fee_type",
        "is_active",
    )
    list_filter = ("fee_type",)
    search_fields = ("property__name", "manager__name")
    readonly_fields = ("is_active", "created_at", "updated_at")
