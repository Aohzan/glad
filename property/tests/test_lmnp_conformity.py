"""
LMNP fiscal conformity tests.

These tests reproduce, on a single property, the rules of the reference
"Suivi LMNP.xlsx" workbook (LMNP.blog simulator) and check every cerfa line.
The multi-property golden scenario copied from the workbook lives in
``test_lmnp_golden_excel.py``.

Reference fixture (year 2025):
  Property:        196 000 € bought 2025-01-01 (15 % land = 29 400 €, 85 % bâti)
  Components (default breakdown, 30/360 prorata, full year here):
    Gros œuvre      88 200 € / 70 ans → 1 260,00 €
    Étanchéité      13 720 € / 25 ans →   548,80 €
    Toiture         15 680 € / 25 ans →   627,20 €
    Agencements     37 240 € / 12 ans → 3 103,33 €
    Électricité     11 760 € / 30 ans →   392,00 €
  Dotation 2025 (254):       5 931,33 €
  Loyers (218):              2 148 €
  Charges (242):             1 766,21 €
  Taxe foncière + CFE (244):   480 €   (310 + 170, dont CFE 243 = 170)
  Intérêts (294):            4 500 €
  Total charges:             6 746,21 €

  Résultat avant amortissement:      −4 598,21 €  (2148 − 6746.21)
  Plafond 39 C = max(0, 2148 − 1766.21 − 480 − 4500) = 0 → amortissement déduit 0
  Réintégration 318 = dotation non déduite = 5 931,33 €
  Résultat comptable 310 = −4 598,21 − 5 931,33 = −10 529,54 €
  Résultat fiscal 352 = 310 + 318 = −4 598,21 €  (déficit reportable 10 ans)
  Amortissements différés fin 2025 (SUIV39C): 5 931,33 €
  2042-C PRO: 5NA = 0 ; 5NY = 4 598,21 € ; 5GJ en 2026 = 4 598,21 €
  Immobilisations brutes (2033-A): 196 000 € ; emprunts fin 2025: 191 000 €
"""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import (
    AmortizationAsset,
    AmortizationSetup,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
)
from property.services.tax_lmnp import (
    get_accounting_data,
    get_bilan_data,
    get_deferred_amortization_balance,
    get_fiscal_deficit_carryforward,
    get_fiscal_deficit_history,
    get_immobilisation_movements,
    get_lmnp_summary,
    get_total_amortization,
)

# ─── Tolerance for floating-point comparisons ─────────────────────────────────
CENT = Decimal("0.01")


def approx_equal(a: Decimal, b: Decimal, tol: Decimal = Decimal("0.02")) -> bool:
    return abs(a - b) <= tol


# ─── Reference fixture ────────────────────────────────────────────────────────


@pytest.fixture
def lmnp_property():
    """Property acquired January 2025 for 196 000 € (15% land, 85% bâti)."""
    return Property.objects.create(
        name="Bien_Immo - 1",
        property_type=Property.APARTMENT,
        buying_value=Money(196_000, "EUR"),
        buying_date=datetime.date(2025, 1, 1),
        tax_regime=Property.TaxRegime.LMNP_REEL,
        is_active=True,
    )


@pytest.fixture
def lmnp_setup(lmnp_property):
    """AmortizationSetup: 196 000 €, 15% land."""
    setup = AmortizationSetup.objects.create(
        property=lmnp_property,
        total_value=Money(196_000, "EUR"),
        land_percentage=Decimal("15.00"),
    )
    setup.initialize_components()
    return setup


@pytest.fixture
def lmnp_loan(lmnp_property):
    """Single loan: 100 000 € at 4% for ~25 years (end 2049)."""
    return PropertyLoan.objects.create(
        property=lmnp_property,
        name="Crédit immobilier",
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2049, 12, 31),
        original_amount=Money(100_000, "EUR"),
        interest_rate=Decimal("4.00"),
        insurance_rate=Decimal("0.00"),
        monthly_payment=Money(Decimal("527.83"), "EUR"),
    )


@pytest.fixture
def lmnp_entries_2025(lmnp_property):
    """Ledger entries for 2025 matching the Excel reference data."""
    # Loyers (line 218)
    PropertyLedgerEntry.objects.create(
        property=lmnp_property,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(Decimal("2148.00"), "EUR"),
        entry_date=datetime.date(2025, 12, 31),
    )
    # Charges locatives refacturées (line 218) — included in charges below
    # Charges d'exploitation (line 242) — total 1766.21
    PropertyLedgerEntry.objects.create(
        property=lmnp_property,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.COOWNERSHIP,
        amount=Money(Decimal("1766.21"), "EUR"),
        entry_date=datetime.date(2025, 12, 31),
    )
    # Taxe foncière (line 244)
    PropertyLedgerEntry.objects.create(
        property=lmnp_property,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.PROPERTY_TAX,
        amount=Money(Decimal("310.00"), "EUR"),
        entry_date=datetime.date(2025, 12, 31),
    )
    # CFE (line 244, sub-line 243)
    PropertyLedgerEntry.objects.create(
        property=lmnp_property,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.CFE,
        amount=Money(Decimal("170.00"), "EUR"),
        entry_date=datetime.date(2025, 12, 31),
    )
    # Intérêts crédit (line 294)
    PropertyLedgerEntry.objects.create(
        property=lmnp_property,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.LOAN_INTEREST,
        amount=Money(Decimal("4500.00"), "EUR"),
        entry_date=datetime.date(2025, 12, 31),
    )


# ─── Amortization conformity tests ───────────────────────────────────────────


@pytest.mark.django_db
class TestAmortizationConformity:
    """Verify amortization values match the Excel reference spreadsheet."""

    def test_setup_creates_six_components(self, lmnp_setup):
        assets = AmortizationAsset.objects.filter(property=lmnp_setup.property)
        assert assets.count() == 6

    def test_depreciable_total_is_85_percent(self, lmnp_setup):
        """
        Components total = 196 000 * (45+6+7+8+19)% = 196 000 * 85% = 166 600 €.
        Each pct is applied to total_value (not just depreciable portion).
        """
        from property.models.asset import AmortizationSetup as S

        assets = AmortizationAsset.objects.filter(property=lmnp_setup.property)
        total = sum(a.value_total.amount for a in assets)
        pct_sum = sum(c["pct"] for c in S.STANDARD_COMPONENTS)
        expected = (Decimal(196000) * Decimal(pct_sum) / Decimal(100)).quantize(
            Decimal("0.01")
        )
        assert approx_equal(total, expected)

    def test_gros_oeuvre_value(self, lmnp_setup):
        """Gros œuvre = 196 000 * 45% = 88 200 €."""
        asset = AmortizationAsset.objects.get(
            property=lmnp_setup.property, label="Gros œuvre"
        )
        expected = Decimal(196000) * Decimal(45) / Decimal(100)
        assert approx_equal(asset.value_total.amount, expected)

    def test_total_amortization_2025(self, lmnp_setup):
        """Dotation 2025 = 1260 + 548.80 + 627.20 + 3103.33 + 392 = 5 931,33 €."""
        total = get_total_amortization(lmnp_setup.property.pk, 2025)
        assert total == Decimal("5931.33")

    def test_cerfa_category_set_on_components(self, lmnp_setup):
        """Each component has a cerfa_category set."""
        assets = AmortizationAsset.objects.filter(property=lmnp_setup.property)
        for asset in assets:
            assert asset.cerfa_category in [
                "terrains",
                "constructions",
                "installations",
                "autres",
            ], (
                f"Asset '{asset.label}' has unexpected cerfa_category: {asset.cerfa_category}"
            )

    def test_gros_oeuvre_category(self, lmnp_setup):
        asset = AmortizationAsset.objects.get(
            property=lmnp_setup.property, label="Gros œuvre"
        )
        assert asset.cerfa_category == "constructions"

    def test_installations_electriques_category(self, lmnp_setup):
        asset = AmortizationAsset.objects.get(
            property=lmnp_setup.property, label="Installations électriques"
        )
        assert asset.cerfa_category == "installations"

    def test_agencements_category(self, lmnp_setup):
        asset = AmortizationAsset.objects.get(
            property=lmnp_setup.property, label="Agencements intérieurs"
        )
        assert asset.cerfa_category == "installations"

    def test_deferred_balance_zero_first_year_with_surplus(
        self, lmnp_setup, lmnp_property
    ):
        """If recettes >> amort, all amort is deducted and nothing is deferred."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("100000.00"), "EUR"),
            entry_date=datetime.date(2025, 6, 1),
        )
        balance = get_deferred_amortization_balance(lmnp_property.pk, 2025)
        assert balance == Decimal(0)

    def test_deferred_balance_accumulates_when_deficit(self, lmnp_setup):
        """With no income, full amort is deferred."""
        balance = get_deferred_amortization_balance(lmnp_setup.property.pk, 2025)
        total = get_total_amortization(lmnp_setup.property.pk, 2025)
        assert balance == total


# ─── LMNP summary conformity tests ───────────────────────────────────────────


@pytest.mark.django_db
class TestLmnpSummaryConformity:
    """Verify get_lmnp_summary output against the Excel reference."""

    def test_recettes_2025(self, lmnp_setup, lmnp_entries_2025, lmnp_property):
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert summary["recettes"] == Decimal("2148.00")

    def test_charges_exploitation_2025(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """Charges d'exploitation (lines 242+244) = 1766.21 + 310 + 170 = 2246.21."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert approx_equal(summary["charges_exploitation"], Decimal("2246.21"))

    def test_charges_financieres_2025(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """Charges financières (line 294) = 4500."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert summary["charges_financieres"] == Decimal("4500.00")

    def test_total_charges_2025(self, lmnp_setup, lmnp_entries_2025, lmnp_property):
        """Total charges = 2246.21 + 4500 = 6746.21."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert approx_equal(summary["charges"], Decimal("6746.21"))

    def test_result_before_amort_2025(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """Résultat avant amort = 2148 - 6746.21 = -4598.21."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert approx_equal(summary["result"], Decimal("-4598.21"))

    def test_taxable_result_is_deficit_2025(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """Résultat fiscal = -4598.21 (déficit, not zero)."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert approx_equal(summary["taxable_result"], Decimal("-4598.21"))

    def test_amortization_not_deducted_when_deficit(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """With an operating deficit, no amortization is deducted (art. 39C)."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert summary["amortization_deductible"] == Decimal(0)

    def test_full_amort_deferred_when_deficit(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """All amortization is deferred when there is an operating deficit."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert summary["amortization_deferred"] == summary["amortization_total"]

    def test_cerfa_310_2025(self, lmnp_setup, lmnp_entries_2025, lmnp_property):
        """
        2033-B line 310 = recettes - charges - amort_total.
        = 2148 - 6746.21 - amort_total
        """
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        expected = Decimal(2148) - Decimal("6746.21") - summary["amortization_total"]
        assert approx_equal(summary["cerfa_310"], expected)

    def test_cerfa_318_2025(self, lmnp_setup, lmnp_entries_2025, lmnp_property):
        """2033-B line 318 = the dotation that could not be deducted (cap = 0 here)."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert summary["plafond_39c"] == Decimal(0)
        assert (
            summary["cerfa_318"] == summary["amortization_total"] == Decimal("5931.33")
        )
        # The charges deficit itself is NOT reintegrated: it stays a fiscal deficit.
        assert approx_equal(summary["cerfa_352"], Decimal("-4598.21"))

    def test_by_line_218_has_loyers(self, lmnp_setup, lmnp_entries_2025, lmnp_property):
        """Line 218 = loyers."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert "218" in summary["by_line"]
        assert summary["by_line"]["218"] == Decimal("2148.00")

    def test_by_line_244_has_impots(self, lmnp_setup, lmnp_entries_2025, lmnp_property):
        """Line 244 = taxe foncière + CFE = 310 + 170 = 480."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert "244" in summary["by_line"]
        assert summary["by_line"]["244"] == Decimal("480.00")

    def test_by_line_243_has_cfe_only(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """Line 243 = CFE sub-total = 170."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert "243" in summary["by_line"]
        assert summary["by_line"]["243"] == Decimal("170.00")

    def test_by_line_294_has_interets(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """Line 294 = intérêts = 4500."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert "294" in summary["by_line"]
        assert summary["by_line"]["294"] == Decimal("4500.00")

    def test_by_line_242_has_charges_exploitation(
        self, lmnp_setup, lmnp_entries_2025, lmnp_property
    ):
        """Line 242 = charges exploitation = 1766.21."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert "242" in summary["by_line"]
        assert approx_equal(summary["by_line"]["242"], Decimal("1766.21"))


# ─── Recurring ledger entries tests ──────────────────────────────────────────


@pytest.mark.django_db
class TestLmnpSummaryRecurringEntries:
    """Verify that recurring entries are correctly counted in the LMNP summary."""

    def test_monthly_rent_started_before_year_counts_all_occurrences(
        self, lmnp_setup, lmnp_property
    ):
        """Monthly rent started in Dec 2024 must appear in 2025 (12 occurrences)."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("500.00"), "EUR"),
            entry_date=datetime.date(2024, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2026, 12, 31),
        )
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        # 12 months × 500 = 6000
        assert summary["recettes"] == Decimal("6000.00")

    def test_monthly_recurring_not_counted_after_recurrence_end(
        self, lmnp_setup, lmnp_property
    ):
        """Monthly entry whose recurrence_end_date is before the year is excluded."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("500.00"), "EUR"),
            entry_date=datetime.date(2022, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2024, 12, 31),
        )
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert summary["recettes"] == Decimal(0)

    def test_yearly_insurance_started_before_year(self, lmnp_setup, lmnp_property):
        """Yearly insurance started in 2020 must appear once in 2025."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.INSURANCE,
            amount=Money(Decimal("600.00"), "EUR"),
            entry_date=datetime.date(2020, 3, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.YEARLY,
        )
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert summary["charges_exploitation"] == Decimal("600.00")

    def test_recurring_entry_appears_in_by_category(self, lmnp_setup, lmnp_property):
        """by_category must include recurring entry amounts."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category=PropertyLedgerEntry.ManagementCategory.MANAGEMENT_FEES,
            amount=Money(Decimal("100.00"), "EUR"),
            entry_date=datetime.date(2024, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
            recurrence_end_date=datetime.date(2025, 6, 30),
        )
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        # 6 occurrences (Jan–Jun 2025) × 100 = 600
        assert summary["by_category"].get("management_fees") == Decimal("600.00")


# ─── Fiscal deficit carryforward conformity tests ────────────────────────────


@pytest.mark.django_db
class TestFiscalDeficitConformity:
    """Verify the fiscal deficit carryforward logic."""

    def _setup_deficit_2025(self, lmnp_property, lmnp_setup, lmnp_entries_2025):
        """Helper: sets up a deficit year 2025."""
        # lmnp_entries_2025 fixture already creates the deficit

    def test_deficit_2025_is_tracked(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """Déficit 2025 = 4598.21 is added to the history."""
        history = get_fiscal_deficit_history(lmnp_property.pk, 2025)
        assert 2025 in history
        assert approx_equal(history[2025], Decimal("4598.21"))

    def test_deficit_carryforward_2025(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """Total carryforward after 2025 = 4598.21."""
        carryforward = get_fiscal_deficit_carryforward(lmnp_property.pk, 2025)
        assert approx_equal(carryforward, Decimal("4598.21"))

    def test_deficit_reduced_by_future_profit(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """A profit year reduces the deficit carryforward."""
        # Add a large income in 2026
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("50000.00"), "EUR"),
            entry_date=datetime.date(2026, 6, 1),
        )
        carryforward_2025 = get_fiscal_deficit_carryforward(lmnp_property.pk, 2025)
        carryforward_2026 = get_fiscal_deficit_carryforward(lmnp_property.pk, 2026)
        # After a profitable year, deficit should be reduced or eliminated
        assert carryforward_2026 < carryforward_2025

    def test_no_deficit_without_entries(self, lmnp_property, lmnp_setup):
        """Without ledger entries, fiscal result is 0 (no deficit)."""
        history = get_fiscal_deficit_history(lmnp_property.pk, 2025)
        assert history == {} or all(d == Decimal(0) for d in history.values())

    def test_deficit_expires_after_10_years(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """Déficits expire after 10 years."""
        # 2025 deficit expires after 2035
        history_2035 = get_fiscal_deficit_history(lmnp_property.pk, 2035)
        history_2036 = get_fiscal_deficit_history(lmnp_property.pk, 2036)
        # In 2035 (year 2025 is still within 10 years), deficit still there
        assert 2025 in history_2035
        # In 2036 (year 2025 is > 10 years old), deficit expired
        assert 2025 not in history_2036

    def test_deficit_from_year_n1_appears_in_5gj(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """2042-C PRO case 5GJ for year 2026 = 2025 deficit."""
        accounting = get_accounting_data([lmnp_property], 2026)
        form_2042c = accounting["form_2042c"]
        # 5GJ = deficit from N-1 = 2025
        entry_5gj = next(
            c for c in form_2042c["deficit_cases_list"] if c["label"] == "5GJ"
        )
        assert approx_equal(entry_5gj["amount"], Decimal("4598.21"))


# ─── 2033-A Bilan conformity tests ───────────────────────────────────────────


@pytest.mark.django_db
class TestBilanConformity:
    """Verify 2033-A bilan data against the Excel reference."""

    def test_immobilisations_brutes_include_land(self, lmnp_property, lmnp_setup):
        """
        Immobilisations brutes = assets + land = 166 600 + 29 400 = 196 000 €.
        """
        bilan = get_bilan_data(lmnp_property.pk, 2025)
        assert approx_equal(bilan["immobilisations_brutes"], Decimal("196000.00"))

    def test_amortissements_cumules_2025(self, lmnp_property, lmnp_setup):
        """Cumul amort fin 2025 = total dotation 2025 (first year)."""
        total = get_total_amortization(lmnp_property.pk, 2025)
        bilan = get_bilan_data(lmnp_property.pk, 2025)
        assert approx_equal(bilan["amortissements_cumules"], total)

    def test_valeur_nette_2025(self, lmnp_property, lmnp_setup):
        """VNC = brut - cumul amort."""
        bilan = get_bilan_data(lmnp_property.pk, 2025)
        expected = bilan["immobilisations_brutes"] - bilan["amortissements_cumules"]
        assert bilan["valeur_nette_comptable"] == expected

    def test_cout_revient_acquisitions_first_year(self, lmnp_property, lmnp_setup):
        """First year: acquisition cost = full 196 000 €."""
        bilan = get_bilan_data(lmnp_property.pk, 2025)
        assert approx_equal(bilan["cout_revient_acquisitions"], Decimal("196000.00"))

    def test_cout_revient_zero_subsequent_year(self, lmnp_property, lmnp_setup):
        """No new acquisitions in year 2: cost = 0."""
        bilan = get_bilan_data(lmnp_property.pk, 2026)
        assert bilan["cout_revient_acquisitions"] == Decimal(0)

    def test_passif_balances_with_actif(self, lmnp_property, lmnp_setup, lmnp_loan):
        """Balance sheet equation: total_capitaux_propres + emprunts == valeur_nette_comptable."""
        bilan = get_bilan_data(lmnp_property.pk, 2025)
        assert (
            bilan["total_capitaux_propres"] + bilan["emprunts"]
            == bilan["valeur_nette_comptable"]
        )

    def test_capital_individuel_plus_resultat_equals_capitaux_propres(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """capital_individuel + resultat_exercice == total_capitaux_propres."""
        bilan = get_bilan_data(lmnp_property.pk, 2025)
        assert (
            bilan["capital_individuel"] + bilan["resultat_exercice"]
            == bilan["total_capitaux_propres"]
        )

    def test_total_capitaux_propres_equals_vnc_minus_emprunts(
        self, lmnp_property, lmnp_setup, lmnp_loan
    ):
        """total_capitaux_propres = valeur_nette_comptable - emprunts."""
        bilan = get_bilan_data(lmnp_property.pk, 2025)
        expected = bilan["valeur_nette_comptable"] - bilan["emprunts"]
        assert bilan["total_capitaux_propres"] == expected


# ─── 2033-C Immobilisations conformity tests ─────────────────────────────────


@pytest.mark.django_db
class TestImmobilisationsConformity:
    """Verify 2033-C movement data."""

    def test_movements_returns_dict(self, lmnp_property, lmnp_setup):
        result = get_immobilisation_movements(lmnp_property.pk, 2025)
        assert "rows" in result
        assert "by_cerfa_category" in result
        assert "terrains_value" in result

    def test_terrains_value_from_setup(self, lmnp_property, lmnp_setup):
        """Terrains = 196 000 * 15% = 29 400 €."""
        result = get_immobilisation_movements(lmnp_property.pk, 2025)
        assert approx_equal(result["terrains_value"], Decimal("29400.00"))

    def test_constructions_category_has_data(self, lmnp_property, lmnp_setup):
        """Constructions (gros œuvre, étanchéité, toiture) have value > 0."""
        result = get_immobilisation_movements(lmnp_property.pk, 2025)
        constructions = result["by_cerfa_category"]["constructions"]
        assert constructions["value_end"] > Decimal(0)

    def test_first_year_acquisitions_equals_value_end(self, lmnp_property, lmnp_setup):
        """First year: acquisitions == value_end (all assets acquired this year)."""
        result = get_immobilisation_movements(lmnp_property.pk, 2025)
        for row in result["rows"]:
            assert approx_equal(row["acquisitions"], row["value_end"]), (
                f"Asset '{row['label']}': acquisitions {row['acquisitions']} != value_end {row['value_end']}"
            )

    def test_second_year_value_start_equals_value_end(self, lmnp_property, lmnp_setup):
        """Second year: value_start == value_end (no new acquisitions)."""
        result = get_immobilisation_movements(lmnp_property.pk, 2026)
        for row in result["rows"]:
            assert approx_equal(row["value_start"], row["value_end"])


# ─── 2042-C PRO conformity tests ─────────────────────────────────────────────


@pytest.mark.django_db
class TestForm2042CConformity:
    """Verify 2042-C PRO values against the Excel reference."""

    def test_case_5ny_is_deficit_amount_2025(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """Case 5NY (déficit, régime réel, cas général) = −352 when deficit."""
        accounting = get_accounting_data([lmnp_property], 2025)
        form_2042c = accounting["form_2042c"]
        assert approx_equal(form_2042c["case_5ny"], Decimal("4598.21"))

    def test_case_5na_is_zero_when_deficit_2025(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """Case 5NA (revenus imposables) = 0 when there is a deficit."""
        accounting = get_accounting_data([lmnp_property], 2025)
        form_2042c = accounting["form_2042c"]
        assert form_2042c["case_5na"] == Decimal(0)

    def test_is_benefice_false_when_deficit(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        accounting = get_accounting_data([lmnp_property], 2025)
        assert accounting["form_2042c"]["is_benefice"] is False

    def test_case_5cd_is_12_for_full_year(self, lmnp_property, lmnp_setup):
        """Case 5CD = 12 for a full-year exercise (activity started 1 January)."""
        accounting = get_accounting_data([lmnp_property], 2025)
        assert accounting["form_2042c"]["case_5cd"] == 12
        accounting = get_accounting_data([lmnp_property], 2026)
        assert accounting["form_2042c"]["case_5cd"] == 12

    def test_case_5cd_first_year_started_in_october(self, lmnp_property):
        """Activity started 16 October → first fiscal year lasts 3 months."""
        lmnp_property.lmnp_start_date = datetime.date(2025, 10, 16)
        lmnp_property.save()
        accounting = get_accounting_data([lmnp_property], 2025)
        assert accounting["form_2042c"]["case_5cd"] == 3
        accounting = get_accounting_data([lmnp_property], 2026)
        assert accounting["form_2042c"]["case_5cd"] == 12

    def test_case_5na_positive_when_profit(self, lmnp_property, lmnp_setup):
        """Case 5NA > 0 when there is a taxable profit."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("100000.00"), "EUR"),
            entry_date=datetime.date(2025, 6, 1),
        )
        accounting = get_accounting_data([lmnp_property], 2025)
        # With large income and no prior deficit, taxable result > 0
        assert accounting["form_2042c"]["case_5na"] > Decimal(0)
        assert accounting["form_2042c"]["case_5ny"] == Decimal(0)


# ─── 2033-B result lines conformity ──────────────────────────────────────────


@pytest.mark.django_db
class TestForm2033BConformity:
    """Verify 2033-B computed lines against the Excel reference."""

    def test_cerfa_310_formula(self, lmnp_property, lmnp_setup, lmnp_entries_2025):
        """2033-B-310 = recettes - charges - amort_total."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        expected_310 = (
            summary["recettes"] - summary["charges"] - summary["amortization_total"]
        )
        assert approx_equal(summary["cerfa_310"], expected_310)

    def test_cerfa_318_never_exceeds_the_dotation(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """2033-B-318 is capped by the dotation: the charges deficit is not reintegrated."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        assert summary["cerfa_310"] < Decimal(0)
        assert summary["cerfa_318"] == summary["amortization_total"]
        assert summary["cerfa_318"] < abs(summary["cerfa_310"])

    def test_310_plus_318_equals_result_before_amortization(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """When nothing is deductible, 310 + 318 = recettes − charges (−4 598,21)."""
        summary = get_lmnp_summary(lmnp_property.pk, 2025)
        computed = summary["cerfa_310"] + summary["cerfa_318"]
        assert approx_equal(computed, Decimal("-4598.21"))

    def test_cerfa_352_is_signed_when_deficit(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """2033-B-352 carries the deficit (negative), it is not clipped to zero."""
        accounting = get_accounting_data([lmnp_property], 2025)
        assert approx_equal(accounting["form_2033b"]["cerfa_352"], Decimal("-4598.21"))

    def test_cerfa_370_equals_352_when_deficit(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """2033-B-370 = 352 when there is no profit to offset prior deficits."""
        accounting = get_accounting_data([lmnp_property], 2025)
        form = accounting["form_2033b"]
        assert form["cerfa_370"] == form["cerfa_352"]
        assert form["cerfa_360"] == Decimal(0)

    def test_prior_deficit_imputed_once(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """Deficit 4 598,21 in 2025, profit in 2026: 360 = deficit, 370 = 352 − 360."""
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal("20000.00"), "EUR"),
            entry_date=datetime.date(2026, 6, 1),
        )
        form = get_accounting_data([lmnp_property], 2026)["form_2033b"]
        # 2026: recettes 20 000, dotation 5 931,33 fully deductible, plus the
        # 5 931,33 deferred from 2025 is deducted line 350.
        assert form["cerfa_318"] == Decimal(0)
        assert form["cerfa_350"] == Decimal("5931.33")
        assert form["cerfa_352"] == Decimal(20000) - 2 * Decimal("5931.33")
        assert approx_equal(form["cerfa_360"], Decimal("4598.21"))
        assert form["cerfa_370"] == form["cerfa_352"] - form["cerfa_360"]
        assert (
            get_accounting_data([lmnp_property], 2026)["form_2042c"]["case_5na"]
            == form["cerfa_370"]
        )


# ─── form_2042c deficit_cases_list ───────────────────────────────────────────


@pytest.mark.django_db
class TestForm2042cDeficitCasesList:
    """Tests for the deficit_cases_list field added to form_2042c."""

    def test_deficit_cases_list_has_10_entries(self, lmnp_property, lmnp_setup):
        """deficit_cases_list must always contain exactly 10 entries (5GJ..5GA)."""
        accounting = get_accounting_data([lmnp_property], 2025)
        cases = accounting["form_2042c"]["deficit_cases_list"]
        assert len(cases) == 10

    def test_deficit_cases_list_labels(self, lmnp_property, lmnp_setup):
        """Labels must be 5GJ (N-1) through 5GA (N-10) in order."""
        accounting = get_accounting_data([lmnp_property], 2025)
        cases = accounting["form_2042c"]["deficit_cases_list"]
        expected_labels = [
            "5GJ",
            "5GI",
            "5GH",
            "5GG",
            "5GF",
            "5GE",
            "5GD",
            "5GC",
            "5GB",
            "5GA",
        ]
        assert [c["label"] for c in cases] == expected_labels

    def test_deficit_cases_list_origin_years(self, lmnp_property, lmnp_setup):
        """origin_year for each case must decrease from year-1 to year-10."""
        accounting = get_accounting_data([lmnp_property], 2025)
        cases = accounting["form_2042c"]["deficit_cases_list"]
        expected_years = list(range(2024, 2014, -1))
        assert [c["origin_year"] for c in cases] == expected_years

    def test_deficit_cases_list_contains_current_year_deficit(
        self, lmnp_property, lmnp_setup, lmnp_entries_2025
    ):
        """After a deficit year, next year's 5GJ entry (N-1 = 2025) must hold the deficit."""
        accounting = get_accounting_data([lmnp_property], 2026)
        cases = accounting["form_2042c"]["deficit_cases_list"]
        # 5GJ is N-1 = 2025
        entry_5gj = next(c for c in cases if c["label"] == "5GJ")
        assert entry_5gj["origin_year"] == 2025
        assert approx_equal(entry_5gj["amount"], Decimal("4598.21"))
