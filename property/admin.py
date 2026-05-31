"""Admin interface for managing properties."""

from django.contrib import admin

from property.models import (
    SCPI,
    AmortizationAsset,
    AmortizationSetup,
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyLoanAmortizationEntry,
    PropertyValue,
    SCPIDividend,
    SCPIInvestment,
    SCPISharePrice,
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


class PropertyLoanAmortizationEntryInline(admin.TabularInline):
    model = PropertyLoanAmortizationEntry
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "date",
        "capital",
        "interest",
        "remaining_balance_amount",
        "created_at",
        "updated_at",
    )
    ordering = ("date",)
    can_delete = True


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


class AmortizationAssetInline(admin.TabularInline):
    model = AmortizationAsset
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "label",
        "beginning_date",
        "value_total",
        "duration_years",
        "is_initial_component",
    )


class AmortizationSetupInline(admin.StackedInline):
    model = AmortizationSetup
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = ("total_value", "land_percentage", "created_at", "updated_at")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    inlines = [
        PropertyValueInline,
        PropertyLedgerEntryInline,
        PropertyLoanInline,
        LeaseInline,
        ManagementMandateInline,
        AmortizationSetupInline,
        AmortizationAssetInline,
    ]
    list_display = (
        "name",
        "property_type",
        "tax_regime",
        "gross_value",
        "net_value",
        "is_active",
    )
    list_filter = ("property_type", "is_active", "tax_regime")
    search_fields = ("name", "address")


@admin.register(PropertyLoan)
class PropertyLoanAdmin(admin.ModelAdmin):
    inlines = [PropertyLoanAmortizationEntryInline]
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
    readonly_fields = (
        "remaining_balance",
        "amount_paid",
        "created_at",
        "updated_at",
    )


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


@admin.register(AmortizationAsset)
class AmortizationAssetAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "label",
        "beginning_date",
        "value_total",
        "duration_years",
        "is_initial_component",
    )
    list_filter = ("property", "is_initial_component")
    search_fields = ("property__name", "label")


@admin.register(AmortizationSetup)
class AmortizationSetupAdmin(admin.ModelAdmin):
    list_display = ("property", "total_value", "land_percentage")
    search_fields = ("property__name",)


# ── SCPI ──────────────────────────────────────────────────────────────────────


class SCPISharePriceInline(admin.TabularInline):
    model = SCPISharePrice
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = ("date", "subscription_value", "withdrawal_value")
    ordering = ("-date",)


class SCPIInvestmentInline(admin.TabularInline):
    model = SCPIInvestment
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "subscription_date",
        "shares_count",
        "unit_purchase_price",
        "ownership_type",
    )


class SCPIDividendInline(admin.TabularInline):
    model = SCPIDividend
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = ("payment_date", "gross_amount", "net_amount", "notes")
    ordering = ("-payment_date",)


@admin.register(SCPI)
class SCPIAdmin(admin.ModelAdmin):
    inlines = [SCPISharePriceInline, SCPIInvestmentInline, SCPIDividendInline]
    list_display = (
        "name",
        "management_company",
        "current_subscription_value",
        "current_withdrawal_value",
        "entry_fee_rate",
        "exit_fee_rate",
    )
    search_fields = ("name", "management_company")
    readonly_fields = ("current_subscription_value", "current_withdrawal_value")


class SCPIDividendInlineForInvestment(admin.TabularInline):
    model = SCPIDividend
    fk_name = "scpi"
    extra = 0


@admin.register(SCPIInvestment)
class SCPIInvestmentAdmin(admin.ModelAdmin):
    list_display = (
        "scpi",
        "subscription_date",
        "shares_count",
        "unit_purchase_price",
        "ownership_type",
    )
    list_filter = ("scpi", "ownership_type")
    search_fields = ("scpi__name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(SCPIDividend)
class SCPIDividendAdmin(admin.ModelAdmin):
    list_display = (
        "scpi",
        "payment_date",
        "gross_amount",
        "net_amount",
    )
    list_filter = ("scpi",)
    search_fields = ("scpi__name",)
    readonly_fields = ("created_at", "updated_at")
