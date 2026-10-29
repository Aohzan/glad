"""Tests for the notification types of the property app."""

import datetime
from unittest.mock import patch

import pytest
from moneyed import Money

from property import notifications
from property.models import LmnpDeclarationSnapshot, Property, PropertyLedgerEntry

LMNP = {"deadline": "05-20", "days_before": 30}


@pytest.fixture
def lmnp_property():
    Property.objects.update(is_active=False)
    return Property.objects.create(
        name="Studio",
        property_type=Property.APARTMENT,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        tax_regime=Property.TaxRegime.LMNP_REEL,
    )


TAXES = {"property_tax": "10-15", "cfe": "12-15", "days_before": 15}


@pytest.mark.django_db
def test_pending_checks(lmnp_property):
    today = datetime.date.today()
    PropertyLedgerEntry.objects.create(
        property=lmnp_property,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(500, "EUR"),
        entry_date=today - datetime.timedelta(days=70),
        recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
    )
    (event,) = notifications._pending_checks({"days": 7}, today)
    assert event.key == "pending"
    assert event.url == "/property/checks/"
    assert "recurring entr" in event.title
    assert list(notifications._pending_checks({"days": 100000}, today)) == []


@pytest.mark.django_db
def test_lmnp_return_in_its_window(lmnp_property):
    with patch.object(
        notifications, "get_lmnp_checklist", return_value={"total_issues": 2}
    ):
        (event,) = notifications._lmnp_return(LMNP, datetime.date(2027, 5, 1))
    assert event.key == "2026"
    assert event.title == "LMNP tax return for 2026 due on May 20, 2027"
    assert "The checklist reports 2 issues." in event.body
    assert "not frozen yet" in event.body
    assert event.url == "/property/lmnp_accounting/?year=2026"


@pytest.mark.django_db
def test_lmnp_return_with_a_frozen_declaration(lmnp_property):
    LmnpDeclarationSnapshot.objects.create(
        fiscal_year=2026, rules_version="2026", property_names=[], data={}
    )
    with patch.object(
        notifications, "get_lmnp_checklist", return_value={"total_issues": 0}
    ):
        (event,) = notifications._lmnp_return(LMNP, datetime.date(2027, 5, 19))
    assert event.body == "On May 20, 2027 (in 1 day)"


@pytest.mark.django_db
def test_lmnp_return_outside_its_window(lmnp_property):
    assert list(notifications._lmnp_return(LMNP, datetime.date(2027, 4, 1))) == []
    assert list(notifications._lmnp_return(LMNP, datetime.date(2027, 5, 21))) == []


@pytest.mark.django_db
def test_lmnp_return_without_lmnp_property(lmnp_property):
    Property.objects.update(tax_regime=Property.TaxRegime.NONE)
    assert list(notifications._lmnp_return(LMNP, datetime.date(2027, 5, 1))) == []


@pytest.mark.django_db
def test_local_taxes(lmnp_property):
    (tax,) = notifications._local_taxes(TAXES, datetime.date(2026, 10, 5))
    assert tax.key == "property_tax:2026"
    (cfe,) = notifications._local_taxes(TAXES, datetime.date(2026, 12, 10))
    assert cfe.key == "cfe:2026"
    assert list(notifications._local_taxes(TAXES, datetime.date(2026, 7, 1))) == []


@pytest.mark.django_db
def test_local_taxes_without_property():
    Property.objects.update(is_active=False)
    assert list(notifications._local_taxes(TAXES, datetime.date(2026, 10, 5))) == []
