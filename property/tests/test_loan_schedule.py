"""Tests for PropertyLoanSchedule (prêt lisseur) functionality."""

import datetime
from decimal import Decimal

from django.test import TestCase
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyLoanSchedule
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
    # Adjust for month overflow
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


def make_smoothed_loan(prop):
    """Create a PTH LISSEUR loan with 5 tranches (240 payments total)."""
    loan = PropertyLoan.objects.create(
        property=prop,
        name="PTH LISSEUR",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(200_000, "EUR"),
        interest_rate=Decimal("3.5"),
        # monthly_payment intentionally left None for smoothed loans
    )
    schedules = [
        (1, 1, Decimal("1804.90")),
        (2, 118, Decimal("234.63")),
        (3, 1, Decimal("234.82")),
        (4, 119, Decimal("724.39")),
        (5, 1, Decimal("721.72")),
    ]
    for order, count, amount in schedules:
        PropertyLoanSchedule.objects.create(
            loan=loan,
            order=order,
            count=count,
            amount=Money(amount, "EUR"),
        )
    return loan


# ─── PropertyLoanSchedule model tests ────────────────────────────────────────


class PropertyLoanScheduleModelTest(TestCase):
    def setUp(self):
        self.prop = make_property()
        self.loan = make_smoothed_loan(self.prop)

    def test_schedule_creation(self):
        schedules = self.loan.schedules.order_by("order")
        self.assertEqual(schedules.count(), 5)
        first = schedules.first()
        self.assertEqual(first.order, 1)
        self.assertEqual(first.count, 1)
        self.assertAlmostEqual(float(first.amount.amount), 1804.90, places=2)

    def test_schedule_str(self):
        s = self.loan.schedules.get(order=1)
        result = str(s)
        self.assertIn("tranche 1", result)
        self.assertIn("1,804", result)  # formatted as €1,804.90

    def test_schedule_ordering(self):
        orders = list(self.loan.schedules.values_list("order", flat=True))
        self.assertEqual(orders, sorted(orders))

    def test_schedule_unique_together(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            PropertyLoanSchedule.objects.create(
                loan=self.loan,
                order=1,  # duplicate order
                count=5,
                amount=Money(Decimal("100.00"), "EUR"),
            )

    def test_schedule_total_payments(self):
        total = sum(s.count for s in self.loan.schedules.all())
        self.assertEqual(total, 240)  # 1+118+1+119+1


# ─── PropertyLoan.is_smoothed() ───────────────────────────────────────────────


class PropertyLoanIsSmoothedTest(TestCase):
    def setUp(self):
        self.prop = make_property()

    def test_standard_loan_not_smoothed(self):
        loan = make_standard_loan(self.prop)
        self.assertFalse(loan.is_smoothed())

    def test_smoothed_loan_is_smoothed(self):
        loan = make_smoothed_loan(self.prop)
        self.assertTrue(loan.is_smoothed())

    def test_unsaved_loan_not_smoothed(self):
        loan = PropertyLoan(
            property=self.prop,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(100_000, "EUR"),
        )
        self.assertFalse(loan.is_smoothed())


# ─── PropertyLoan.get_payment_sequence() ─────────────────────────────────────


class PropertyLoanPaymentSequenceTest(TestCase):
    def setUp(self):
        self.prop = make_property()

    def test_standard_loan_sequence(self):
        loan = make_standard_loan(self.prop, months=24)
        seq = loan.get_payment_sequence()
        self.assertEqual(len(seq), 24)
        self.assertTrue(all(v == seq[0] for v in seq))

    def test_smoothed_loan_sequence(self):
        loan = make_smoothed_loan(self.prop)
        seq = loan.get_payment_sequence()
        self.assertEqual(len(seq), 240)
        # First payment
        self.assertAlmostEqual(float(seq[0]), 1804.90, places=2)
        # Payments 2–119 (indices 1–118)
        for i in range(1, 119):
            self.assertAlmostEqual(float(seq[i]), 234.63, places=2)
        # Payment 120 (index 119)
        self.assertAlmostEqual(float(seq[119]), 234.82, places=2)
        # Payments 121–239 (indices 120–238)
        for i in range(120, 239):
            self.assertAlmostEqual(float(seq[i]), 724.39, places=2)
        # Last payment (index 239)
        self.assertAlmostEqual(float(seq[239]), 721.72, places=2)

    def test_loan_without_payment_returns_empty(self):
        loan = PropertyLoan.objects.create(
            property=self.prop,
            name="No Payment",
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2022, 1, 1),
            original_amount=Money(10_000, "EUR"),
        )
        seq = loan.get_payment_sequence()
        self.assertEqual(seq, [])


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
        # After all payments, balance should be ~0
        monthly = Decimal("1159.97")
        balance = build_loan_amortization_balance(
            original_amount=Decimal("200000"),
            interest_rate=Decimal("3.5"),
            payment_sequence=[monthly] * 240,
            months_elapsed=240,
        )
        self.assertAlmostEqual(float(balance), 0.0, delta=50.0)

    def test_zero_interest_rate(self):
        # With 0% rate, balance decreases linearly
        monthly = Decimal("1000")
        balance = build_loan_amortization_balance(
            original_amount=Decimal("24000"),
            interest_rate=Decimal("0"),
            payment_sequence=[monthly] * 24,
            months_elapsed=12,
        )
        self.assertAlmostEqual(float(balance), 12000.0, delta=1.0)

    def test_none_interest_rate(self):
        monthly = Decimal("1000")
        balance = build_loan_amortization_balance(
            original_amount=Decimal("24000"),
            interest_rate=None,
            payment_sequence=[monthly] * 24,
            months_elapsed=12,
        )
        self.assertAlmostEqual(float(balance), 12000.0, delta=1.0)

    def test_balance_never_negative(self):
        # Overpayment scenario
        balance = build_loan_amortization_balance(
            original_amount=Decimal("1000"),
            interest_rate=Decimal("3.5"),
            payment_sequence=[Decimal("10000")] * 12,
            months_elapsed=12,
        )
        self.assertEqual(balance, Decimal("0"))

    def test_smoothed_loan_balance_midpoint(self):
        """After 120 months of a smoothed loan, balance should be significantly reduced."""
        loan_amount = Decimal("200000")
        # Build sequence matching PTH LISSEUR
        seq = (
            [Decimal("1804.90")]
            + [Decimal("234.63")] * 118
            + [Decimal("234.82")]
            + [Decimal("724.39")] * 119
            + [Decimal("721.72")]
        )
        balance_120 = build_loan_amortization_balance(
            original_amount=loan_amount,
            interest_rate=Decimal("3.5"),
            payment_sequence=seq,
            months_elapsed=120,
        )
        # After 10 years of a smoothed loan with low initial payments,
        # balance should still be substantial (> 100k)
        self.assertGreater(float(balance_120), 100_000)
        self.assertLess(float(balance_120), float(loan_amount))


# ─── PropertyLoan.remaining_balance() with schedules ─────────────────────────


class PropertyLoanRemainingBalanceSmoothedTest(TestCase):
    def setUp(self):
        self.prop = make_property()
        self.loan = make_smoothed_loan(self.prop)

    def test_before_start_date(self):
        balance = self.loan.remaining_balance(datetime.date(2019, 12, 31))
        self.assertEqual(balance.amount, Decimal("200000"))

    def test_at_start_date(self):
        balance = self.loan.remaining_balance(datetime.date(2020, 1, 1))
        self.assertEqual(balance.amount, Decimal("200000"))

    def test_after_end_date(self):
        balance = self.loan.remaining_balance(datetime.date(2041, 1, 1))
        self.assertEqual(balance.amount, Decimal("0"))

    def test_midpoint_balance_less_than_original(self):
        balance = self.loan.remaining_balance(datetime.date(2030, 1, 1))
        self.assertLess(balance.amount, Decimal("200000"))
        self.assertGreater(balance.amount, Decimal("0"))

    def test_smoothed_vs_linear_approximation(self):
        """Smoothed loan balance at midpoint should differ from linear approximation."""
        midpoint = datetime.date(2030, 1, 1)
        smoothed_balance = self.loan.remaining_balance(midpoint)
        # Linear approximation would give 50% = 100,000
        # Smoothed loan with low early payments should have higher balance
        self.assertGreater(float(smoothed_balance.amount), 100_000)

    def test_currency_preserved(self):
        balance = self.loan.remaining_balance(datetime.date(2025, 1, 1))
        self.assertEqual(str(balance.currency), "EUR")


# ─── build_loan_monthly_maps() with payment_sequence ─────────────────────────


class BuildLoanMonthlyMapsSmoothedTest(TestCase):
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
        self.assertIn((2020, 1), interest_map)
        # With 0% rate, all payment is principal
        self.assertAlmostEqual(float(principal_map[(2020, 1)]), 1000.0, delta=1.0)
        self.assertAlmostEqual(float(interest_map[(2020, 1)]), 0.0, delta=0.01)

    def test_smoothed_loan_maps(self):
        seq = (
            [Decimal("1804.90")]
            + [Decimal("234.63")] * 118
            + [Decimal("234.82")]
            + [Decimal("724.39")] * 119
            + [Decimal("721.72")]
        )
        interest_map, principal_map, insurance_map = build_loan_monthly_maps(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Decimal("200000"),
            interest_rate=Decimal("3.5"),
            insurance_amount=Decimal("0"),
            payment_sequence=seq,
        )
        # First month: high payment
        self.assertIn((2020, 1), principal_map)
        # Second month: low payment (234.63)
        self.assertIn((2020, 2), principal_map)
        # Total months should be 240
        self.assertLessEqual(len(principal_map), 240)

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

    def test_no_payment_no_sequence_returns_empty(self):
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

    def test_payment_sequence_takes_precedence(self):
        """When payment_sequence is provided, monthly_payment is ignored."""
        seq = [Decimal("500")] * 24
        _, principal_map, _ = build_loan_monthly_maps(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2022, 1, 1),
            original_amount=Decimal("12000"),
            monthly_payment=Decimal("1000"),  # should be ignored
            interest_rate=Decimal("0"),
            insurance_amount=Decimal("0"),
            payment_sequence=seq,
        )
        # With 0% rate and 500/month, principal = 500
        self.assertAlmostEqual(float(principal_map[(2020, 1)]), 500.0, delta=1.0)


# ─── PropertyLoan.compute_monthly_payment() with schedules ───────────────────


class PropertyLoanComputeMonthlyPaymentSmoothedTest(TestCase):
    def setUp(self):
        self.prop = make_property()

    def test_compute_does_nothing_for_smoothed_loan(self):
        loan = make_smoothed_loan(self.prop)
        original_payment = loan.monthly_payment
        loan.compute_monthly_payment()
        self.assertEqual(loan.monthly_payment, original_payment)

    def test_compute_works_for_standard_loan(self):
        loan = PropertyLoan(
            property=self.prop,
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(200_000, "EUR"),
            interest_rate=Decimal("3.5"),
        )
        loan.compute_monthly_payment()
        self.assertIsNotNone(loan.monthly_payment)
        self.assertAlmostEqual(float(loan.monthly_payment.amount), 1159.97, delta=1.0)


# ─── PropertyLoan.taeg_rate() with schedules ─────────────────────────────────


class PropertyLoanTaegSmoothedTest(TestCase):
    def setUp(self):
        self.prop = make_property()

    def test_taeg_returns_zero_for_smoothed_loan(self):
        loan = make_smoothed_loan(self.prop)
        self.assertEqual(loan.taeg_rate(), Decimal("0.0"))

    def test_taeg_works_for_standard_loan(self):
        loan = make_standard_loan(self.prop)
        taeg = loan.taeg_rate()
        self.assertGreater(taeg, Decimal("0"))


# ─── Property.total_remaining_loans_at_date() with smoothed loans ────────────


class PropertyTotalRemainingLoansSmoothedTest(TestCase):
    def setUp(self):
        self.prop = make_property()

    def test_total_remaining_with_smoothed_loan(self):
        make_smoothed_loan(self.prop)
        total = self.prop.total_remaining_loans_at_date(datetime.date(2025, 1, 1))
        self.assertGreater(total.amount, Decimal("0"))
        self.assertLess(total.amount, Decimal("200000"))

    def test_total_remaining_mixed_loans(self):
        make_smoothed_loan(self.prop)
        make_standard_loan(self.prop, amount=100_000)
        total = self.prop.total_remaining_loans_at_date(datetime.date(2025, 1, 1))
        self.assertGreater(total.amount, Decimal("0"))

    def test_total_remaining_after_all_loans_end(self):
        make_smoothed_loan(self.prop)
        total = self.prop.total_remaining_loans_at_date(datetime.date(2041, 1, 1))
        self.assertEqual(total.amount, Decimal("0"))


# ─── PropertyLoanSchedule admin / str ────────────────────────────────────────


class PropertyLoanScheduleStrTest(TestCase):
    def setUp(self):
        self.prop = make_property()
        self.loan = PropertyLoan.objects.create(
            property=self.prop,
            name="Test Loan",
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Money(100_000, "EUR"),
        )

    def test_str_contains_order_and_count(self):
        s = PropertyLoanSchedule.objects.create(
            loan=self.loan,
            order=2,
            count=118,
            amount=Money(Decimal("234.63"), "EUR"),
        )
        result = str(s)
        self.assertIn("2", result)
        self.assertIn("118", result)
        self.assertIn("234", result)


# ─── Interest rounding in amortization ────────────────────────────────────────


class InterestRoundingTest(TestCase):
    """Interest must be rounded to 2 decimal places to match bank tables."""

    def test_interest_rounded_in_balance_calculation(self):
        """Each monthly interest is rounded to 2dp before computing principal."""
        # 100,000 at 3.25% for 180 months: monthly_rate = 0.0325/12
        # Month 1 interest = 100000 * 0.0325/12 = 270.8333...
        # Bank rounds to 270.83, so principal = payment - 270.83
        balance = build_loan_amortization_balance(
            original_amount=Decimal("100000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("700")] * 180,
            months_elapsed=1,
        )
        # interest = round(100000 * 3.25/100/12, 2) = 270.83
        # principal = 700 - 270.83 = 429.17
        # balance = 100000 - 429.17 = 99570.83
        self.assertEqual(balance, Decimal("99570.83"))

    def test_interest_rounded_in_monthly_maps(self):
        """Monthly interest entries in the map must be rounded to 2dp."""
        interest_map, _, _ = build_loan_monthly_maps(
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date(2040, 1, 1),
            original_amount=Decimal("100000"),
            monthly_payment=Decimal("700"),
            interest_rate=Decimal("3.25"),
            insurance_amount=Decimal("0"),
        )
        jan_interest = interest_map[(2025, 1)]
        # 100000 * 3.25/100/12 = 270.8333... rounded to 270.83
        self.assertEqual(jan_interest, Decimal("270.83"))

    def test_rounding_prevents_drift_over_many_months(self):
        """Balance after N months with rounding must not drift from exact bank value."""
        # Use real Angers bank data: 40000 at 3.25%, 180 months
        # Row 1 (2025-11-10): payment=270.59, interest=97.85, principal=172.74 → remaining=39827.26
        # Row 2 (2025-12-10): payment=281.07, interest=107.87, principal=173.20 → remaining=39654.06
        seq = [Decimal("270.59"), Decimal("281.07")]
        balance = build_loan_amortization_balance(
            original_amount=Decimal("40000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=seq,
            months_elapsed=2,
            disbursement_date=datetime.date(2025, 10, 13),
            first_payment_date=datetime.date(2025, 11, 10),
        )
        # Bank shows 39,654.06 after 2 payments
        self.assertAlmostEqual(float(balance), 39654.06, delta=2.0)


# ─── Partial first period (first_payment_date) ────────────────────────────────


class PartialFirstPeriodTest(TestCase):
    """When first_payment_date differs from start_date, the first month's
    interest must be computed proportionally (days / 365).
    """

    def test_prorated_first_interest_in_balance(self):
        """First month interest uses monthly_rate × days/days_in_month convention."""
        # Disbursement: 2025-10-13, first payment: 2025-11-10 → 28 days, October has 31 days
        # interest₁ = 40000 × (3.25/100/12) × (28/31) = 97.85
        balance_with_prorate = build_loan_amortization_balance(
            original_amount=Decimal("40000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("270.59")],
            months_elapsed=1,
            disbursement_date=datetime.date(2025, 10, 13),
            first_payment_date=datetime.date(2025, 11, 10),
        )
        balance_without_prorate = build_loan_amortization_balance(
            original_amount=Decimal("40000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("270.59")],
            months_elapsed=1,
        )
        # With prorate, less interest → more principal → lower remaining balance
        self.assertLess(float(balance_with_prorate), float(balance_without_prorate))
        # Bank shows 39,827.26 after first payment
        self.assertAlmostEqual(float(balance_with_prorate), 39827.26, delta=1.0)

    def test_prorated_first_interest_value(self):
        """Verify the actual prorated interest amount: 97.85€ for 28 days in October."""
        # interest = 40000 × (3.25/100/12) × (28/31) = 97.848... → rounds to 97.85
        # principal = 270.59 - 97.85 = 172.74
        # balance = 40000 - 172.74 = 39827.26
        balance = build_loan_amortization_balance(
            original_amount=Decimal("40000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("270.59")],
            months_elapsed=1,
            disbursement_date=datetime.date(2025, 10, 13),
            first_payment_date=datetime.date(2025, 11, 10),
        )
        self.assertEqual(balance, Decimal("39827.26"))

    def test_no_prorate_when_no_first_payment_date(self):
        """Without first_payment_date, behaves as before (full monthly rate)."""
        balance = build_loan_amortization_balance(
            original_amount=Decimal("40000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("281.07")],
            months_elapsed=1,
        )
        # interest = round(40000 * 3.25/100/12, 2) = 108.33
        # principal = 281.07 - 108.33 = 172.74
        # balance = 40000 - 172.74 = 39827.26
        self.assertAlmostEqual(float(balance), 39827.26, delta=0.5)

    def test_monthly_maps_start_at_first_payment_month(self):
        """When first_payment_date is provided, the map keys start from that month."""
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
        # October must NOT be in the map — first payment is November
        self.assertNotIn((2025, 10), interest_map)
        self.assertIn((2025, 11), interest_map)

    def test_monthly_maps_prorated_first_interest(self):
        """The first month in the map uses monthly_rate × days/days_in_month."""
        interest_map, _, _ = build_loan_monthly_maps(
            start_date=datetime.date(2025, 10, 13),
            end_date=datetime.date(2040, 10, 13),
            original_amount=Decimal("40000"),
            monthly_payment=Decimal("270.59"),
            interest_rate=Decimal("3.25"),
            insurance_amount=Decimal("0"),
            disbursement_date=datetime.date(2025, 10, 13),
            first_payment_date=datetime.date(2025, 11, 10),
        )
        nov_interest = interest_map.get((2025, 11), Decimal("0"))
        # 40000 × (3.25/100/12) × (28/31) = 97.85 (not 108.33 for a full month)
        self.assertEqual(nov_interest, Decimal("97.85"))
        # Full-month interest would be 108.33 — ensure we're clearly less
        self.assertLess(float(nov_interest), 105.0)

    def test_same_date_no_prorate(self):
        """When disbursement_date == first_payment_date, use standard monthly rate."""
        balance = build_loan_amortization_balance(
            original_amount=Decimal("40000"),
            interest_rate=Decimal("3.25"),
            payment_sequence=[Decimal("281.07")],
            months_elapsed=1,
            disbursement_date=datetime.date(2025, 11, 10),
            first_payment_date=datetime.date(2025, 11, 10),
        )
        # No prorate: interest = round(40000 * 3.25/100/12, 2) = 108.33
        self.assertAlmostEqual(float(balance), 39827.26, delta=0.5)

    def test_first_payment_date_on_model(self):
        """PropertyLoan.remaining_balance() uses first_payment_date when set."""
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
        # With first_payment_date set, remaining balance after 1 month should
        # reflect the prorated first period
        balance_with = loan.remaining_balance(datetime.date(2025, 11, 30))
        # Without first_payment_date
        loan.first_payment_date = None
        balance_without = loan.remaining_balance(datetime.date(2025, 11, 30))
        # With prorated first period, slightly different balance
        self.assertNotEqual(float(balance_with.amount), float(balance_without.amount))
