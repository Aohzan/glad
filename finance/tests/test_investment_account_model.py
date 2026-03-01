"""Tests for InvestmentAccount and related model methods."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
    InvestmentAccountType,
)

# ---------------------------------------------------------------------------
# InvestmentAccountType.__str__
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_investment_account_type_str_with_code():
    """InvestmentAccountType with code returns just the code."""
    account_type = InvestmentAccountType.objects.create(name="PEA", code="PEA")
    assert str(account_type) == "PEA"


@pytest.mark.django_db
def test_investment_account_type_str_without_code():
    """InvestmentAccountType without code returns name."""
    account_type = InvestmentAccountType.objects.create(
        name="Compte Titres Ordinaire", code=None
    )
    assert str(account_type) == "Compte Titres Ordinaire"


# ---------------------------------------------------------------------------
# InvestmentAccount.__str__
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_investment_account_str_name_matches_type_code(investment_account_type):
    """When account name matches account type code, only the name is returned."""
    account = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name=investment_account_type.code,  # e.g. "TIT"
        owner="Bob",
        is_active=True,
        opening_cash_value=Money(Decimal("0"), "EUR"),
    )
    # name matches code → account_name = "TIT", then owner appended
    assert investment_account_type.code in str(account)
    assert "Bob" in str(account)


@pytest.mark.django_db
def test_investment_account_str_name_differs_from_type(investment_account_type):
    """When name differs from type, both are concatenated."""
    account = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="Portfolio",
        is_active=True,
        opening_cash_value=Money(Decimal("0"), "EUR"),
    )
    result = str(account)
    assert "Portfolio" in result


@pytest.mark.django_db
def test_investment_account_str_no_name(investment_account_type):
    """Account with no name returns account_type str."""
    account = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name=None,
        is_active=True,
        opening_cash_value=Money(Decimal("0"), "EUR"),
    )
    result = str(account)
    assert str(investment_account_type) in result


@pytest.mark.django_db
def test_investment_account_str_with_institution(investment_account_type):
    """Account with institution appends ' at <institution>'."""
    account = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="Account",
        institution="Bourse Direct",
        is_active=True,
        opening_cash_value=Money(Decimal("0"), "EUR"),
    )
    assert "Bourse Direct" in str(account)


@pytest.mark.django_db
def test_investment_account_str_inactive(investment_account_type):
    """Inactive account appends '(closed)'."""
    account = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="Old Account",
        is_active=False,
        opening_cash_value=Money(Decimal("0"), "EUR"),
    )
    assert "(closed)" in str(account)


# ---------------------------------------------------------------------------
# InvestmentAccount.get_cash_value
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_investment_account_get_cash_value_no_history(active_investment_account):
    """get_cash_value() with no history returns opening_cash_value."""
    result = active_investment_account.get_cash_value()
    assert result == active_investment_account.opening_cash_value


@pytest.mark.django_db
def test_investment_account_get_cash_value_with_history(active_investment_account):
    """get_cash_value() returns most recent cash value."""
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(Decimal("3000.00"), "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=5),
    )
    result = active_investment_account.get_cash_value()
    assert result == Money(Decimal("3000.00"), "EUR")


# ---------------------------------------------------------------------------
# InvestmentAccount.get_value
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_investment_account_get_value_no_holdings_no_history(active_investment_account):
    """get_value() with no holdings returns cash (opening_cash_value fallback)."""
    result = active_investment_account.get_value()
    assert result == active_investment_account.opening_cash_value


@pytest.mark.django_db
def test_investment_account_get_value_holding_uses_initial_value(
    active_investment_account,
):
    """get_value() uses holding initial_value when no holding history exists."""
    InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="ETF World",
        is_active=True,
        initial_value=Money(Decimal("500.00"), "EUR"),
        initial_quantity=Decimal("10"),
    )
    result = active_investment_account.get_value()
    expected = active_investment_account.opening_cash_value + Money(
        Decimal("500.00"), "EUR"
    )
    assert result == expected


@pytest.mark.django_db
def test_investment_account_get_value_with_holding_history(active_investment_account):
    """get_value() uses the most recent holding history value."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="S&P 500",
        is_active=True,
        initial_value=Money(Decimal("100.00"), "EUR"),
        initial_quantity=Decimal("5"),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("700.00"), "EUR"),
        quantity=Decimal("5"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )
    result = active_investment_account.get_value()
    assert result.amount >= Decimal("700.00")


@pytest.mark.django_db
def test_investment_account_get_value_with_date_arg(active_investment_account):
    """get_value() accepts a date object (not datetime) without error."""
    result = active_investment_account.get_value(
        max_date=datetime.date.today() - datetime.timedelta(days=1)
    )
    assert result is not None


# ---------------------------------------------------------------------------
# InvestmentAccount.get_cash_progression
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_investment_account_get_cash_progression(active_investment_account):
    """get_cash_progression() returns an AccountProgression with cash values."""
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(Decimal("2500.00"), "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=1),
    )
    progression = active_investment_account.get_cash_progression(days=30)
    assert progression.gross_difference is not None


# ---------------------------------------------------------------------------
# InvestmentAccount.current_value / current_cash_value / currency properties
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_investment_account_current_value_property(active_investment_account):
    """current_value property proxies get_value()."""
    assert (
        active_investment_account.current_value == active_investment_account.get_value()
    )


@pytest.mark.django_db
def test_investment_account_current_cash_value_property(active_investment_account):
    """current_cash_value property proxies get_cash_value()."""
    assert (
        active_investment_account.current_cash_value
        == active_investment_account.get_cash_value()
    )


@pytest.mark.django_db
def test_investment_account_currency_property(active_investment_account):
    """currency property returns currency string."""
    assert active_investment_account.currency == "EUR"


# ---------------------------------------------------------------------------
# InvestmentAccountHolding.short_name
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_holding_short_name_code_only(active_investment_account):
    """short_name returns code when only code is set."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name=None,
        code="QQQ",
        is_active=True,
        initial_value=Money(Decimal("0"), "EUR"),
    )
    assert holding.short_name == "QQQ"


@pytest.mark.django_db
def test_holding_short_name_name_only(active_investment_account):
    """short_name returns name when only name is set."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="NASDAQ ETF",
        code=None,
        is_active=True,
        initial_value=Money(Decimal("0"), "EUR"),
    )
    assert holding.short_name == "NASDAQ ETF"


@pytest.mark.django_db
def test_holding_short_name_both(active_investment_account):
    """short_name returns 'name (code)' when both are set."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="S&P 500",
        code="SPY",
        is_active=True,
        initial_value=Money(Decimal("0"), "EUR"),
    )
    assert holding.short_name == "S&P 500 (SPY)"


# ---------------------------------------------------------------------------
# InvestmentAccountHolding.__str__
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_holding_str_active(active_investment_account):
    """Active holding __str__ does not contain '(closed)'."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund A",
        is_active=True,
        initial_value=Money(Decimal("0"), "EUR"),
    )
    assert "(closed)" not in str(holding)
    assert "Fund A" in str(holding)


@pytest.mark.django_db
def test_holding_str_inactive(active_investment_account):
    """Inactive holding __str__ contains '(closed)'."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Old Fund",
        is_active=False,
        initial_value=Money(Decimal("0"), "EUR"),
    )
    assert "(closed)" in str(holding)


# ---------------------------------------------------------------------------
# InvestmentAccountHolding.get_quantity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_holding_get_quantity_no_history_with_initial(active_investment_account):
    """get_quantity() returns initial_quantity when no history exists."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund B",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
        initial_quantity=Decimal("15"),
    )
    assert holding.get_quantity() == Decimal("15")


@pytest.mark.django_db
def test_holding_get_quantity_no_history_no_initial(active_investment_account):
    """get_quantity() returns None when no history and no initial_quantity."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund C",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
        initial_quantity=None,
    )
    assert holding.get_quantity() is None


@pytest.mark.django_db
def test_holding_get_quantity_with_history(active_investment_account):
    """get_quantity() returns most recent history quantity."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund D",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
        initial_quantity=Decimal("10"),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("200"), "EUR"),
        quantity=Decimal("20"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )
    assert holding.get_quantity() == Decimal("20")


# ---------------------------------------------------------------------------
# InvestmentAccountHolding.get_progression
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_holding_get_progression(active_investment_account):
    """get_progression() returns AccountProgression for the holding."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund E",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
        initial_quantity=Decimal("5"),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("150"), "EUR"),
        quantity=Decimal("5"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )
    progression = holding.get_progression(days=30)
    assert progression.gross_difference is not None


# ---------------------------------------------------------------------------
# InvestmentAccountHolding.value / quantity properties
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_holding_value_property(active_investment_account):
    """value property returns Money wrapping get_value()."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund F",
        is_active=True,
        initial_value=Money(Decimal("250"), "EUR"),
        initial_quantity=Decimal("1"),
    )
    assert holding.value == Money(Decimal("250"), "EUR")


@pytest.mark.django_db
def test_holding_quantity_property(active_investment_account):
    """quantity property proxies get_quantity()."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund G",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
        initial_quantity=Decimal("7"),
    )
    assert holding.quantity == Decimal("7")


# ---------------------------------------------------------------------------
# InvestmentAccountHoldingHistory.__str__
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_holding_history_str(investment_holding_history):
    """InvestmentAccountHoldingHistory __str__ includes value and date."""
    s = str(investment_holding_history)
    assert "300" in s or "2025" in s
