"""Tests for the migration of the lease tenant fields to the lease parties."""

import datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from property.models import Lease, Property

BEFORE = [("property", "0016_lease_parties_and_rental_fields")]
AFTER = [("property", "0017_move_lease_tenants_to_parties")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_tenant_fields_become_a_tenant_party():
    # A lease of the current schema: going back must not fail on it.
    current = Property.objects.create(
        name="Now",
        property_type="AP",
        buying_value=0,
        buying_date=datetime.date(2020, 1, 1),
    )
    Lease.objects.create(
        property=current, start_date=datetime.date(2021, 1, 1), rent_amount=500
    )
    apps = _migrate(BEFORE)
    OldProperty = apps.get_model("property", "Property")
    OldLease = apps.get_model("property", "Lease")
    prop = OldProperty.objects.create(
        name="Old",
        property_type="apartment",
        buying_value=0,
        buying_date=datetime.date(2020, 1, 1),
    )
    common = {
        "property": prop,
        "start_date": datetime.date(2021, 1, 1),
        "rent_amount": 500,
    }
    named = OldLease.objects.create(
        first_name="Jean", last_name="Dupont", email="j@example.com", **common
    )
    OldLease.objects.create(last_name="", **common)

    apps = _migrate(AFTER)
    LeaseParty = apps.get_model("property", "LeaseParty")
    (party,) = LeaseParty.objects.filter(lease_id=named.pk)
    assert party.lease_id == named.pk
    assert (party.role, party.first_name, party.last_name, party.email) == (
        "tenant",
        "Jean",
        "Dupont",
        "j@example.com",
    )

    apps = _migrate(BEFORE)
    assert (
        apps.get_model("property", "Lease").objects.get(pk=named.pk).last_name
        == "Dupont"
    )
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
