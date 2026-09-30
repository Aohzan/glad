"""Tests for the monthly net worth snapshots."""

import datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from moneyed import Money

from base.models import NetWorthSnapshot
from base.services import snapshots
from base.services.snapshots import invalidate_from, month_starts, net_worth_history
from finance.models.other_asset import OtherAsset, OtherAssetValue

CURRENCY = "XAU"  # isolates the test data from any other fixture
D = datetime.date


@pytest.fixture(autouse=True)
def _no_snapshot(db):
    NetWorthSnapshot.objects.all().delete()


@pytest.fixture
def asset():
    asset = OtherAsset.objects.create(
        name="Snapshot gold",
        acquisition_date=D(2024, 1, 1),
        acquisition_value=Money(1000, CURRENCY),
    )
    OtherAssetValue.objects.create(
        asset=asset, value=Money(1500, CURRENCY), value_date=D(2024, 3, 10)
    )
    return asset


def _snapshot(month, other="1"):
    return NetWorthSnapshot.objects.create(
        month=month, currency=CURRENCY, other=Decimal(other)
    )


class TestMonthStarts:
    def test_months(self):
        assert month_starts(2, today=D(2026, 3, 15)) == [
            D(2026, 1, 1),
            D(2026, 2, 1),
            D(2026, 3, 1),
        ]


class TestHistory:
    def test_stores_past_months_only(self, asset):
        months = [D(2024, 1, 1), D(2024, 3, 1), D(2024, 4, 1)]
        history = net_worth_history(months, CURRENCY, today=D(2024, 4, 20))
        assert [h["other"] for h in history] == [
            Decimal(1000),
            Decimal(1000),
            Decimal(1500),
        ]
        stored = NetWorthSnapshot.objects.filter(currency=CURRENCY)
        assert sorted(stored.values_list("month", flat=True)) == months[:2]
        assert stored.get(month=D(2024, 1, 1)).total == Decimal(1000)
        assert "2024-01" in str(stored.get(month=D(2024, 1, 1)))

    def test_reuses_snapshots(self, asset, monkeypatch):
        _snapshot(D(2024, 1, 1), other="42")
        calls = []
        original = snapshots.compute_month
        monkeypatch.setattr(
            snapshots,
            "compute_month",
            lambda assets, month: calls.append(month) or original(assets, month),
        )
        history = net_worth_history(
            [D(2024, 1, 1), D(2024, 2, 1)], CURRENCY, today=D(2024, 4, 1)
        )
        assert history[0]["other"] == Decimal(42)
        assert calls == [D(2024, 2, 1)]

    def test_unvaluable_asset_counts_as_zero(self, asset, monkeypatch):
        def _fail(self, max_date=None):
            raise ValueError("broken")

        monkeypatch.setattr(OtherAsset, "get_value", _fail)
        history = net_worth_history([D(2024, 5, 1)], CURRENCY, today=D(2024, 4, 1))
        assert history[0]["other"] == Decimal(0)


class TestInvalidation:
    def test_invalidate_from(self):
        for month in (D(2024, 1, 1), D(2024, 2, 1), D(2024, 3, 1)):
            _snapshot(month)
        invalidate_from(datetime.datetime(2024, 2, 1, 12))
        assert list(NetWorthSnapshot.objects.values_list("month", flat=True)) == [
            D(2024, 1, 1)
        ]
        invalidate_from(None)
        assert not NetWorthSnapshot.objects.exists()

    def test_new_value_invalidates_from_its_date(self, asset):
        _snapshot(D(2024, 1, 1))
        _snapshot(D(2024, 6, 1))
        OtherAssetValue.objects.create(
            asset=asset, value=Money(1, CURRENCY), value_date=D(2024, 5, 15)
        )
        assert list(NetWorthSnapshot.objects.values_list("month", flat=True)) == [
            D(2024, 1, 1)
        ]

    def test_moved_value_invalidates_from_the_earliest_date(self, asset):
        value = asset.values.get()
        _snapshot(D(2024, 2, 1))
        _snapshot(D(2024, 4, 1))
        value.value_date = D(2024, 5, 1)
        value.save()
        assert list(NetWorthSnapshot.objects.values_list("month", flat=True)) == [
            D(2024, 2, 1)
        ]

    def test_deleted_value(self, asset):
        _snapshot(D(2024, 2, 1))
        _snapshot(D(2024, 4, 1))
        asset.values.get().delete()
        assert NetWorthSnapshot.objects.count() == 1

    def test_asset_change_clears_everything(self, asset):
        _snapshot(D(2020, 1, 1))
        asset.name = "Renamed"
        asset.save()
        assert not NetWorthSnapshot.objects.exists()


class TestCommand:
    def test_rebuild(self, asset):
        _snapshot(D(1990, 1, 1))
        out = StringIO()
        call_command(
            "rebuild_net_worth_snapshots",
            "--years=1",
            f"--currency={CURRENCY}",
            stdout=out,
        )
        assert "12 snapshot(s) computed" in out.getvalue()
        assert not NetWorthSnapshot.objects.filter(month=D(1990, 1, 1)).exists()
