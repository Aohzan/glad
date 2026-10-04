"""Tests for the helpers shared by every model."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from finance.models.other_asset import OtherAsset, OtherAssetValue

D = datetime.date
DAYS = [D(2024, 2, 1), D(2024, 3, 1), D(2024, 5, 31), D(2024, 6, 1), D(2025, 1, 1)]


@pytest.fixture
def asset(db):
    asset = OtherAsset.objects.create(
        name="Latest watch",
        acquisition_date=D(2024, 1, 1),
        acquisition_value=Money(1000, "EUR"),
    )
    for day, value in [(D(2024, 3, 1), 1100), (D(2024, 6, 1), 1200)]:
        OtherAssetValue.objects.create(
            asset=asset, value=Money(value, "EUR"), value_date=day
        )
    return asset


def _latest(asset, day):
    latest = asset.latest_related("values", "value_date", day)
    return latest.value.amount if latest else None


def test_latest_related_queries_without_prefetch(asset, django_assert_num_queries):
    with django_assert_num_queries(len(DAYS)):
        found = [_latest(asset, day) for day in DAYS]

    assert found == [None, Decimal(1100), Decimal(1100), Decimal(1200), Decimal(1200)]


def test_latest_related_reads_the_prefetched_objects(asset, django_assert_num_queries):
    prefetched = OtherAsset.objects.prefetch_related("values").get(pk=asset.pk)

    with django_assert_num_queries(0):
        found = [_latest(prefetched, day) for day in DAYS]

    assert found == [_latest(asset, day) for day in DAYS]
