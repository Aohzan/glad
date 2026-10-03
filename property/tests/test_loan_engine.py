"""Tests for the amortization schedule engine, against independent references."""

import datetime
from decimal import Decimal

import pytest

from property.utils import (
    Installment,
    LoanCosts,
    build_schedule,
    count_installments,
    due_date,
    schedule_from_table,
)

D = datetime.date
DISBURSED = D(2020, 1, 15)


def _standard_loan(
    *,
    capital: Decimal = Decimal(200000),
    count: int = 240,
    disbursement_date: datetime.date = DISBURSED,
    first_payment_date: datetime.date | None = None,
    monthly_payment: Decimal | None = None,
    monthly_insurance: Decimal = Decimal(0),
    closed_on: datetime.date | None = None,
):
    """200 000 € at 3.5 % over 240 months, disbursed on 2020-01-15."""
    return build_schedule(
        capital=capital,
        annual_rate=Decimal("3.5"),
        count=count,
        disbursement_date=disbursement_date,
        first_payment_date=first_payment_date,
        monthly_payment=monthly_payment,
        monthly_insurance=monthly_insurance,
        closed_on=closed_on,
    )


def _closed_form_balance(capital, monthly_rate, payment, k):
    """Capital owed after k installments, without any rounding."""
    growth = (1 + monthly_rate) ** k
    return capital * growth - payment * (growth - 1) / monthly_rate


class TestStandardLoan:
    def test_first_installment_and_annuity(self):
        schedule = _standard_loan()
        first = schedule.installments[0]
        assert first.date == D(2020, 2, 15)
        assert first.principal == Decimal("576.59")
        assert first.interest == Decimal("583.33")
        assert first.payment == Decimal("1159.92")

    def test_repays_the_capital_in_the_given_count(self):
        schedule = _standard_loan()
        assert len(schedule) == 240
        assert schedule.total.principal == Decimal("200000.00")
        assert schedule.total.interest == Decimal("78380.66")
        assert schedule.installments[-1].balance == Decimal(0)
        # The last installment falls on the end date of the loan form.
        assert schedule.last_date == D(2040, 1, 15)
        assert {i.date.day for i in schedule} == {15}

    def test_balances_follow_the_closed_form(self):
        """The rounded schedule stays within half a cent per month of the formula."""
        schedule = _standard_loan()
        monthly_rate = Decimal("3.5") / Decimal(1200)
        for k, installment in enumerate(schedule.installments, start=1):
            exact = _closed_form_balance(
                Decimal(200000), monthly_rate, Decimal("1159.92"), k
            )
            if k < 240:
                assert abs(installment.balance - exact) <= Decimal("0.005") * k
        assert schedule.installments[119].balance == Decimal("117298.78")

    def test_insurance_on_every_installment(self):
        schedule = _standard_loan(monthly_insurance=Decimal("60.00"))
        assert {i.insurance for i in schedule} == {Decimal("60.00")}
        assert schedule.total.insurance == Decimal("14400.00")


class TestBrokenFirstPeriod:
    def test_short_first_period_lowers_the_first_interest(self):
        """10 days short at 3.65 %: 100 000 × 3.65 % × 10 / 365 = 100.00 less."""
        schedule = build_schedule(
            capital=Decimal(100000),
            annual_rate=Decimal("3.65"),
            count=240,
            disbursement_date=D(2025, 1, 15),
            first_payment_date=D(2025, 2, 5),
        )
        first, second = schedule.installments[:2]
        assert first.interest == Decimal("204.17")
        assert first.principal == Decimal("283.53")
        assert first.balance == Decimal("99716.47")
        assert second.interest == Decimal("303.30")
        assert second.principal == Decimal("284.40")
        assert schedule.last_date == D(2045, 1, 5)
        assert len(schedule) == 240
        assert schedule.total.principal == Decimal(100000)

    def test_deferred_first_payment_keeps_every_installment(self):
        """A first payment a year later pays the interest of the extra days."""
        schedule = _standard_loan(
            disbursement_date=D(2025, 1, 15), first_payment_date=D(2026, 1, 15)
        )
        assert schedule.installments[0].interest == Decimal("6988.81")
        assert len(schedule) == 240
        assert schedule.last_date == D(2045, 12, 15)
        assert schedule.total.principal == Decimal(200000)

    def test_one_month_later_is_not_a_broken_period(self):
        regular = _standard_loan()
        explicit = _standard_loan(first_payment_date=D(2020, 2, 15))
        assert explicit.installments == regular.installments

    def test_end_of_month_disbursement(self):
        """A loan disbursed on the 31st is debited on the last day of each month."""
        schedule = _standard_loan(disbursement_date=D(2025, 1, 31))
        assert [i.date for i in schedule.installments[:4]] == [
            D(2025, 2, 28),
            D(2025, 3, 31),
            D(2025, 4, 30),
            D(2025, 5, 31),
        ]
        # 28 February is one month after 31 January: no broken period.
        on_the_28th = _standard_loan(
            disbursement_date=D(2025, 1, 31), first_payment_date=D(2025, 2, 28)
        )
        assert on_the_28th.installments[0].interest == Decimal("583.33")


class TestStoredPayment:
    def test_payment_above_the_annuity_ends_the_loan_early(self):
        schedule = build_schedule(
            capital=Decimal(72000),
            annual_rate=Decimal("2.40"),
            count=96,
            disbursement_date=D(2022, 10, 3),
            first_payment_date=D(2022, 11, 3),
            monthly_payment=Decimal(870),
        )
        assert len(schedule) == 91
        assert schedule.last_date == D(2030, 5, 3)
        assert schedule.installments[-1].balance == Decimal(0)
        assert schedule.total.principal == Decimal(72000)

    def test_payment_below_the_annuity_leaves_a_larger_last_installment(self):
        schedule = _standard_loan(monthly_payment=Decimal(1100))
        assert len(schedule) == 240
        last = schedule.installments[-1]
        assert last.principal > Decimal(1100)
        assert last.balance == Decimal(0)

    def test_payment_below_the_interest_repays_nothing(self):
        schedule = _standard_loan(count=3, monthly_payment=Decimal(100))
        assert [i.principal for i in schedule.installments[:2]] == [
            Decimal(0),
            Decimal(0),
        ]
        assert schedule.installments[-1].principal == Decimal(200000)


class TestEdgeCases:
    def test_zero_rate_spreads_the_rounding_on_the_last_installment(self):
        schedule = build_schedule(
            capital=Decimal(10000),
            annual_rate=Decimal(0),
            count=3,
            disbursement_date=D(2025, 1, 1),
        )
        assert [i.principal for i in schedule] == [
            Decimal("3333.33"),
            Decimal("3333.33"),
            Decimal("3333.34"),
        ]
        assert schedule.total.interest == Decimal(0)

    def test_single_installment(self):
        schedule = _standard_loan(count=1)
        assert len(schedule) == 1
        assert schedule.installments[0].principal == Decimal(200000)

    @pytest.mark.parametrize(
        ("capital", "count"), [(Decimal(200000), 0), (Decimal(0), 240)]
    )
    def test_nothing_to_repay(self, capital, count):
        schedule = _standard_loan(capital=capital, count=count)
        assert len(schedule) == 0
        assert schedule.last_date is None
        assert schedule.total == LoanCosts()


class TestQueries:
    def test_balance_around_the_disbursement(self):
        schedule = _standard_loan()
        assert schedule.balance_at(D(2020, 1, 14)) == Decimal(0)
        assert schedule.balance_at(D(2020, 1, 15)) == Decimal(200000)
        assert schedule.balance_at(D(2020, 2, 14)) == Decimal(200000)
        assert schedule.balance_at(D(2020, 2, 15)) == Decimal("199423.41")
        assert schedule.balance_at(D(2045, 1, 1)) == Decimal(0)

    def test_paid_to_and_between(self):
        schedule = _standard_loan(monthly_insurance=Decimal(60))
        assert schedule.paid_to(D(2020, 2, 14)) == LoanCosts()
        assert schedule.paid_to(D(2020, 3, 15)) == LoanCosts(
            principal=Decimal("576.59") + Decimal("578.27"),
            interest=Decimal("583.33") + Decimal("581.65"),
            insurance=Decimal(120),
        )
        year_2021 = schedule.paid_between(D(2021, 1, 1), D(2021, 12, 31))
        assert year_2021.insurance == Decimal(720)
        assert year_2021 == sum(
            (i.costs for i in schedule if i.date.year == 2021), LoanCosts()
        )
        assert schedule.paid_between(D(2021, 6, 1), D(2021, 6, 10)) == LoanCosts()

    def test_by_month_matches_the_installments(self):
        schedule = _standard_loan(first_payment_date=D(2020, 2, 5))
        months = schedule.by_month()
        assert len(months) == 240
        assert months[(2020, 2)] == schedule.installments[0].costs
        assert sum(months.values(), LoanCosts()) == schedule.total

    def test_next_installment(self):
        schedule = _standard_loan()
        assert schedule.next_installment(D(2020, 1, 20)) == schedule.installments[0]
        assert schedule.next_installment(D(2020, 2, 15)) == schedule.installments[0]
        assert schedule.next_installment(D(2020, 2, 16)) == schedule.installments[1]
        assert schedule.next_installment(D(2040, 1, 16)) is None

    def test_closed_loan_stops_at_the_sale(self):
        schedule = _standard_loan(closed_on=D(2030, 6, 20))
        assert schedule.last_date == D(2030, 6, 15)
        assert schedule.balance_at(D(2030, 6, 20)) == schedule.installments[-1].balance
        assert schedule.balance_at(D(2030, 6, 21)) == Decimal(0)
        assert schedule.paid_to(D(2035, 1, 1)) == schedule.total


class TestScheduleFromTable:
    def test_rows_are_sorted_and_carry_the_insurance(self):
        rows = [
            (D(2020, 3, 5), Decimal("578.32"), Decimal("581.65"), Decimal("198845.04")),
            (D(2020, 2, 5), Decimal("576.64"), Decimal("583.33"), Decimal("199423.36")),
        ]
        schedule = schedule_from_table(
            capital=Decimal(200000),
            disbursement_date=D(2020, 1, 15),
            rows=rows,
            monthly_insurance=Decimal(60),
        )
        assert schedule.installments[0] == Installment(
            date=D(2020, 2, 5),
            principal=Decimal("576.64"),
            interest=Decimal("583.33"),
            insurance=Decimal(60),
            balance=Decimal("199423.36"),
        )
        assert schedule.balance_at(D(2020, 2, 1)) == Decimal(200000)
        # After the last row the table's balance stays, whatever the end date.
        assert schedule.balance_at(D(2030, 1, 1)) == Decimal("198845.04")


class TestDates:
    def test_due_date(self):
        assert due_date(D(2020, 1, 15), None, 0) == D(2020, 2, 15)
        assert due_date(D(2020, 1, 31), None, 1) == D(2020, 3, 31)
        assert due_date(D(2020, 1, 15), D(2020, 2, 5), 2) == D(2020, 4, 5)

    @pytest.mark.parametrize(
        ("first_payment_date", "end_date", "expected"),
        [
            (None, D(2040, 1, 15), 240),
            (D(2020, 2, 5), D(2040, 1, 5), 240),
            (D(2020, 3, 5), D(2040, 1, 15), 239),
            (None, D(2020, 1, 31), 0),
        ],
    )
    def test_count_installments(self, first_payment_date, end_date, expected):
        assert count_installments(D(2020, 1, 15), first_payment_date, end_date) == (
            expected
        )
