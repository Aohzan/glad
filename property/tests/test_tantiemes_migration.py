"""Tests for the migration of the coproperty share fields to the tantièmes."""

import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("property", "0021_lease_notice_by")]
AFTER = [("property", "0022_coproperty_tantiemes")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_old_share_fields_become_the_tantiemes():
    apps = _migrate(BEFORE)
    OldProperty = apps.get_model("property", "Property")
    common = {
        "property_type": "apartment",
        "buying_value": 0,
        "buying_date": datetime.date(2020, 1, 1),
    }
    full = OldProperty.objects.create(
        name="Full",
        coproperty_share=Decimal(250),
        shares_count=Decimal(1000),
        **common,
    )
    percent = OldProperty.objects.create(
        name="Percent", coproperty_share=Decimal("7.01"), **common
    )
    inconsistent = OldProperty.objects.create(
        name="Inconsistent",
        coproperty_share=Decimal(50),
        shares_count=Decimal(2),
        **common,
    )
    decimal_share = OldProperty.objects.create(
        name="Decimal share",
        coproperty_share=Decimal("25.50"),
        shares_count=Decimal(1000),
        **common,
    )
    small_count = OldProperty.objects.create(
        name="Small count",
        coproperty_share=Decimal("0.20"),
        shares_count=Decimal("0.4"),
        **common,
    )
    count_only = OldProperty.objects.create(
        name="Count only", shares_count=Decimal(1000), **common
    )

    apps = _migrate(AFTER)
    Property = apps.get_model("property", "Property")

    def tantiemes(pk):
        prop = Property.objects.get(pk=pk)
        return (
            prop.voting_tantiemes,
            prop.voting_tantiemes_total,
            prop.charges_tantiemes,
            prop.charges_tantiemes_total,
        )

    assert tantiemes(full.pk) == (250, 1000, 250, 1000)
    # A share alone, or above its count, is the percentage of its label.
    assert tantiemes(percent.pk) == (701, 10_000, 701, 10_000)
    assert tantiemes(inconsistent.pk) == (5000, 10_000, 5000, 10_000)
    # A share with decimals, or a count below 1, is a percentage as well.
    assert tantiemes(decimal_share.pk) == (2550, 10_000, 2550, 10_000)
    assert tantiemes(small_count.pk) == (20, 10_000, 20, 10_000)
    assert tantiemes(count_only.pk) == (None, None, None, None)

    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
