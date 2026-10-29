"""Tests for the legal rules of the residential leases."""

import datetime

import pytest
from moneyed import Money

from property.models import Lease
from rental import rules

TODAY = datetime.date(2026, 10, 1)


@pytest.mark.parametrize(
    ("lease_type", "cap"),
    [
        (Lease.LeaseType.EMPTY, Money(800, "EUR")),
        (Lease.LeaseType.FURNISHED, Money(1600, "EUR")),
        (Lease.LeaseType.STUDENT, Money(1600, "EUR")),
        (Lease.LeaseType.MOBILITY, Money(0, "EUR")),
        (Lease.LeaseType.COMMERCIAL, None),
    ],
)
def test_deposit_cap(lease_type, cap):
    lease = Lease(lease_type=lease_type, rent_amount=Money(800, "EUR"))
    assert rules.deposit_cap(lease) == cap


@pytest.mark.django_db
def test_required_diagnostics_of_an_old_building(lease):
    lease.property.construction_year = 1930
    assert rules.required_diagnostics(lease, TODAY) == [
        "Energy performance (DPE)",
        "Natural and technological risks",
        "Lead exposure (CREP)",
        "Asbestos",
        "Electricity and gas installations",
    ]


@pytest.mark.django_db
def test_required_diagnostics_of_a_recent_building(lease):
    lease.property.construction_year = 2020
    assert rules.required_diagnostics(lease, TODAY) == [
        "Energy performance (DPE)",
        "Natural and technological risks",
    ]


@pytest.mark.django_db
def test_required_diagnostics_without_construction_year(lease):
    lease.property.construction_year = None
    assert len(rules.required_diagnostics(lease, TODAY)) == 5
