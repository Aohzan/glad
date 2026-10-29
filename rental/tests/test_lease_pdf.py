"""Tests for the lease PDF."""

from decimal import Decimal

import pytest

from property.models import Lease, LeaseParty
from rental.services.lease_pdf import BLANK, _area, _duration, lease_pdf
from rental.services.signature import page_count


@pytest.mark.django_db
@pytest.mark.parametrize("lease_type", [t for t, _label in Lease.LeaseType.choices])
def test_every_lease_type(lease, lease_type):
    lease.lease_type = lease_type
    content = lease_pdf(lease)
    assert content.startswith(b"%PDF")
    assert page_count(content) >= 2


@pytest.mark.django_db
def test_full_lease(lease, guarantor):
    LeaseParty.objects.create(
        lease=lease,
        first_name="Anne",
        last_name="Leroy",
        email="anne@example.com",
        birth_date="1990-02-03",
        birth_place="Lyon",
    )
    lease.refresh_from_db()
    prop = lease.property
    prop.is_tight_zone = True
    prop.floor_area = 42
    lease.charges_mode = Lease.ChargesMode.FLAT
    lease.periodicity = Lease.Periodicity.QUARTERLY
    lease.irl_reference_quarter = 2
    lease.irl_reference_value = "145.17"
    lease.notes = "Animaux acceptés."
    assert lease_pdf(lease).startswith(b"%PDF")


def test_duration():
    three_years = "3 ans"  # codespell:ignore ans
    assert _duration(Lease(lease_type=Lease.LeaseType.EMPTY)) == three_years
    assert _duration(Lease(lease_type=Lease.LeaseType.FURNISHED)) == "1 an"
    assert _duration(Lease(lease_type=Lease.LeaseType.STUDENT)) == "9 mois"
    assert _duration(Lease(lease_type=Lease.LeaseType.MOBILITY)).endswith("mois")
    assert (
        _duration(Lease(lease_type=Lease.LeaseType.EMPTY, duration_months=18))
        == "18 mois"
    )


def test_area():
    assert _area(None) == BLANK
    assert _area(Decimal("22.00")) == "22"
    assert _area(Decimal("100.00")) == "100"
    assert _area(Decimal("31.50")) == "31,5"
