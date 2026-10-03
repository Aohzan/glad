"""Tests for the fortnight-based interest estimate of regulated savings books."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountType,
    SavingAccountValue,
)
from finance.services.interest import (
    effective_fortnight,
    estimate_account_interest,
    estimate_interest,
    fortnight_index,
    fortnight_start,
)

TODAY = datetime.date(2026, 3, 20)
RATE = Decimal("2.4")  # 2400 € earn exactly 2.40 € per fortnight


def _estimate(start="0", movements=(), today=TODAY, year=2026):
    return estimate_interest(
        start_balance=Decimal(start),
        movements=[(d, Decimal(a)) for d, a in movements],
        rate=RATE,
        year=year,
        today=today,
        currency="EUR",
    )


class TestFortnights:
    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (datetime.date(2026, 1, 1), 0),
            (datetime.date(2026, 1, 15), 0),
            (datetime.date(2026, 1, 16), 1),
            (datetime.date(2026, 2, 28), 3),
            (datetime.date(2026, 12, 31), 23),
        ],
    )
    def test_index(self, day, expected):
        assert fortnight_index(day) == expected

    def test_start(self):
        assert fortnight_start(0, 2026) == datetime.date(2026, 1, 1)
        assert fortnight_start(3, 2026) == datetime.date(2026, 2, 16)

    def test_deposit_counts_from_next_fortnight(self):
        assert effective_fortnight(datetime.date(2026, 1, 15), Decimal(1)) == 1
        assert effective_fortnight(datetime.date(2026, 12, 20), Decimal(1)) == 24

    def test_withdrawal_counts_from_current_fortnight(self):
        assert effective_fortnight(datetime.date(2026, 1, 16), Decimal(-1)) == 1


class TestEstimateInterest:
    def test_constant_balance(self):
        estimate = _estimate(start="2400")
        assert estimate.projected_year_end == Decimal("57.60")
        assert estimate.elapsed_fortnights == 5
        assert estimate.earned_to_date == Decimal("12.00")

    def test_deposit_on_15th_and_16th(self):
        assert _estimate(
            movements=[(datetime.date(2026, 1, 15), "2400")]
        ).projected_year_end == Decimal("55.20")
        assert _estimate(
            movements=[(datetime.date(2026, 1, 16), "2400")]
        ).projected_year_end == Decimal("52.80")

    def test_withdrawal_stops_interest_in_its_fortnight(self):
        estimate = _estimate(
            start="2400", movements=[(datetime.date(2026, 1, 16), "-2400")]
        )
        assert estimate.projected_year_end == Decimal("2.40")

    def test_late_december_deposit_and_other_years_are_ignored(self):
        estimate = _estimate(
            movements=[
                (datetime.date(2026, 12, 20), "2400"),
                (datetime.date(2025, 6, 1), "2400"),
            ]
        )
        assert estimate.projected_year_end == Decimal("0.00")

    def test_negative_balance_earns_nothing(self):
        estimate = _estimate(
            start="100", movements=[(datetime.date(2026, 1, 2), "-200")]
        )
        assert estimate.projected_year_end == Decimal("0.00")

    def test_past_and_future_years(self):
        assert _estimate(start="2400", year=2025).earned_to_date == Decimal("57.60")
        assert _estimate(start="2400", year=2027).earned_to_date == Decimal("0.00")


@pytest.fixture
def livret_a_type():
    return SavingAccountType.objects.get_or_create(code="LA", name="Livret A")[0]


def _account(account_type, **kwargs) -> SavingAccount:
    defaults = {
        "name": "Livret",
        "opening_value": Money(Decimal(1000), "EUR"),
        "opening_date": datetime.date(2025, 1, 1),
        "interest_rate": RATE,
    }
    defaults.update(kwargs)
    return SavingAccount.objects.create(account_type=account_type, **defaults)


@pytest.mark.django_db
class TestEstimateAccountInterest:
    def test_start_balance_and_deposits(self, livret_a_type):
        account = _account(livret_a_type)
        SavingAccountValue.objects.create(
            account=account,
            value=Money(2400, "EUR"),
            value_date=datetime.datetime(2025, 12, 31, 12),
        )
        SavingAccountDeposit.objects.create(
            account=account,
            amount=Money(2400, "EUR"),
            deposit_date=datetime.datetime(2026, 1, 10, 9),
            update_account_value=False,
        )
        estimate = estimate_account_interest(account, today=TODAY)
        assert estimate is not None
        assert estimate.projected_year_end == Decimal("112.80")

    def test_account_opened_this_year(self, livret_a_type):
        account = _account(
            livret_a_type,
            opening_value=Money(2400, "EUR"),
            opening_date=datetime.date(2026, 2, 1),
        )
        estimate = estimate_account_interest(account, today=TODAY)
        assert estimate is not None
        assert estimate.projected_year_end == Decimal("50.40")

    def test_not_applicable(self, livret_a_type):
        other_type = SavingAccountType.objects.get_or_create(code="DIV", name="DIV")[0]
        assert estimate_account_interest(_account(other_type)) is None
        assert (
            estimate_account_interest(
                _account(livret_a_type, name="No rate", interest_rate=Decimal(0))
            )
            is None
        )
        assert (
            estimate_account_interest(
                _account(livret_a_type, name="Closed", is_active=False)
            )
            is None
        )

    def test_detail_view_shows_card(self, user_client, livret_a_type):
        account = _account(livret_a_type)
        response = user_client.get(
            reverse("finance:saving_detail", kwargs={"pk": account.pk})
        )
        assert response.context["interest_estimate"] is not None
        assert 'id="interest-panel"' in response.content.decode()
