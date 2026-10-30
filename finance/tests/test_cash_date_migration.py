"""Tests for the migrations keeping one value per account and date."""

import datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("finance", "0011_holding_auto_update_and_quotes")]
AFTER = [("finance", "0012_one_cash_value_per_date")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_keeps_the_last_cash_value_entered_for_a_date():
    apps = _migrate(BEFORE)
    account = apps.get_model("finance", "InvestmentAccount").objects.create(
        account_type=apps.get_model("finance", "InvestmentAccountType").objects.create(
            name="Cash migration", code="CM"
        ),
        name="Cash migration",
        opening_date=datetime.date(2024, 1, 1),
        opening_cash_value=0,
    )
    cash = apps.get_model("finance", "InvestmentAccountCash")
    day, other_day = datetime.date(2024, 6, 1), datetime.date(2024, 7, 1)
    cash.objects.create(account=account, value_date=day, value=100)
    last = cash.objects.create(account=account, value_date=day, value=200)
    alone = cash.objects.create(account=account, value_date=other_day, value=300)
    snapshots = apps.get_model("base", "NetWorthSnapshot").objects
    for month in (5, 7):
        snapshots.create(month=datetime.date(2024, month, 1), currency="EUR")

    apps = _migrate(AFTER)
    cash = apps.get_model("finance", "InvestmentAccountCash")
    assert set(
        cash.objects.filter(account_id=account.pk).values_list("pk", flat=True)
    ) == {
        last.pk,
        alone.pk,
    }
    # The history from the cleaned date is recomputed.
    months = apps.get_model("base", "NetWorthSnapshot").objects.values_list(
        "month", flat=True
    )
    assert list(months) == [datetime.date(2024, 5, 1)]
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_keeps_the_last_saving_value_entered_for_a_day():
    apps = _migrate([("finance", "0012_one_cash_value_per_date")])
    account = apps.get_model("finance", "SavingAccount").objects.create(
        account_type=apps.get_model("finance", "SavingAccountType").objects.create(
            name="Saving migration", code="SM"
        ),
        name="Saving migration",
        opening_date=datetime.date(2024, 1, 1),
        opening_value=0,
    )
    values = apps.get_model("finance", "SavingAccountValue")
    first = values.objects.create(
        account=account, value_date=datetime.datetime(2024, 6, 1, 9), value=200
    )
    values.objects.create(
        account=account, value_date=datetime.datetime(2024, 6, 1, 18), value=100
    )
    alone = values.objects.create(
        account=account, value_date=datetime.datetime(2024, 7, 1), value=300
    )
    snapshots = apps.get_model("base", "NetWorthSnapshot").objects
    for month in (5, 7):
        snapshots.create(month=datetime.date(2024, month, 1), currency="EUR")

    apps = _migrate([("finance", "0013_one_saving_value_per_day")])
    values = apps.get_model("finance", "SavingAccountValue")
    kept = values.objects.filter(account_id=account.pk).values_list("value", flat=True)
    # The last entered, not the latest in the day.
    assert sorted(kept) == [100, 300]
    assert not values.objects.filter(pk=first.pk).exists()
    assert values.objects.filter(pk=alone.pk).exists()
    months = apps.get_model("base", "NetWorthSnapshot").objects.values_list(
        "month", flat=True
    )
    assert list(months) == [datetime.date(2024, 5, 1)]
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
