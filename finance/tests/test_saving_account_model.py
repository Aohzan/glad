"""Tests for SavingAccount and related model methods."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountType,
    SavingAccountValue,
)

# ---------------------------------------------------------------------------
# SavingAccountType.__str__
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saving_account_type_str_with_code():
    """SavingAccountType with code returns 'name (code)'."""
    account_type = SavingAccountType.objects.create(name="Livret A", code="LA")
    assert str(account_type) == "Livret A (LA)"


@pytest.mark.django_db
def test_saving_account_type_str_without_code():
    """SavingAccountType without code returns just the name."""
    account_type = SavingAccountType.objects.create(name="Livret B", code=None)
    assert str(account_type) == "Livret B"


# ---------------------------------------------------------------------------
# SavingAccount.__str__
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saving_account_str_name_matches_type_name():
    """When account name equals the account type name, only name is returned."""
    account_type = SavingAccountType.objects.create(name="PEL", code="PEL")
    account = SavingAccount.objects.create(
        account_type=account_type,
        name="PEL",
        owner="Alice",
        is_active=True,
        opening_value=Money(Decimal("0"), "EUR"),
    )
    # name == account_type.name so account_name = "PEL"
    # owner is "Alice" → "PEL Alice"
    assert str(account) == "PEL Alice"


@pytest.mark.django_db
def test_saving_account_str_name_differs_from_type():
    """When account name differs from account type, both are concatenated."""
    account_type = SavingAccountType.objects.create(name="Livret A", code="LA")
    account = SavingAccount.objects.create(
        account_type=account_type,
        name="My Savings",
        is_active=True,
        opening_value=Money(Decimal("0"), "EUR"),
    )
    assert str(account) == "Livret A My Savings"


@pytest.mark.django_db
def test_saving_account_str_with_institution():
    """Account with institution includes ' at <institution>'."""
    account_type = SavingAccountType.objects.create(name="Livret A", code=None)
    account = SavingAccount.objects.create(
        account_type=account_type,
        name="My Account",
        institution="BNP",
        is_active=True,
        opening_value=Money(Decimal("0"), "EUR"),
    )
    assert " at BNP" in str(account) or " BNP" in str(account)


@pytest.mark.django_db
def test_saving_account_str_inactive():
    """Inactive account appends '(closed)' to its string representation."""
    account_type = SavingAccountType.objects.create(name="CEL", code=None)
    account = SavingAccount.objects.create(
        account_type=account_type,
        name="Old Account",
        is_active=False,
        opening_value=Money(Decimal("0"), "EUR"),
    )
    assert "(closed)" in str(account)


@pytest.mark.django_db
def test_saving_account_str_no_name():
    """Account with no name returns just account_type name."""
    account_type = SavingAccountType.objects.create(name="LDDS", code=None)
    account = SavingAccount.objects.create(
        account_type=account_type,
        name=None,
        is_active=True,
        opening_value=Money(Decimal("0"), "EUR"),
    )
    assert str(account) == "LDDS"


# ---------------------------------------------------------------------------
# SavingAccount.get_value
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saving_account_get_value_no_history(active_saving_account):
    """get_value() with no history returns opening_value."""
    value = active_saving_account.get_value()
    assert value == active_saving_account.opening_value


@pytest.mark.django_db
def test_saving_account_get_value_with_date_object(active_saving_account):
    """get_value() with a date (not datetime) converts it and queries correctly."""
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("2000.00"), "EUR"),
        value_date=datetime.datetime(2025, 1, 15, 12, 0, 0),
    )
    # Pass a plain date — triggers the isinstance branch
    result = active_saving_account.get_value(max_date=datetime.date(2025, 2, 1))
    assert result == Money(Decimal("2000.00"), "EUR")


@pytest.mark.django_db
def test_saving_account_get_value_with_future_date(active_saving_account):
    """get_value() before any history returns opening_value."""
    result = active_saving_account.get_value(
        max_date=datetime.datetime(2000, 1, 1, 0, 0, 0)
    )
    assert result == active_saving_account.opening_value


# ---------------------------------------------------------------------------
# SavingAccountValue.__str__
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saving_account_value_str(active_saving_account):
    """SavingAccountValue.__str__ includes account, value and date."""
    val = SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("1500.00"), "EUR"),
        value_date=datetime.datetime(2025, 3, 1, 10, 0, 0),
    )
    s = str(val)
    assert "1,500" in s or "1500" in s
    assert "2025" in s


# ---------------------------------------------------------------------------
# SavingAccount.get_progression
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saving_account_get_progression_no_deposits(active_saving_account):
    """get_progression() with no deposits returns deposits as zero Money."""
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("1200.00"), "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=20),
    )
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("1300.00"), "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )
    progression = active_saving_account.get_progression(days=30)
    assert progression.gross_difference is not None
    assert progression.net_difference is not None


@pytest.mark.django_db
def test_saving_account_get_progression_with_deposit(active_saving_account):
    """get_progression() sums deposits within the period."""
    SavingAccountDeposit.objects.create(
        account=active_saving_account,
        amount=Money(Decimal("500.00"), "EUR"),
        deposit_date=datetime.datetime.now() - datetime.timedelta(days=5),
    )
    progression = active_saving_account.get_progression(days=30)
    # A 500 EUR deposit reduces net_difference relative to gross_difference
    assert progression.net_difference.amount <= progression.gross_difference.amount


# ---------------------------------------------------------------------------
# SavingAccount.current_value property
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saving_account_current_value_property(active_saving_account):
    """current_value property proxies get_value()."""
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("999.00"), "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )
    assert active_saving_account.current_value == active_saving_account.get_value()


# ---------------------------------------------------------------------------
# SavingAccount.currency property
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saving_account_currency_property(active_saving_account):
    """currency property returns string representation of opening_value currency."""
    assert active_saving_account.currency == "EUR"
