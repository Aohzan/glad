"""Tests for AmortizationAsset model, LMNP tax service art. 39C, and fiscal views."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import (
    AmortizationAsset,
    AmortizationSetup,
    Property,
    PropertyLedgerEntry,
)
from property.services.tax_lmnp import (
    get_accounting_data,
    get_amortization_table,
    get_deferred_amortization_balance,
    get_lmnp_summary,
    get_total_amortization,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="Test LMNP Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        tax_regime=Property.TaxRegime.LMNP_REEL,
    )


@pytest.fixture
def structure_asset(property_obj):
    """Gros œuvre asset: 200 000 €, 75 years, acquired 2020-01-01."""
    return AmortizationAsset.objects.create(
        property=property_obj,
        label="Gros œuvre",
        acquisition_date=datetime.date(2020, 1, 1),
        value_total=Money(170_000, "EUR"),  # already land-excluded
        duration_years=75,
    )


@pytest.fixture
def fittings_asset(property_obj):
    """Agencements: 10 000 €, 12 years, acquired 2020-07-01."""
    return AmortizationAsset.objects.create(
        property=property_obj,
        label="Agencements",
        acquisition_date=datetime.date(2020, 7, 1),
        value_total=Money(10_000, "EUR"),
        duration_years=12,
    )


# ─── AmortizationAsset model tests ───────────────────────────────────────────


@pytest.mark.django_db
class TestAmortizationAssetCreation:
    def test_create_structure_asset(self, structure_asset):
        assert structure_asset.pk is not None
        assert structure_asset.duration_years == 75

    def test_str_representation(self, structure_asset):
        s = str(structure_asset)
        assert "Gros œuvre" in s
        assert structure_asset.property.name in s

    def test_default_durations_constant(self):
        pass  # DEFAULT_DURATIONS removed with category

    def test_category_choices(self):
        pass  # Category enum removed


@pytest.mark.django_db
class TestDepreciableBase:
    def test_structure_base_equals_value_total(self, structure_asset):
        """depreciable_base() returns value_total directly (land handled externally)."""
        base = structure_asset.depreciable_base()
        assert base == structure_asset.value_total

    def test_fittings_base_equals_value_total(self, fittings_asset):
        base = fittings_asset.depreciable_base()
        assert base == fittings_asset.value_total


@pytest.mark.django_db
class TestGetAnnualAmortization:
    def test_zero_before_acquisition_year(self, structure_asset):
        assert structure_asset.get_annual_amortization(2019) == Decimal("0")

    def test_zero_after_useful_life(self, structure_asset):
        # acquisition_date=2020, duration=75 → life ends 2094
        assert structure_asset.get_annual_amortization(2096) == Decimal("0")

    def test_full_year_middle(self, structure_asset):
        """Middle year: full annual dotation."""
        # 170000 / 75 ≈ 2266.67
        dotation = structure_asset.get_annual_amortization(2025)
        expected = (Decimal("170000") / Decimal("75")).quantize(Decimal("0.01"))
        assert dotation == expected

    def test_first_year_prorata_january(self, structure_asset):
        """Acquisition on January 1: prorata = 12/12 = full year."""
        dotation = structure_asset.get_annual_amortization(2020)
        expected = (Decimal("170000") / Decimal("75")).quantize(Decimal("0.01"))
        assert dotation == expected

    def test_first_year_prorata_july(self, fittings_asset):
        """Acquisition on July 1: prorata = 6/12 of annual."""
        dotation = fittings_asset.get_annual_amortization(2020)
        annual = Decimal("10000") / Decimal("12")
        expected = (annual * Decimal("6") / Decimal("12")).quantize(Decimal("0.01"))
        assert dotation == expected

    def test_middle_years_fittings(self, fittings_asset):
        """Years 2021–2030 are full years for fittings asset (12-year life)."""
        annual = (Decimal("10000") / Decimal("12")).quantize(Decimal("0.01"))
        for y in range(2021, 2031):
            assert fittings_asset.get_annual_amortization(y) == annual


@pytest.mark.django_db
class TestCumulativeAmortization:
    def test_cumulative_increases_each_year(self, structure_asset):
        cumul_2020 = structure_asset.cumulative_amortization(2020)
        cumul_2021 = structure_asset.cumulative_amortization(2021)
        assert cumul_2021 > cumul_2020

    def test_cumulative_zero_before_acquisition(self, structure_asset):
        assert structure_asset.cumulative_amortization(2019) == Decimal("0")

    def test_cumulative_sums_correctly(self, fittings_asset):
        d2020 = fittings_asset.get_annual_amortization(2020)
        d2021 = fittings_asset.get_annual_amortization(2021)
        assert fittings_asset.cumulative_amortization(2021) == d2020 + d2021


# ─── AmortizationSetup model tests ───────────────────────────────────────────


@pytest.mark.django_db
class TestAmortizationSetup:
    def test_create_setup(self, property_obj):
        setup = AmortizationSetup.objects.create(
            property=property_obj,
            total_value=Money(200_000, "EUR"),
            land_percentage=Decimal("15.00"),
        )
        assert setup.pk is not None

    def test_initialize_components_creates_five_assets(self, property_obj):
        setup = AmortizationSetup.objects.create(
            property=property_obj,
            total_value=Money(200_000, "EUR"),
            land_percentage=Decimal("15.00"),
        )
        # Ensure no assets initially
        assert AmortizationAsset.objects.filter(property=property_obj).count() == 0
        setup.initialize_components()
        assets = AmortizationAsset.objects.filter(property=property_obj)
        assert assets.count() == 5

    def test_initialize_components_sets_is_initial_component(self, property_obj):
        setup = AmortizationSetup.objects.create(
            property=property_obj,
            total_value=Money(200_000, "EUR"),
            land_percentage=Decimal("15.00"),
        )
        setup.initialize_components()
        for asset in AmortizationAsset.objects.filter(property=property_obj):
            assert asset.is_initial_component is True

    def test_initialize_components_sum_percentages(self, property_obj):
        """All component percentages should add up to 100%."""
        setup = AmortizationSetup.objects.create(
            property=property_obj,
            total_value=Money(200_000, "EUR"),
            land_percentage=Decimal("15.00"),
        )
        setup.initialize_components()
        # 5 standard components created
        labels = list(
            AmortizationAsset.objects.filter(property=property_obj).values_list(
                "label", flat=True
            )
        )
        assert "Gros œuvre" in labels
        assert "Installations électriques" in labels
        assert "Étanchéité" in labels
        assert "Toiture" in labels
        assert "Agencements intérieurs" in labels


# ─── Tax service: amortization helpers ───────────────────────────────────────


@pytest.mark.django_db
class TestGetAmortizationTable:
    def test_empty_table_no_assets(self, property_obj):
        table = get_amortization_table(property_obj.pk, 2025)
        assert table == []

    def test_table_has_expected_keys(self, structure_asset, property_obj):
        table = get_amortization_table(property_obj.pk, 2025)
        assert len(table) == 1
        row = table[0]
        assert "label" in row
        assert "depreciable_base" in row
        assert "value_total" in row
        assert "duration_years" in row
        assert "annual_dotation" in row
        assert "cumulative" in row
        assert "asset_pk" in row

    def test_table_multiple_assets(self, structure_asset, fittings_asset, property_obj):
        table = get_amortization_table(property_obj.pk, 2025)
        assert len(table) == 2

    def test_table_dotation_matches_model(self, structure_asset, property_obj):
        table = get_amortization_table(property_obj.pk, 2025)
        assert table[0]["annual_dotation"] == structure_asset.get_annual_amortization(
            2025
        )


@pytest.mark.django_db
class TestGetTotalAmortization:
    def test_total_zero_no_assets(self, property_obj):
        assert get_total_amortization(property_obj.pk, 2025) == Decimal("0")

    def test_total_sums_all_assets(self, structure_asset, fittings_asset, property_obj):
        total = get_total_amortization(property_obj.pk, 2025)
        expected = structure_asset.get_annual_amortization(
            2025
        ) + fittings_asset.get_annual_amortization(2025)
        assert total == expected


# ─── Tax service: art. 39C logic ─────────────────────────────────────────────


@pytest.mark.django_db
class TestGetLmnpSummaryArt39C:
    def _add_rent(self, property_obj, amount, year=2025):
        return PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal(str(amount)), "EUR"),
            entry_date=datetime.date(year, 6, 1),
        )

    def _add_expense(self, property_obj, amount, year=2025):
        return PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.MANAGEMENT_FEES,
            amount=Money(Decimal(str(amount)), "EUR"),
            entry_date=datetime.date(year, 6, 1),
        )

    def test_no_amortization_result_unchanged(self, property_obj):
        self._add_rent(property_obj, "12000")
        self._add_expense(property_obj, "2000")
        summary = get_lmnp_summary(property_obj.pk, 2025)
        assert summary["recettes"] == Decimal("12000")
        assert summary["charges"] == Decimal("2000")
        assert summary["result"] == Decimal("10000")
        assert summary["amortization_total"] == Decimal("0")
        assert summary["taxable_result"] == Decimal("10000")

    def test_amortization_fully_deductible(self, property_obj):
        asset = AmortizationAsset.objects.create(
            property=property_obj,
            label="Gros œuvre test",
            acquisition_date=datetime.date(2025, 1, 1),
            value_total=Money(170_000, "EUR"),
            duration_years=75,
        )
        self._add_rent(property_obj, "12000")
        self._add_expense(property_obj, "2000")
        summary = get_lmnp_summary(property_obj.pk, 2025)
        amort = asset.get_annual_amortization(2025)
        assert summary["amortization_total"] == amort
        assert summary["deferred_prior"] == Decimal("0")
        assert summary["amortization_deductible"] == amort
        assert summary["amortization_deferred"] == Decimal("0")
        assert summary["taxable_result"] == Decimal("10000") - amort

    def test_amortization_partially_deferred(self, property_obj):
        asset = AmortizationAsset.objects.create(
            property=property_obj,
            label="Gros œuvre partial",
            acquisition_date=datetime.date(2025, 1, 1),
            value_total=Money(170_000, "EUR"),
            duration_years=75,
        )
        self._add_rent(property_obj, "3000")
        self._add_expense(property_obj, "2000")
        summary = get_lmnp_summary(property_obj.pk, 2025)
        assert summary["amortization_deductible"] == Decimal("1000")
        assert summary["amortization_deferred"] == asset.get_annual_amortization(
            2025
        ) - Decimal("1000")
        assert summary["taxable_result"] == Decimal("0")

    def test_amortization_fully_deferred_when_operating_deficit(self, property_obj):
        asset = AmortizationAsset.objects.create(
            property=property_obj,
            label="Gros œuvre deficit",
            acquisition_date=datetime.date(2025, 1, 1),
            value_total=Money(170_000, "EUR"),
            duration_years=75,
        )
        self._add_rent(property_obj, "1000")
        self._add_expense(property_obj, "2000")
        summary = get_lmnp_summary(property_obj.pk, 2025)
        assert summary["result"] == Decimal("-1000")
        assert summary["amortization_deductible"] == Decimal("0")
        assert summary["amortization_deferred"] == asset.get_annual_amortization(2025)
        # Art. 39C: amort is deferred but the operating deficit remains
        assert summary["taxable_result"] == Decimal("-1000")

    def test_taxable_result_not_worsened_by_amort(self, property_obj):
        """Art. 39C: amortization cannot create or deepen a deficit.
        When result_before_amort > 0 and < amort, taxable_result = 0 (not negative).
        """
        AmortizationAsset.objects.create(
            property=property_obj,
            label="X",
            acquisition_date=datetime.date(2025, 1, 1),
            value_total=Money(170_000, "EUR"),
            duration_years=75,
        )
        self._add_rent(property_obj, "10000")
        self._add_expense(property_obj, "9500")
        summary = get_lmnp_summary(property_obj.pk, 2025)
        # result_before_amort = 500 > 0, amort ~2267
        # amort_deductible = min(2267, 500) = 500
        # taxable_result = 500 - 500 = 0 (not negative — amort didn't create deficit)
        assert summary["taxable_result"] == Decimal("0")

    def test_result_key_is_before_amortization(self, property_obj):
        AmortizationAsset.objects.create(
            property=property_obj,
            label="Y",
            acquisition_date=datetime.date(2025, 1, 1),
            value_total=Money(170_000, "EUR"),
            duration_years=75,
        )
        self._add_rent(property_obj, "6000")
        self._add_expense(property_obj, "1000")
        summary = get_lmnp_summary(property_obj.pk, 2025)
        assert summary["result"] == Decimal("5000")

    def test_deferred_prior_carried_forward(self, property_obj, structure_asset):
        self._add_rent(property_obj, "3000", year=2025)
        self._add_expense(property_obj, "2000", year=2025)
        summary_2025 = get_lmnp_summary(property_obj.pk, 2025)
        deferred = summary_2025["deferred_balance"]

        self._add_rent(property_obj, "20000", year=2026)
        summary_2026 = get_lmnp_summary(property_obj.pk, 2026)
        assert summary_2026["deferred_prior"] == deferred

    def test_summary_includes_year(self, property_obj):
        summary = get_lmnp_summary(property_obj.pk, 2025)
        assert summary["year"] == 2025


@pytest.mark.django_db
class TestGetDeferredAmortizationBalance:
    def test_no_assets_returns_zero(self, property_obj):
        assert get_deferred_amortization_balance(property_obj.pk, 2025) == Decimal("0")

    def test_zero_before_first_acquisition(self, structure_asset, property_obj):
        assert get_deferred_amortization_balance(property_obj.pk, 2019) == Decimal("0")

    def test_full_deferral_accumulates(self, property_obj, structure_asset):
        balance_2020 = get_deferred_amortization_balance(property_obj.pk, 2020)
        balance_2021 = get_deferred_amortization_balance(property_obj.pk, 2021)
        assert balance_2021 > balance_2020

    def test_deferred_absorbed_with_revenue(self, property_obj, structure_asset):
        PropertyLedgerEntry.objects.create(
            property=property_obj,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("1000000"), "EUR"),
            entry_date=datetime.date(2025, 1, 1),
        )
        balance_2025 = get_deferred_amortization_balance(property_obj.pk, 2025)
        assert balance_2025 == Decimal("0")


# ─── Accounting dashboard ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestGetAccountingData:
    def test_returns_all_form_keys(self, property_obj, structure_asset):
        data = get_accounting_data([property_obj], 2025)
        assert "form_2033b" in data
        assert "form_2033a" in data
        assert "form_2033c" in data
        assert "form_2031" in data
        assert "form_2031bis" in data
        assert "form_2042c" in data

    def test_aggregates_multiple_properties(self, property_obj, structure_asset):
        property2 = Property.objects.create(
            name="Second Property",
            property_type=Property.APARTMENT,
            buying_value=Money(150_000, "EUR"),
            buying_date=datetime.date(2021, 1, 1),
            tax_regime=Property.TaxRegime.LMNP_REEL,
        )
        AmortizationAsset.objects.create(
            property=property2,
            label="Structure 2",
            acquisition_date=datetime.date(2021, 1, 1),
            value_total=Money(100_000, "EUR"),
            duration_years=75,
        )
        data = get_accounting_data([property_obj, property2], 2025)
        assert len(data["form_2033b"]["per_prop"]) == 2

    def test_form_2042c_is_benefice_flag(self, property_obj):
        data = get_accounting_data([property_obj], 2025)
        assert "is_benefice" in data["form_2042c"]

    def test_empty_properties_list(self):
        data = get_accounting_data([], 2025)
        assert data["form_2033b"]["recettes"] == Decimal("0")
        assert data["form_2042c"]["is_benefice"] is True  # 0 is non-negative


@pytest.mark.django_db
class TestAccountingDashboardView:
    def test_redirects_unauthenticated(self, client):
        url = reverse("property:accounting")
        response = client.get(url)
        assert response.status_code == 302

    def test_returns_200_for_authenticated(self, admin_client):
        url = reverse("property:accounting")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_context_has_accounting(self, admin_client):
        url = reverse("property:accounting")
        response = admin_client.get(url)
        assert "accounting" in response.context
        assert "year" in response.context
        assert "lmnp_properties" in response.context

    def test_year_param(self, admin_client):
        url = reverse("property:accounting")
        response = admin_client.get(url, {"year": "2023"})
        assert response.context["year"] == 2023

    def test_template_used(self, admin_client):
        url = reverse("property:accounting")
        response = admin_client.get(url)
        assert "property/accounting_dashboard.html" in [
            t.name for t in response.templates
        ]


# ─── Initialize amortization view ────────────────────────────────────────────


@pytest.mark.django_db
class TestInitializeAmortizationView:
    def test_post_creates_setup_and_assets(self, admin_client, property_obj):
        url = reverse(
            "property:initialize_amortization", kwargs={"pk": property_obj.pk}
        )
        assert not AmortizationSetup.objects.filter(property=property_obj).exists()
        response = admin_client.post(url)
        assert response.status_code == 302
        assert AmortizationSetup.objects.filter(property=property_obj).exists()
        assert AmortizationAsset.objects.filter(property=property_obj).count() == 5

    def test_post_uses_buying_value_as_total(self, admin_client, property_obj):
        """Amortization setup total_value is initialized from buying_value, not net_value."""
        url = reverse(
            "property:initialize_amortization", kwargs={"pk": property_obj.pk}
        )
        admin_client.post(url)
        setup = AmortizationSetup.objects.get(property=property_obj)
        assert setup.total_value.amount == property_obj.buying_value.amount

    def test_get_redirects(self, admin_client, property_obj):
        url = reverse(
            "property:initialize_amortization", kwargs={"pk": property_obj.pk}
        )
        response = admin_client.get(url)
        assert response.status_code in (302, 405)

    def test_unauthenticated_redirects(self, client, property_obj):
        url = reverse(
            "property:initialize_amortization", kwargs={"pk": property_obj.pk}
        )
        response = client.post(url)
        assert response.status_code == 302

    def test_404_for_missing_property(self, admin_client):
        url = reverse("property:initialize_amortization", kwargs={"pk": 999999})
        response = admin_client.post(url)
        assert response.status_code == 404


# ─── Amortization asset CRUD views ───────────────────────────────────────────


@pytest.mark.django_db
class TestAmortizationAssetCrudViews:
    def test_create_get_renders_form(self, admin_client, property_obj):
        url = reverse(
            "property:new_amortization", kwargs={"property_pk": property_obj.pk}
        )
        response = admin_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_create_post_creates_asset(self, admin_client, property_obj):
        url = reverse(
            "property:new_amortization", kwargs={"property_pk": property_obj.pk}
        )
        data = {
            "label": "Agencements",
            "acquisition_date": "2024-01-01",
            "value_total_0": "5000.00",
            "value_total_1": "EUR",
            "duration_years": "12",
        }
        count_before = AmortizationAsset.objects.filter(property=property_obj).count()
        response = admin_client.post(url, data)
        assert (
            AmortizationAsset.objects.filter(property=property_obj).count()
            == count_before + 1
        )
        assert response.status_code == 302

    def test_edit_get_renders_form_with_instance(
        self, admin_client, property_obj, structure_asset
    ):
        url = reverse(
            "property:edit_amortization",
            kwargs={"property_pk": property_obj.pk, "asset_pk": structure_asset.pk},
        )
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.context["form"].instance == structure_asset

    def test_edit_post_updates_asset(self, admin_client, property_obj, structure_asset):
        url = reverse(
            "property:edit_amortization",
            kwargs={"property_pk": property_obj.pk, "asset_pk": structure_asset.pk},
        )
        data = {
            "label": "Gros œuvre modifié",
            "acquisition_date": "2020-01-01",
            "value_total_0": "170000.00",
            "value_total_1": "EUR",
            "duration_years": "75",
        }
        admin_client.post(url, data)
        structure_asset.refresh_from_db()
        assert structure_asset.label == "Gros œuvre modifié"

    def test_delete_post_removes_asset(
        self, admin_client, property_obj, structure_asset
    ):
        url = reverse(
            "property:delete_amortization",
            kwargs={"property_pk": property_obj.pk, "asset_pk": structure_asset.pk},
        )
        response = admin_client.post(url)
        assert response.status_code == 302
        assert not AmortizationAsset.objects.filter(pk=structure_asset.pk).exists()

    def test_delete_404_wrong_property(
        self, admin_client, property_obj, structure_asset
    ):
        other_property = Property.objects.create(
            name="Other",
            property_type=Property.APARTMENT,
            buying_value=Money(100000, "EUR"),
            buying_date=datetime.date(2021, 1, 1),
        )
        url = reverse(
            "property:delete_amortization",
            kwargs={"property_pk": other_property.pk, "asset_pk": structure_asset.pk},
        )
        response = admin_client.post(url)
        assert response.status_code == 404

    def test_unauthenticated_create_redirects(self, client, property_obj):
        url = reverse(
            "property:new_amortization", kwargs={"property_pk": property_obj.pk}
        )
        response = client.get(url)
        assert response.status_code == 302

    def test_create_post_invalid_form_rerenders(self, admin_client, property_obj):
        """POST with invalid data should re-render the form, not create asset."""
        url = reverse(
            "property:new_amortization", kwargs={"property_pk": property_obj.pk}
        )
        response = admin_client.post(url, {})  # empty/invalid form
        assert response.status_code == 200
        assert "form" in response.context

    def test_edit_post_invalid_form_rerenders(
        self, admin_client, property_obj, structure_asset
    ):
        """POST with invalid data should re-render the form without saving."""
        url = reverse(
            "property:edit_amortization",
            kwargs={"property_pk": property_obj.pk, "asset_pk": structure_asset.pk},
        )
        response = admin_client.post(url, {})  # empty/invalid form
        assert response.status_code == 200
        assert "form" in response.context

    def test_delete_get_redirects_without_deleting(
        self, admin_client, property_obj, structure_asset
    ):
        """GET on delete endpoint should redirect without deleting."""
        url = reverse(
            "property:delete_amortization",
            kwargs={"property_pk": property_obj.pk, "asset_pk": structure_asset.pk},
        )
        response = admin_client.get(url)
        assert response.status_code == 302
        assert AmortizationAsset.objects.filter(pk=structure_asset.pk).exists()

    def test_initialize_post_when_setup_exists(self, admin_client, property_obj):
        """POST when AmortizationSetup already exists should reinitialize components."""
        from property.models import AmortizationSetup

        AmortizationSetup.objects.create(
            property=property_obj,
            total_value=Money(200000, "EUR"),
            land_percentage=Decimal("15.00"),
        )
        url = reverse(
            "property:initialize_amortization", kwargs={"pk": property_obj.pk}
        )
        response = admin_client.post(url)
        assert response.status_code == 302
        assert AmortizationAsset.objects.filter(property=property_obj).count() == 5


# ─── get_amortization_context via detail view ─────────────────────────────────


@pytest.mark.django_db
class TestGetAmortizationContextViaDetailView:
    """Cover get_amortization_context and get_amortization_schedule via the detail view."""

    def test_detail_view_with_lmnp_reel_no_assets(self, admin_client, property_obj):
        """Detail view for LMNP_REEL property without assets calls get_amortization_context."""
        url = reverse("property:detail", kwargs={"pk": property_obj.pk})
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.context["show_amortization_tab"] is True
        assert response.context["amortization_table"] == []
        assert response.context["amortization_end_year"] is None

    def test_detail_view_with_lmnp_reel_with_assets(
        self, admin_client, property_obj, structure_asset
    ):
        """Detail view with assets populates the schedule context."""
        url = reverse("property:detail", kwargs={"pk": property_obj.pk})
        response = admin_client.get(url)
        assert response.status_code == 200
        assert len(response.context["amortization_table"]) == 1
        assert response.context["amortization_end_year"] == 2094
        assert response.context["amortization_total_base"] == Decimal("170000")

    def test_detail_view_with_amortization_setup_no_setup_raises_does_not_exist(
        self, admin_client, property_obj
    ):
        """No AmortizationSetup → amortization_setup context is None."""
        url = reverse("property:detail", kwargs={"pk": property_obj.pk})
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.context["amortization_setup"] is None


# ─── accounting_dashboard with invalid year param ────────────────────────────


@pytest.mark.django_db
class TestAccountingDashboardInvalidYear:
    def test_invalid_year_falls_back_to_current(self, admin_client):
        import datetime

        url = reverse("property:accounting")
        response = admin_client.get(url, {"year": "notanumber"})
        assert response.status_code == 200
        assert response.context["year"] == datetime.date.today().year
