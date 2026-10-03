"""Tests for the upcoming deadlines of the dashboard."""

import datetime
from decimal import Decimal

import pytest
from dateutil.relativedelta import relativedelta
from django.urls import reverse
from moneyed import Money

from base.services.deadlines import Deadline, upcoming_deadlines
from finance.models.investment_account import InvestmentAccount, InvestmentAccountType
from property.models import Lease, Property, PropertyLoan
from property.models.scpi import SCPI, SCPIInvestment

TODAY = datetime.date.today()


def _in(days: int) -> datetime.date:
    return TODAY + datetime.timedelta(days=days)


@pytest.fixture
def data(db):
    av_type = InvestmentAccountType.objects.get_or_create(code="AV", name="AV")[0]
    InvestmentAccount.objects.create(
        account_type=av_type,
        name="Deadline AV",
        opening_date=_in(10) - relativedelta(years=8),
    )
    InvestmentAccount.objects.create(
        account_type=av_type,
        name="Old AV",
        opening_date=_in(-100) - relativedelta(years=8),
    )
    prop = Property.objects.create(
        name="Deadline flat",
        property_type=Property.APARTMENT,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        dpe_rating="C",
        dpe_date=datetime.date(2021, 7, 10),
    )
    PropertyLoan.objects.create(
        property=prop,
        name="Deadline loan",
        lender="Bank",
        start_date=datetime.date(2020, 1, 1),
        end_date=_in(100),
        original_amount=Money(50000, "EUR"),
        monthly_payment=Money(500, "EUR"),
        interest_rate=Decimal("1.5"),
        insurance_rate=Decimal("0.1"),
    )
    Lease.objects.create(
        property=prop,
        last_name="Tenant",
        lease_type=Lease.LeaseType.EMPTY,
        status=Lease.Status.ACTIVE,
        start_date=_in(-10) - relativedelta(years=1),
        end_date=_in(20),
        rent_amount=Money(800, "EUR"),
    )
    banned = Property.objects.create(
        name="Deadline F house",
        property_type=Property.HOUSE,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        dpe_rating="F",
    )
    Lease.objects.create(
        property=banned,
        last_name="Other",
        lease_type=Lease.LeaseType.EMPTY,
        status=Lease.Status.ACTIVE,
        start_date=_in(-200),
        rent_amount=Money(700, "EUR"),
    )
    Property.objects.create(
        name="Deadline E empty",
        property_type=Property.HOUSE,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        dpe_rating="E",
    )
    scpi = SCPI.objects.create(name="Deadline SCPI")
    SCPIInvestment.objects.create(
        scpi=scpi,
        subscription_date=datetime.date(2020, 1, 1),
        shares_count=Decimal(10),
        unit_purchase_price=Money(200, "EUR"),
        ownership_type=SCPIInvestment.OwnershipType.BARE,
        dismemberment_start_date=datetime.date(2020, 1, 1),
        dismemberment_end_date=_in(200),
        bare_ownership_ratio=Decimal(70),
    )


def _mine(deadlines: list[Deadline]) -> list[Deadline]:
    return [d for d in deadlines if "Deadline" in d.title]


@pytest.mark.django_db
class TestUpcomingDeadlines:
    def test_collects_every_source(self, data):
        deadlines = _mine(upcoming_deadlines())
        details = {(d.title, str(d.detail)) for d in deadlines}
        assert any(t.startswith("AV Deadline AV") for t, _ in details)
        assert ("Deadline flat — Deadline loan", "End of the loan") in details
        assert ("Deadline flat — Tenant", "End of the lease") in details
        assert ("Deadline flat — Tenant", "Rent revision (IRL)") in details
        assert ("Deadline SCPI", "End of the dismemberment") in details
        # The F ban (2028) of the rented house is shown only within a year.
        f_ban = [d for d in deadlines if d.title == "Deadline F house"]
        assert all(d.date == datetime.date(2028, 1, 1) for d in f_ban)
        # A property without lease has no rental ban deadline.
        assert not [d for d in deadlines if d.title == "Deadline E empty"]
        # Milestones passed more than PAST_DAYS ago are dropped.
        assert not [d for d in deadlines if "Old AV" in d.title]
        dates = [d.date for d in deadlines]
        assert dates == sorted(dates)

    def test_dpe_expiry(self, data):
        later = datetime.date(2031, 3, 1)
        deadlines = _mine(upcoming_deadlines(today=later))
        expiry = [d for d in deadlines if str(d.detail) == "DPE expiry"]
        assert [d.date for d in expiry] == [datetime.date(2031, 7, 9)]

    def test_limit(self, data):
        assert len(upcoming_deadlines(limit=2)) == 2

    def test_levels(self):
        def deadline(days):
            return Deadline(_in(days), "t", "d", "/", "bi-x", TODAY)

        assert deadline(-3).level == "secondary"
        assert deadline(-3).days_ago == 3
        assert deadline(10).level == "warning"
        assert deadline(10).days_ago == 0
        assert deadline(90).level == "info"
        assert deadline(90).days_left == 90

    def test_dashboard_shows_deadlines(self, admin_client, data):
        response = admin_client.get(reverse("dashboard_panel_overview"))
        content = response.content.decode()
        assert 'id="deadlines"' in content
        assert "Watch list" in content

    def test_deadlines_page(self, admin_client, data):
        response = admin_client.get(reverse("deadlines"))
        assert response.status_code == 200
        upcoming = response.context["upcoming"]
        assert all(d.days_left >= 0 for d in upcoming)
        assert all(d.days_left < 0 for d in response.context["past"])
        if upcoming:
            assert str(upcoming[0].detail) in response.content.decode()

    def test_helpers(self):
        deadline = Deadline(_in(45), "t", "d", "/", "x", TODAY)
        assert deadline.months_left == 1
        assert not deadline.is_soon
        assert deadline.month == deadline.date.replace(day=1)
        assert Deadline(_in(3), "t", "d", "/", "x", TODAY).is_soon
