"""Tests for the migration of the lease tenant fields to the lease parties."""

import datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("property", "0016_lease_parties_and_rental_fields")]
AFTER = [("property", "0017_move_lease_tenants_to_parties")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_tenant_fields_become_a_tenant_party():
    apps = _migrate(BEFORE)
    Property = apps.get_model("property", "Property")
    Lease = apps.get_model("property", "Lease")
    prop = Property.objects.create(
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
    named = Lease.objects.create(
        first_name="Jean", last_name="Dupont", email="j@example.com", **common
    )
    Lease.objects.create(last_name="", **common)

    apps = _migrate(AFTER)
    LeaseParty = apps.get_model("property", "LeaseParty")
    (party,) = LeaseParty.objects.all()
    assert party.lease_id == named.pk
    assert (party.role, party.first_name, party.last_name, party.email) == (
        "tenant",
        "Jean",
        "Dupont",
        "j@example.com",
    )

    apps = _migrate(BEFORE)
    Lease = apps.get_model("property", "Lease")
    assert Lease.objects.get(pk=named.pk).last_name == "Dupont"
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
