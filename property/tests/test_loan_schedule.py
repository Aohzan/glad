"""Tests for PropertyLoanAmortizationEntry and PropertyLoan.remaining_balance()."""

import datetime
import io
from decimal import Decimal

from django.test import TestCase
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyLoanAmortizationEntry
from property.utils import build_loan_amortization_balance, build_loan_monthly_maps

# ─── Fixtures ────────────────────────────────────────────────────────────────


def make_property():
    return Property.objects.create(
        name="Test Property",
        property_type=Property.HOUSE,
        buying_value=Money(200_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


def make_standard_loan(prop, *, start=None, months=240, amount=200_000, rate="3.5"):
    start = start or datetime.date(2020, 1, 1)
    end = datetime.date(start.year + months // 12, start.month + months % 12, 1)
    if end.month > 12:
        end = end.replace(year=end.year + 1, month=end.month - 12)
    return PropertyLoan.objects.create(
        property=prop,
        name="Standard Loan",
        start_date=start,
        end_date=end,
        original_amount=Money(amount, "EUR"),
        monthly_payment=Money(Decimal("1159.97"), "EUR"),
        interest_rate=Decimal(rate),
    )


# ─── PropertyLoanAmortizationEntry model ─────────────────────────────────────


class PropertyLoanAmortizationEntryModelTest(TestCase):
    def setUp(self):
        self.prop = make_property()
        self.loan = make_standard_loan(self.prop)

    def _make_entry(self, date, capital, interest, balance):
        return PropertyLoanAmortizationEntry.objects.create(
            loan=self.loan,
            date=date,
            capital=Money(Decimal(str(capital)), "EUR"),
            interest=Money(Decimal(str(interest)), "EUR"),
            remaining_balance_amount=Money(Decimal(str(balance)), "EUR"),
        )

    def test_creation(self):
        entry = self._make_entry(
            datetime.date(2020, 1, 1), "500.00", "583.33", "199500.00"
        )
        self.assertEqual(entry.loan, self.loan)
        self.assertEqual(entry.date, datetime.date(2020, 1, 1))
        self.assertAlmostEqual(float(entry.capital.amount), 500.0, places=2)

    def test_ordering(self):
        self._make_entry(datetime.date(2020, 3, 1), "502", "581", "198500")
        self._make_entry(datetime.date(2020, 1, 1), "500", "583", "199500")
        self._make_entry(datetime.date(2020, 2, 1), "501", "582", "199000")
        dates = list(
            PropertyLoanAmortizationEntry.objects.filter(loan=self.loan).values_list(
                "date", flat=True
            )
        )
        self.assertEqual(dates, sorted(dates))

    def test_unique_together(self):
        from django.db import IntegrityError

        self._make_entry(datetime.date(2020, 1, 1), "500", "583", "199500")
        with self.assertRaises(IntegrityError):
            self._make_entry(datetime.date(2020, 1, 1), "500", "583", "199500")

    def test_str(self):
        entry = self._make_entry(datetime.date(2020, 1, 1), "500", "583", "199500")
        result = str(entry)
        self.assertIn("2020-01-01", result)


# ─── remaining_balance() with amortization table ──────────────────────────────


class RemainingBalanceWithAmortizationTableTest(TestCase):
    def setUp(self):
        self.prop = make_property()
        self.loan = make_standard_loan(self.prop)
        # Insert a few entries
        for i, (capital, interest, balance) in enumerate(
            [
                ("576.64", "583.33", "199423.36"),
                ("578.32", "581.65", "198845.04"),
                ("580.01", "579.96", "198265.03"),
            ]
        ):
            PropertyLoanAmortizationEntry.objects.create(
                loan=self.loan,
                date=datetime.date(2020, i + 1, 1),
                capital=Money(Decimal(capital), "EUR"),
                interest=Money(Decimal(interest), "EUR"),
                remaining_balance_amount=Money(Decimal(balance), "EUR"),
            )

    def test_returns_value_from_table(self):
        balance = self.loan.remaining_balance(datetime.date(2020, 3, 31))
        self.assertAlmostEqual(float(balance.amount), 198265.03, places=1)

    def test_before_first_entry_returns_original(self):
        balance = self.loan.remaining_balance(datetime.date(2019, 12, 31))
        self.assertEqual(balance.amount, Decimal("200000"))

    def test_currency_preserved(self):
        balance = self.loan.remaining_balance(datetime.date(2020, 2, 1))
        self.assertEqual(str(balance.currency), "EUR")

    def test_takes_most_recent_entry_on_or_before_date(self):
        # Ask for date between entry 2 and entry 3
        balance = self.loan.remaining_balance(datetime.date(2020, 2, 15))
        self.assertAlmostEqual(float(balance.amount), 198845.04, places=1)


# ─── remaining_balance() fallback (no amortization table) ────────────────────


class RemainingBalanceFallbackTest(TestCase):
    def setUp(self):
        self.prop = make_property()
        self.loan = make_standard_loan(self.prop)

    def test_before_start(self):
        balance = self.loan.remaining_balance(datetime.date(2019, 12, 31))
        self.assertEqual(balance.amount, Decimal("200000"))

    def test_after_end(self):
        balance = self.loan.remaining_balance(datetime.date(2041, 1, 1))
        self.assertEqual(balance.amount, Decimal("0"))

    def test_midpoint_less_than_original(self):
        balance = self.loan.remaining_balance(datetime.date(2030, 1, 1))
        self.assertLess(balance.amount, Decimal("200000"))
        self.assertGreater(balance.amount, Decimal("0"))

    def test_currency_preserved(self):
        balance = self.loan.remaining_balance(datetime.date(2025, 1, 1))
        self.assertEqual(str(balance.currency), "EUR")


# ─── build_loan_amortization_balance() ───────────────────────────────────────


class BuildLoanAmortizationBalanceTest(TestCase):
    def test_zero_months_elapsed(self):
        balance = build_loan_amortization_balance(
            original_amount=Decimal("100000"),
            interest_rate=Decimal("3.5"),
            payment_sequence=[Decimal("579.96")] * 240,
            months_elapsed=0,
        )
        self.assertEqual(balance, Decimal("100000"))

    def test_full_repayment(self):
        monthly = Decimal("1159.97")
        balance = build_loan_amortization_balance(
            original_amount=Decimal("200000"),
            interest_rate=Decimal("3.5"),
            payment_sequence=[monthly] * 240,
            months_elapsed=240,
        )
        self.assertAlmostEqual(float(balance), 0.0, delta=50.0)

    def test_zero_interest_rate(self):
        monthly = Decimal("1000")
        balance = build_loan_amortization_balance(
            original_amount=Decimal("24000"),
            interest_rate=Decimal("0"),
            payment_sequence=[monthly] * 24,
            months_elapsed=12,
        )
        self.assertAlmostEqual(float(balance), 12000.0, delta=1.0)

    def test_balance_never_negative(self):
        balance = build_loan_amortization_balance(
            original_amount=Decimal("1000"),
            interest_rate=Decimal("3.5"),
            payment_sequence=[Decimal("10000")] * 12,
            months_elapsed=12,
        )
        self.assertEqual(balance, Decimal("0"))


# ─── CSV import view ──────────────────────────────────────────────────────────


class ImportLoanAmortizationViewTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user("testuser", password="pass")  # type: ignore
        self.client.force_login(self.user)
        self.prop = make_property()
        self.loan = make_standard_loan(self.prop)

    def _csv_upload(self, content, filename="amort.csv"):
        return self.client.post(
            f"/property/{self.prop.pk}/loans/{self.loan.pk}/amortization/import/",
            {"csv_file": io.BytesIO(content.encode())},
            format="multipart",
        )

    def test_valid_csv_creates_entries(self):
        csv = "date,capital,interets,capital_restant\n2020-01-01,576.64,583.33,199423.36\n2020-02-01,578.32,581.65,198845.04\n"
        response = self._csv_upload(csv)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            PropertyLoanAmortizationEntry.objects.filter(loan=self.loan).count(), 2
        )

    def test_invalid_row_aborts_entirely(self):
        csv = "date,capital,interets,capital_restant\n2020-01-01,576.64,583.33,199423.36\n2020-02-01,BAD,581.65,198845.04\n"
        response = self._csv_upload(csv)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            PropertyLoanAmortizationEntry.objects.filter(loan=self.loan).count(), 0
        )

    def test_reimport_replaces_existing(self):
        PropertyLoanAmortizationEntry.objects.create(
            loan=self.loan,
            date=datetime.date(2019, 1, 1),
            capital=Money(Decimal("100"), "EUR"),
            interest=Money(Decimal("100"), "EUR"),
            remaining_balance_amount=Money(Decimal("199900"), "EUR"),
        )
        csv = "date,capital,interets,capital_restant\n2020-01-01,576.64,583.33,199423.36\n"
        self._csv_upload(csv)
        entries = PropertyLoanAmortizationEntry.objects.filter(loan=self.loan)
        self.assertEqual(entries.count(), 1)
        first_entry = entries.first()
        assert first_entry is not None
        self.assertEqual(first_entry.date, datetime.date(2020, 1, 1))

    def test_semicolon_separator(self):
        csv = "date;capital;interets;capital_restant\n2020-01-01;576,64;583,33;199423,36\n"
        self._csv_upload(csv)
        self.assertEqual(
            PropertyLoanAmortizationEntry.objects.filter(loan=self.loan).count(), 1
        )


# ─── Generate view ────────────────────────────────────────────────────────────


class GenerateLoanAmortizationViewTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user("testuser2", password="pass")  # type: ignore
        self.client.force_login(self.user)
        self.prop = make_property()
        self.loan = make_standard_loan(self.prop)

    def test_generate_creates_entries(self):
        response = self.client.post(
            f"/property/{self.prop.pk}/loans/{self.loan.pk}/amortization/generate/"
        )
        self.assertEqual(response.status_code, 302)
        count = PropertyLoanAmortizationEntry.objects.filter(loan=self.loan).count()
        self.assertGreater(count, 0)
        # First entry should be before last entry (ordered by date)
        entries = PropertyLoanAmortizationEntry.objects.filter(loan=self.loan)
        first_entry = entries.first()
        last_entry = entries.last()
        assert first_entry is not None
        assert last_entry is not None
        self.assertLess(first_entry.date, last_entry.date)

    def test_generate_balance_decreases(self):
        self.client.post(
            f"/property/{self.prop.pk}/loans/{self.loan.pk}/amortization/generate/"
        )
        entries = list(PropertyLoanAmortizationEntry.objects.filter(loan=self.loan))
        self.assertGreater(
            float(entries[0].remaining_balance_amount.amount),
            float(entries[-1].remaining_balance_amount.amount),
        )


# ─── build_loan_monthly_maps() ────────────────────────────────────────────────


class BuildLoanMonthlyMapsTest(TestCase):
    def test_standard_loan_maps(self):
        interest_map, principal_map, insurance_map = build_loan_monthly_maps(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2022, 1, 1),
            original_amount=Decimal("24000"),
            monthly_payment=Decimal("1000"),
            interest_rate=Decimal("0"),
            insurance_amount=Decimal("0"),
        )
        self.assertIn((2020, 1), principal_map)
        self.assertAlmostEqual(float(principal_map[(2020, 1)]), 1000.0, delta=1.0)
        self.assertAlmostEqual(float(interest_map[(2020, 1)]), 0.0, delta=0.01)

    def test_insurance_map_populated(self):
        _, _, insurance_map = build_loan_monthly_maps(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2022, 1, 1),
            original_amount=Decimal("24000"),
            monthly_payment=Decimal("1000"),
            interest_rate=Decimal("0"),
            insurance_amount=Decimal("50"),
        )
        self.assertIn((2020, 1), insurance_map)
        self.assertAlmostEqual(float(insurance_map[(2020, 1)]), 50.0, delta=0.01)

    def test_no_payment_returns_empty(self):
        interest_map, principal_map, insurance_map = build_loan_monthly_maps(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2022, 1, 1),
            original_amount=Decimal("24000"),
            monthly_payment=None,
            interest_rate=Decimal("3.5"),
            insurance_amount=Decimal("0"),
            payment_sequence=None,
        )
        self.assertEqual(len(principal_map), 0)


# ─── Interest rounding ────────────────────────────────────────────────────────


class InterestRoundingTest(TestCase):
    def test_interest_rounded_in_balance_calculation(self):
        balance = build_loan_amortization_balance(
            original_amount=Decimal("100000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("700")] * 180,
            months_elapsed=1,
        )
        self.assertEqual(balance, Decimal("99570.83"))

    def test_interest_rounded_in_monthly_maps(self):
        interest_map, _, _ = build_loan_monthly_maps(
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Decimal("100000"),
            monthly_payment=Decimal("700"),
            interest_rate=Decimal("3.25"),
            insurance_amount=Decimal("0"),
        )
        self.assertEqual(interest_map[(2025, 1)], Decimal("270.83"))


# ─── Partial first period ─────────────────────────────────────────────────────


class PartialFirstPeriodTest(TestCase):
    def test_prorated_first_interest_in_balance(self):
        balance_with = build_loan_amortization_balance(
            original_amount=Decimal("40000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("270.59")],
            months_elapsed=1,
            disbursement_date=datetime.date(2025, 10, 13),
            first_payment_date=datetime.date(2025, 11, 10),
        )
        balance_without = build_loan_amortization_balance(
            original_amount=Decimal("40000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("270.59")],
            months_elapsed=1,
        )
        self.assertLess(float(balance_with), float(balance_without))
        self.assertAlmostEqual(float(balance_with), 39827.26, delta=1.0)

    def test_monthly_maps_start_at_first_payment_month(self):
        interest_map, _, _ = build_loan_monthly_maps(
            start_date=datetime.date(2025, 10, 13),
            end_date=datetime.date(2040, 10, 13),
            original_amount=Decimal("40000"),
            monthly_payment=Decimal("281.07"),
            interest_rate=Decimal("3.25"),
            insurance_amount=Decimal("0"),
            disbursement_date=datetime.date(2025, 10, 13),
            first_payment_date=datetime.date(2025, 11, 10),
        )
        self.assertNotIn((2025, 10), interest_map)
        self.assertIn((2025, 11), interest_map)

    def test_first_payment_date_on_model(self):
        prop = Property.objects.create(
            name="Test",
            property_type=Property.HOUSE,
            buying_value=Money(100_000, "EUR"),
            buying_date=datetime.date(2025, 10, 1),
        )
        loan = PropertyLoan.objects.create(
            property=prop,
            name="Facilimmo",
            start_date=datetime.date(2025, 10, 13),
            end_date=datetime.date(2040, 10, 13),
            original_amount=Money(Decimal("40000"), "EUR"),
            monthly_payment=Money(Decimal("281.07"), "EUR"),
            interest_rate=Decimal("3.25"),
            first_payment_date=datetime.date(2025, 11, 10),
        )
        balance_with = loan.remaining_balance(datetime.date(2025, 11, 30))
        loan.first_payment_date = None
        balance_without = loan.remaining_balance(datetime.date(2025, 11, 30))
        self.assertNotEqual(float(balance_with.amount), float(balance_without.amount))
