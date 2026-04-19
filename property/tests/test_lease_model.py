"""Tests for property/models/lease.py."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import Lease, Property


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


@pytest.fixture
def lease(property_obj):
    return Lease.objects.create(
        property=property_obj,
        first_name="Jean",
        last_name="Dupont",
        email="jean.dupont@example.com",
        phone="0612345678",
        lease_type=Lease.LeaseType.FURNISHED,
        status=Lease.Status.ACTIVE,
        start_date=datetime.date(2022, 1, 1),
        rent_amount=Money(Decimal("800.00"), "EUR"),
        charges_amount=Money(Decimal("50.00"), "EUR"),
        deposit_amount=Money(Decimal("1600.00"), "EUR"),
    )


@pytest.mark.django_db
class TestLeaseModel:
    def test_name_with_first_and_last(self, lease):
        assert lease.name == "Jean Dupont"

    def test_name_with_only_last_name(self, property_obj):
        lease = Lease.objects.create(
            property=property_obj,
            first_name="",
            last_name="Martin",
            lease_type=Lease.LeaseType.FURNISHED,
            status=Lease.Status.ACTIVE,
            start_date=datetime.date(2022, 1, 1),
            rent_amount=Money(Decimal("700.00"), "EUR"),
        )
        assert lease.name == "Martin"

    def test_str_representation(self, lease):
        result = str(lease)
        assert "Jean Dupont" in result
        assert "2022-01-01" in result

    def test_str_with_only_last_name(self, property_obj):
        lease = Lease.objects.create(
            property=property_obj,
            first_name="",
            last_name="Martin",
            lease_type=Lease.LeaseType.FURNISHED,
            status=Lease.Status.ACTIVE,
            start_date=datetime.date(2022, 1, 1),
            rent_amount=Money(Decimal("700.00"), "EUR"),
        )
        result = str(lease)
        assert "Martin" in result

    def test_is_active_at_during_lease(self, lease):
        assert lease.is_active_at(datetime.date(2022, 6, 1)) is True

    def test_is_active_at_before_start(self, lease):
        assert lease.is_active_at(datetime.date(2021, 12, 31)) is False

    def test_is_active_at_on_start_date(self, lease):
        assert lease.is_active_at(datetime.date(2022, 1, 1)) is True

    def test_is_active_at_after_end_date(self, property_obj):
        lease = Lease.objects.create(
            property=property_obj,
            first_name="Marie",
            last_name="Curie",
            lease_type=Lease.LeaseType.FURNISHED,
            status=Lease.Status.ENDED,
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2022, 12, 31),
            rent_amount=Money(Decimal("800.00"), "EUR"),
        )
        assert lease.is_active_at(datetime.date(2023, 1, 1)) is False

    def test_is_active_at_on_end_date(self, property_obj):
        lease = Lease.objects.create(
            property=property_obj,
            first_name="Marie",
            last_name="Curie",
            lease_type=Lease.LeaseType.FURNISHED,
            status=Lease.Status.ENDED,
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2022, 12, 31),
            rent_amount=Money(Decimal("800.00"), "EUR"),
        )
        # end_date < date means inactive; on end_date itself it's still active
        assert lease.is_active_at(datetime.date(2022, 12, 31)) is True

    def test_is_active_at_no_end_date(self, lease):
        # No end_date means indefinitely active
        assert lease.is_active_at(datetime.date(2030, 1, 1)) is True

    def test_total_rent(self, lease):
        total = lease.total_rent()
        assert total.amount == Decimal("850.00")
        assert str(total.currency) == "EUR"

    def test_total_rent_zero_charges(self, property_obj):
        lease = Lease.objects.create(
            property=property_obj,
            first_name="Paul",
            last_name="Blanc",
            lease_type=Lease.LeaseType.EMPTY,
            status=Lease.Status.ACTIVE,
            start_date=datetime.date(2022, 1, 1),
            rent_amount=Money(Decimal("600.00"), "EUR"),
            charges_amount=Money(Decimal("0.00"), "EUR"),
        )
        total = lease.total_rent()
        assert total.amount == Decimal("600.00")

    def test_lease_type_choices(self):
        assert Lease.LeaseType.FURNISHED == "furnished"
        assert Lease.LeaseType.EMPTY == "empty"
        assert Lease.LeaseType.COMMERCIAL == "commercial"
        assert Lease.LeaseType.OTHER == "other"

    def test_status_choices(self):
        assert Lease.Status.UPCOMING == "upcoming"
        assert Lease.Status.ACTIVE == "active"
        assert Lease.Status.NOTICE_PERIOD == "notice"
        assert Lease.Status.ENDED == "ended"

    def test_periodicity_choices(self):
        assert Lease.Periodicity.MONTHLY == "monthly"
        assert Lease.Periodicity.QUARTERLY == "quarterly"

    def test_default_status_is_upcoming(self, property_obj):
        lease = Lease.objects.create(
            property=property_obj,
            last_name="Test",
            start_date=datetime.date(2025, 1, 1),
            rent_amount=Money(Decimal("500.00"), "EUR"),
        )
        assert lease.status == Lease.Status.UPCOMING

    def test_default_periodicity_is_monthly(self, property_obj):
        lease = Lease.objects.create(
            property=property_obj,
            last_name="Test",
            start_date=datetime.date(2025, 1, 1),
            rent_amount=Money(Decimal("500.00"), "EUR"),
        )
        assert lease.periodicity == Lease.Periodicity.MONTHLY

    def test_meta_ordering(self):
        assert Lease._meta.ordering == ["-start_date"]
