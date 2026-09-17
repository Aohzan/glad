"""
Golden tests: Glad must reproduce the reference LMNP workbook.

The scenario is copied from "Suivi LMNP.xlsx" (LMNP.blog simulator v2025c),
sheets 1-Biens_Immos, 2-Crédits, 3-Loyers_Charges and Calcul_Liasse:

Bien 1 "Orléans": 110 000 € bought 2024-11-06, LMNP activity from 2025-01-01,
  land 15 %, detailed components (45 % gros œuvre 70 y, 6 % électricité 30 y,
  7 % étanchéité 25 y, 8 % toiture 25 y, 19 % agencements 12 y),
  furniture 4 750 € / 10 y from 2025-01-01.
  2025: rents 7 352,17 ; charges 1 316,18 ; taxe foncière 708,03 ;
        interest 4 143,27 ; loan insurance 179,88.
Bien 2 "Angers": 75 000 € + 22 834 € acquisition fees capitalised, bought and
  rented from 2025-10-16, same breakdown; other assets: furniture 1 273 € / 10 y
  (2025-11-10), électricité 619 € / 20 y (2025-10-18), chauffe-eau 1 385 € / 15 y
  (2025-10-29).
  2025: rents 236 ; charges 95,25 ; interest 459,64 ; loan insurance 21,12.

Workbook outputs (Calcul_Liasse, column E = 2025, F = 2026):
  dotation 2025 (2033-C 572)         4 460,82
  résultat d'exploitation (270)        806,89
  résultat comptable (310)          −3 796,02
  plafond 39 C (E44)                   664,80
  amortissement déduit                 664,80
  réintégration 318 (E52)            3 796,02
  résultat fiscal 352 (E63)              0,00
  amortissements différés fin 2025   3 796,02
  durée de l'exercice 5CD                  12
  dotation 2026                      7 015,04
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
)
from property.services.tax_lmnp import (
    FiscalCarry,
    LmnpYearInputs,
    compute_year,
    compute_years,
    exercise_months,
    get_accounting_data,
    get_total_amortization,
)
from property.utils.date_utils import days360

D = Decimal
CENT = D("0.01")

# ─── Workbook inputs for 2025, all properties combined ────────────────────────

EXCEL_2025 = LmnpYearInputs(
    year=2025,
    revenue_218=D("7588.17"),  # 3-Loyers_Charges!AC10
    external_charges_242=D(
        "1612.43"
    ),  # 3-Loyers_Charges!AE10 (charges + assurance crédit)
    taxes_244=D("708.03"),  # 3-Loyers_Charges!AI10
    cfe_243=D(0),
    financial_charges_294=D("4602.91"),  # 2-Crédits!T10
    depreciation_254=D("4460.82"),  # Calcul_Liasse!E29
    activity_start=datetime.date(2025, 1, 1),
)


# ─── Pure engine ──────────────────────────────────────────────────────────────


class TestComputeYearAgainstWorkbook:
    def test_2025_matches_calcul_liasse(self):
        result, carry = compute_year(EXCEL_2025)
        assert result.operating_result_270 == D("806.89")  # E38
        assert result.accounting_result_310 == D("-3796.02")  # E40
        assert result.depreciation_cap_39c == D("664.80")  # E44
        assert result.depreciation_deducted == D("664.80")  # MIN(E37, E44)
        assert result.depreciation_reintegrated_318 == D("3796.02")  # E52
        assert result.deferred_depreciation_used_350 == D(0)  # E59
        assert result.deferred_depreciation_end == D("3796.02")  # E61
        assert result.fiscal_result_352 == D(0)  # E63
        assert result.fiscal_result_370 == D(0)  # E69
        assert result.case_5na == D(0)
        assert result.case_5ny == D(0)
        assert result.case_5cd == 12  # E111
        assert result.deficits_end == {}
        assert carry.deferred_depreciation == D("3796.02")
        assert carry.deficits == {}

    def test_deferred_amortization_is_deducted_in_a_profitable_year(self):
        """Line 350: the 2025 ARD are deducted in 2026 up to the profit."""
        _, carry = compute_year(EXCEL_2025)
        year_2026 = LmnpYearInputs(
            year=2026,
            revenue_218=D(12000),
            external_charges_242=D(2000),
            depreciation_254=D(5000),
        )
        result, carry = compute_year(year_2026, carry)
        assert result.depreciation_cap_39c == D(10000)
        assert result.depreciation_deducted == D(5000)
        assert result.depreciation_reintegrated_318 == D(0)
        assert result.deferred_depreciation_start == D("3796.02")
        assert result.deferred_depreciation_used_350 == D("3796.02")
        assert result.deferred_depreciation_end == D(0)
        assert result.fiscal_result_352 == D(12000) - D(2000) - D(5000) - D("3796.02")
        assert result.case_5na == result.fiscal_result_352
        assert carry.deferred_depreciation == D(0)

    def test_deferred_amortization_never_creates_a_deficit(self):
        _, carry = compute_year(EXCEL_2025)
        small_profit = LmnpYearInputs(
            year=2026, revenue_218=D(3000), external_charges_242=D(1000)
        )
        result, _ = compute_year(small_profit, carry)
        assert result.deferred_depreciation_used_350 == D(2000)
        assert result.fiscal_result_352 == D(0)
        assert result.deferred_depreciation_end == D("1796.02")


class TestComputeYearRules:
    def test_charges_deficit_is_a_reportable_deficit_not_a_reintegration(self):
        """Art. 39 C: only the dotation is reintegrated; the charges deficit stays."""
        inputs = LmnpYearInputs(
            year=2025,
            revenue_218=D(1000),
            external_charges_242=D(3000),
            depreciation_254=D(500),
        )
        result, carry = compute_year(inputs)
        assert result.depreciation_cap_39c == D(0)
        assert result.depreciation_reintegrated_318 == D(500)  # capped by the dotation
        assert result.accounting_result_310 == D(-2500)
        assert result.fiscal_result_352 == D(-2000)
        assert result.case_5ny == D(2000)
        assert result.case_5na == D(0)
        assert result.deficits_end == {2025: D(2000)}
        assert carry.deficits == {2025: D(2000)}
        assert carry.deferred_depreciation == D(500)

    def test_prior_deficit_is_imputed_once(self):
        """Regression: deficit 1 000 in N, profit 1 500 in N+1 → 5NA = 500."""
        years = compute_years(
            [
                LmnpYearInputs(year=2025, external_charges_242=D(1000)),
                LmnpYearInputs(year=2026, revenue_218=D(1500)),
            ]
        )
        second = years[1]
        assert second.prior_deficits_start == {2025: D(1000)}
        assert second.prior_deficits_used_360 == D(1000)
        assert second.fiscal_result_352 == D(1500)
        assert second.fiscal_result_370 == D(500)
        assert second.case_5na == D(500)
        assert second.deficits_end == {}

    def test_deficits_are_imputed_oldest_first(self):
        years = compute_years(
            [
                LmnpYearInputs(year=2020, external_charges_242=D(1000)),
                LmnpYearInputs(year=2021, external_charges_242=D(500)),
                LmnpYearInputs(year=2022, revenue_218=D(800)),
            ]
        )
        assert years[-1].deficits_end == {2020: D(200), 2021: D(500)}
        assert years[-1].prior_deficits_used_360 == D(800)
        assert years[-1].fiscal_result_370 == D(0)

    def test_deficit_expires_after_ten_years(self):
        """A 2015 deficit is usable until 2025 (5GA) and gone in 2026."""
        inputs = [LmnpYearInputs(year=2015, external_charges_242=D(100))]
        inputs += [LmnpYearInputs(year=y) for y in range(2016, 2027)]
        years = {r.year: r for r in compute_years(inputs)}
        assert years[2025].deficits_end == {2015: D(100)}
        by_box = {
            box: (origin, amount) for box, origin, amount in years[2025].deficit_cases
        }
        assert by_box["5GA"] == (2015, D(100))
        assert years[2026].deficits_end == {}

    def test_deficit_cases_5g_list_previous_ten_years(self):
        result, _ = compute_year(
            LmnpYearInputs(year=2030), FiscalCarry(deficits={2029: D(7)})
        )
        boxes = [c[0] for c in result.deficit_cases]
        years = [c[1] for c in result.deficit_cases]
        assert boxes == [
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
        assert years == list(range(2029, 2019, -1))
        assert result.deficit_cases[0] == ("5GJ", 2029, D(7))

    def test_accounting_fees_do_not_reduce_the_39c_cap(self):
        """BOI-BIC-AMT-20-40-10-20 § 70: frais de comptabilité are not charges afférentes."""
        without = LmnpYearInputs(
            year=2025,
            revenue_218=D(5000),
            external_charges_242=D(1000),
            depreciation_254=D(9000),
        )
        with_fees = LmnpYearInputs(
            year=2025,
            revenue_218=D(5000),
            external_charges_242=D(1300),
            accounting_fees=D(300),
            depreciation_254=D(9000),
        )
        assert compute_year(without)[0].depreciation_cap_39c == D(4000)
        assert compute_year(with_fees)[0].depreciation_cap_39c == D(4000)
        # …but they remain deductible: the accounting result is lower.
        assert compute_year(with_fees)[0].accounting_result_310 == (
            compute_year(without)[0].accounting_result_310 - D(300)
        )

    def test_exercise_months(self):
        assert exercise_months(2025, datetime.date(2025, 10, 16)) == 3
        assert exercise_months(2025, datetime.date(2025, 1, 1)) == 12
        assert exercise_months(2026, datetime.date(2025, 10, 16)) == 12
        assert exercise_months(2025, None) == 12

    def test_as_dict_exposes_every_line(self):
        data = compute_year(EXCEL_2025)[0].as_dict()
        assert data["fiscal_result_352"] == D(0)
        assert data["is_profit"] is True
        assert data["deficit_carryforward"] == D(0)


# ─── Amortization (1-Biens_Immos amortization tables) ─────────────────────────


class TestDays360:
    @pytest.mark.parametrize(
        ("start", "expected"),
        [
            (datetime.date(2025, 1, 1), 360),
            (datetime.date(2025, 10, 16), 75),
            (datetime.date(2025, 11, 10), 51),
            (datetime.date(2025, 10, 18), 73),
            (datetime.date(2025, 10, 29), 62),
            (datetime.date(2020, 7, 1), 180),
            (datetime.date(2024, 11, 6), 55),
        ],
    )
    def test_days_to_year_end(self, start, expected):
        assert days360(start, datetime.date(start.year, 12, 31)) == expected


def _asset(value, years, start, category="constructions"):
    return AmortizationAsset(
        label="x",
        beginning_date=start,
        value_total=Money(D(str(value)), "EUR"),
        duration_years=years,
        cerfa_category=category,
    )


ORLEANS_START = datetime.date(2025, 1, 1)
ANGERS_START = datetime.date(2025, 10, 16)


class TestComponentDotations:
    """Per-line values of the workbook amortization table (column Z = 2025)."""

    @pytest.mark.parametrize(
        ("value", "years", "start", "expected_2025"),
        [
            # Orléans (full year)
            ("49500", 70, ORLEANS_START, "707.14"),
            ("6600", 30, ORLEANS_START, "220.00"),
            ("7700", 25, ORLEANS_START, "308.00"),
            ("8800", 25, ORLEANS_START, "352.00"),
            ("20900", 12, ORLEANS_START, "1741.67"),
            ("4750", 10, ORLEANS_START, "475.00"),
            # Angers (75 days on a 30/360 basis)
            ("44025.30", 70, ANGERS_START, "131.03"),
            ("5870.04", 30, ANGERS_START, "40.76"),
            ("6848.38", 25, ANGERS_START, "57.07"),
            ("7826.72", 25, ANGERS_START, "65.22"),
            ("18588.46", 12, ANGERS_START, "322.72"),
            ("1273", 10, datetime.date(2025, 11, 10), "18.03"),
            ("619", 20, datetime.date(2025, 10, 18), "6.28"),
            ("1385", 15, datetime.date(2025, 10, 29), "15.90"),
        ],
    )
    def test_first_year_dotation(self, value, years, start, expected_2025):
        assert _asset(value, years, start).get_annual_amortization(2025) == D(
            expected_2025
        )

    def test_land_is_never_amortized(self):
        assert _asset("16500", None, ORLEANS_START, "terrains").get_annual_amortization(
            2025
        ) == D(0)

    def test_whole_life_adds_up_to_the_value(self):
        asset = _asset("44025.30", 70, ANGERS_START)
        total = sum(asset.get_annual_amortization(y) for y in range(2025, 2097))
        assert total == D("44025.30")
        assert asset.amortization_end_year == 2095
        assert asset.get_annual_amortization(2096) == D(0)


# ─── Whole scenario through the database ──────────────────────────────────────


def _entry(prop, category, amount, day, income=False):
    return PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=(
            PropertyLedgerEntry.FlowType.INCOME
            if income
            else PropertyLedgerEntry.FlowType.EXPENSE
        ),
        management_category=category,
        amount=Money(D(amount), "EUR"),
        entry_date=day,
    )


@pytest.fixture
def workbook(db):
    cat = PropertyLedgerEntry.ManagementCategory
    orleans = Property.objects.create(
        name="Orléans",
        property_type=Property.APARTMENT,
        buying_value=Money(110_000, "EUR"),
        buying_date=datetime.date(2024, 11, 6),
        lmnp_start_date=datetime.date(2025, 1, 1),
        notary_fees=Money(6_497, "EUR"),
        agency_fees=Money(10_400, "EUR"),
        credit_fees=Money(2_633, "EUR"),
        tax_regime=Property.TaxRegime.LMNP_REEL,
    )
    angers = Property.objects.create(
        name="Angers",
        property_type=Property.APARTMENT,
        buying_value=Money(75_000, "EUR"),
        buying_date=datetime.date(2025, 10, 16),
        lmnp_start_date=datetime.date(2025, 10, 16),
        tax_regime=Property.TaxRegime.LMNP_REEL,
    )
    # Orléans: fees are not capitalised (bought before the activity started)
    AmortizationSetup.objects.create(
        property=orleans, total_value=Money(110_000, "EUR"), land_percentage=D(15)
    ).initialize_components()
    # Angers: acquisition fees 7 449 + 13 000 + 2 385 = 22 834 are capitalised
    AmortizationSetup.objects.create(
        property=angers,
        total_value=Money(75_000 + 22_834, "EUR"),
        land_percentage=D(15),
    ).initialize_components()

    def other(prop, label, value, years, start, category):
        AmortizationAsset.objects.create(
            property=prop,
            label=label,
            beginning_date=start,
            value_total=Money(D(value), "EUR"),
            duration_years=years,
            cerfa_category=category,
        )

    other(orleans, "Meubles", "4750", 10, ORLEANS_START, "autres")
    other(angers, "Meubles", "1273", 10, datetime.date(2025, 11, 10), "autres")
    other(
        angers,
        "Rénovation électrique",
        "619",
        20,
        datetime.date(2025, 10, 18),
        "installations",
    )
    other(
        angers, "Chauffe-eau", "1385", 15, datetime.date(2025, 10, 29), "installations"
    )

    dec = datetime.date(2025, 12, 31)
    _entry(orleans, cat.RENT_COLLECTED, "7352.17", dec, income=True)
    _entry(orleans, cat.COOWNERSHIP, "1316.18", dec)
    _entry(orleans, cat.PROPERTY_TAX, "708.03", dec)
    _entry(orleans, cat.LOAN_INTEREST, "4143.27", dec)
    _entry(orleans, cat.LOAN_INSURANCE, "179.88", dec)
    _entry(angers, cat.RENT_COLLECTED, "236", dec, income=True)
    _entry(angers, cat.COOWNERSHIP, "95.25", dec)
    _entry(angers, cat.LOAN_INTEREST, "459.64", dec)
    _entry(angers, cat.LOAN_INSURANCE, "21.12", dec)
    return [orleans, angers]


@pytest.mark.django_db
class TestWorkbookScenario:
    def test_orleans_components_start_with_the_activity(self, workbook):
        orleans = workbook[0]
        values = {
            a.label: (a.value_total.amount, a.beginning_date)
            for a in AmortizationAsset.objects.filter(
                property=orleans, is_initial_component=True
            )
        }
        assert values == {
            "Terrain": (D("16500.00"), ORLEANS_START),
            "Gros œuvre": (D("49500.00"), ORLEANS_START),
            "Installations électriques": (D("6600.00"), ORLEANS_START),
            "Étanchéité": (D("7700.00"), ORLEANS_START),
            "Toiture": (D("8800.00"), ORLEANS_START),
            "Agencements intérieurs": (D("20900.00"), ORLEANS_START),
        }

    def test_angers_components_include_the_fees(self, workbook):
        angers = workbook[1]
        values = {
            a.label: a.value_total.amount
            for a in AmortizationAsset.objects.filter(
                property=angers, is_initial_component=True
            )
        }
        assert values["Terrain"] == D("14675.10")
        assert values["Gros œuvre"] == D("44025.30")
        assert values["Agencements intérieurs"] == D("18588.46")
        assert sum(values.values(), D(0)) == D(97_834)

    def test_dotations_2025_and_2026(self, workbook):
        orleans, angers = workbook
        assert get_total_amortization(orleans.pk, 2025) == D("3803.81")
        assert get_total_amortization(angers.pk, 2025) == D("657.01")
        assert get_total_amortization(orleans.pk, 2026) + get_total_amortization(
            angers.pk, 2026
        ) == D("7015.04")

    def test_liasse_2025_matches_calcul_liasse(self, workbook):
        accounting = get_accounting_data(workbook, 2025)
        b = accounting["form_2033b"]
        assert b["recettes"] == D("7588.17")  # 218
        assert b["autres_charges_externes"] == D("1612.43")  # 242
        assert b["impots_taxes"] == D("708.03")  # 244
        assert b["cfe"] == D(0)  # 243
        assert b["amortization_total"] == D("4460.82")  # 254
        assert b["resultat_exploitation_270"] == D("806.89")
        assert b["charges_financieres"] == D("4602.91")  # 294
        assert b["cerfa_310"] == D("-3796.02")
        assert b["plafond_39c"] == D("664.80")
        assert b["amortization_deductible"] == D("664.80")
        assert b["cerfa_318"] == D("3796.02")
        assert b["cerfa_350"] == D(0)
        assert b["cerfa_352"] == D(0)
        assert b["cerfa_360"] == D(0)
        assert b["cerfa_370"] == D(0)
        assert b["deferred_balance"] == D("3796.02")

        c = accounting["form_2042c"]
        assert c["case_5na"] == D(0)
        assert c["case_5ny"] == D(0)
        assert c["case_5cd"] == 12
        assert c["deficit_carryforward"] == D(0)

        suiv = accounting["form_suiv39c"]["rows"]
        assert [r["year"] for r in suiv] == [2025]
        assert suiv[0]["deferred_end"] == D("3796.02")

        assert accounting["form_2031"]["benefice"] == D(0)
        assert accounting["form_2031"]["deficit"] == D(0)

    def test_2033c_totals_2025(self, workbook):
        totals = get_accounting_data(workbook, 2025)["form_2033c"]["totals"]
        # 1-Biens_Immos!Z258: 110 000 + 97 834 + 4 750 + 1 273 + 619 + 1 385
        assert totals["value_end"] == D("215861.00")
        assert totals["acquisitions"] == D("215861.00")
        assert totals["dotation"] == D("4460.82")
        assert totals["amort_end"] == D("4460.82")

    def test_2026_uses_the_deferred_amortization(self, workbook):
        cat = PropertyLedgerEntry.ManagementCategory
        _entry(
            workbook[0],
            cat.RENT_COLLECTED,
            "30000",
            datetime.date(2026, 12, 31),
            income=True,
        )
        b = get_accounting_data(workbook, 2026)["form_2033b"]
        assert b["amortization_total"] == D("7015.04")
        assert b["cerfa_318"] == D(0)
        assert b["deferred_prior"] == D("3796.02")
        assert b["cerfa_350"] == D("3796.02")
        assert b["cerfa_352"] == D(30000) - D("7015.04") - D("3796.02")
        assert b["deferred_balance"] == D(0)
