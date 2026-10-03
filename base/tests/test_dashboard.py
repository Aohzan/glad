"""Tests for the dashboard services, panels and number filters."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import translation
from moneyed import Money

from base.models import Ownership
from base.services import dashboard
from base.services.ownership import HolderResolver, holder_label
from base.templatetags import glad_format
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import SavingAccount, SavingAccountValue
from property.models import Property, PropertyLoan, PropertyValue
from property.models.scpi import SCPI, SCPIInvestment

TODAY = datetime.date.today()
CURRENCY = "XAU"  # isolates the test data from the shared fixtures


def _money(amount):
    return Money(amount, CURRENCY)


@pytest.fixture
def assets(saving_account_type):
    """One asset of every class, all in CURRENCY."""
    saving = SavingAccount.objects.create(
        name="Gold passbook",
        account_type=saving_account_type,
        opening_value=_money(0),
        opening_date=TODAY - datetime.timedelta(days=400),
        institution="Bank",
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=saving,
        value=_money(1000),
        value_date=datetime.datetime.combine(
            TODAY - datetime.timedelta(days=60), datetime.time()
        ),
    )
    SavingAccountValue.objects.create(
        account=saving,
        value=_money(900),
        value_date=datetime.datetime.combine(TODAY, datetime.time()),
    )
    prop = Property.objects.create(
        name="Gold flat",
        property_type=Property.APARTMENT,
        city="Lyon",
        buying_value=_money(100000),
        buying_date=TODAY - datetime.timedelta(days=800),
        is_active=True,
    )
    PropertyValue.objects.create(
        property=prop, value=_money(120000), valuation_date=TODAY
    )
    PropertyLoan.objects.create(
        property=prop,
        name="Mortgage",
        lender="Gold bank",
        start_date=TODAY - datetime.timedelta(days=700),
        end_date=TODAY + datetime.timedelta(days=3000),
        original_amount=_money(80000),
        monthly_payment=_money(500),
        insurance=_money(20),
        interest_rate=Decimal("2.0"),
    )
    scpi = SCPI.objects.create(name="Gold SCPI", management_company="Gold AM")
    SCPIInvestment.objects.create(
        scpi=scpi,
        subscription_date=TODAY - datetime.timedelta(days=200),
        shares_count=Decimal(10),
        unit_purchase_price=_money(100),
    )
    other = OtherAsset.objects.create(
        name="Gold bar",
        category=OtherAsset.Category.PRECIOUS_METALS,
        acquisition_date=TODAY - datetime.timedelta(days=100),
        acquisition_value=_money(5000),
    )
    OtherAssetValue.objects.create(asset=other, value=_money(5500), value_date=TODAY)
    return {"saving": saving, "property": prop, "scpi": scpi, "other": other}


@pytest.mark.django_db
class TestRegistry:
    def test_groups_every_class(self, assets):
        groups = dashboard.registry(CURRENCY, TODAY)
        kinds = [g.kind for g in groups]
        assert kinds == ["property", "saving", "scpi", "other"]
        saving = next(g for g in groups if g.kind == "saving")
        row = saving.rows[0]
        assert row.name == str(assets["saving"])
        assert row.sub.endswith("Bank")
        assert row.value == Decimal(900)
        assert row.old_value == Decimal(1000)
        assert row.change == Decimal(-100)
        assert row.change_pct == Decimal(-10)
        assert saving.change_pct == Decimal(-10)
        assert Decimal(0) < saving.share < Decimal(100)

    def test_property_row_is_net_of_loans(self, assets):
        groups = dashboard.registry(CURRENCY, TODAY)
        row = next(g for g in groups if g.kind == "property").rows[0]
        assert row.gross == Decimal(120000)
        assert row.gross is not None
        assert row.value < row.gross
        assert row.sub == "Lyon"

    def test_hero_adds_up(self, assets):
        groups = dashboard.registry(CURRENCY, TODAY)
        hero = dashboard.hero_summary(groups, CURRENCY, TODAY)
        assert hero.net == sum(r.value for g in groups for r in g.rows)
        assert hero.gross == hero.net + hero.debt
        assert hero.debt > 0
        assert 0 < hero.debt_ratio < 100

    def test_underwater_property_shows_its_negative_equity(self, assets):
        """The net value and the debts keep a loan above the property value."""
        prop = assets["property"]
        PropertyLoan.objects.create(
            property=prop,
            name="Works",
            start_date=TODAY - datetime.timedelta(days=10),
            end_date=TODAY + datetime.timedelta(days=3650),
            original_amount=_money(100000),
            monthly_payment=_money(900),
            interest_rate=Decimal("1.0"),
        )
        groups = dashboard.registry(CURRENCY, TODAY)
        row = next(g for g in groups if g.kind == "property").rows[0]
        owed = prop.total_remaining_loans_at_date(TODAY).amount
        assert row.gross is not None
        assert owed > row.gross
        assert row.value == row.gross - owed
        hero = dashboard.hero_summary(groups, CURRENCY, TODAY)
        assert hero.debt == owed
        assert hero.gross == hero.net + owed

    def test_empty_currency(self, db):
        groups = dashboard.registry("XPT", TODAY)
        assert groups == []
        hero = dashboard.hero_summary(groups, "XPT", TODAY)
        assert hero.net == 0
        assert hero.debt_ratio == 0
        assert hero.change_30d_pct is None
        assert hero.change_12m is None

    def test_watch_lists_drops(self, assets):
        groups = dashboard.registry(CURRENCY, TODAY)
        items = dashboard.watch_items(groups, TODAY)
        drops = [i for i in items if i.row is not None]
        assert [i.title for i in drops] == [str(assets["saving"])]
        assert all(i.deadline.days_left >= 0 for i in items if i.deadline)

    def test_liabilities(self, assets):
        loans = [
            loan for loan in dashboard.liabilities(TODAY) if loan.name == "Gold flat"
        ]
        assert len(loans) == 1
        loan = loans[0]
        assert loan.lender == "Gold bank"
        assert loan.monthly == Decimal(520)
        assert 0 < loan.repaid_pct < 100

    def test_property_flows(self, assets):
        flows = [f for f in dashboard.property_flows(TODAY) if f.name == "Gold flat"]
        assert len(flows) == 1
        assert flows[0].loan > 0
        assert flows[0].cashflow < 0

    def test_percent_helper(self):
        assert dashboard._pct(Decimal(110), Decimal(100)) == Decimal(10)
        assert dashboard._pct(Decimal(5), Decimal(0)) is None


@pytest.mark.django_db
class TestHolders:
    def test_labels(self, assets):
        resolver = HolderResolver()
        saving = assets["saving"]
        assert resolver.label(saving) == "Household"
        alice = User.objects.create(username="alice", first_name="Alice")
        bob = User.objects.create(username="bob")
        content_type = ContentType.objects.get_for_model(saving)
        Ownership.objects.create(
            content_type=content_type, object_id=saving.pk, user=alice, share=50
        )
        assert HolderResolver().label(saving) == "Alice"
        Ownership.objects.create(
            content_type=content_type, object_id=saving.pk, user=bob, share=50
        )
        assert HolderResolver().label(saving) == "Joint"

    def test_dismembered_rights(self, assets):
        alice = User.objects.create(username="alice2", first_name="Alice")
        bare = Ownership(user=alice, right=Ownership.Right.BARE, share=100)
        usufruct = Ownership(user=alice, right=Ownership.Right.USUFRUCT, share=100)
        assert holder_label([bare]) == "Alice (bare)"
        assert holder_label([usufruct]) == "Alice (usufruct)"

    def test_unknown_object(self):
        assert HolderResolver().rows(object()) == []


@pytest.mark.django_db
class TestPanels:
    def test_overview(self, admin_client, assets):
        response = admin_client.get(reverse("dashboard_panel_overview"))
        assert response.status_code == 200
        content = response.content.decode()
        for anchor in ('id="hero"', 'id="registry"', 'id="deadlines"'):
            assert anchor in content
        assert response.context["groups"]

    def test_property(self, admin_client, assets):
        response = admin_client.get(reverse("dashboard_panel_property"))
        assert response.status_code == 200
        assert "Gold bank" in response.content.decode()

    def test_default_currency(self, db):
        assert isinstance(dashboard.default_currency(), str)


class TestFormatFilters:
    def test_french(self):
        with translation.override("fr"):
            assert glad_format.money0(Decimal("24100.4"), "EUR") == "24 100 €"
            assert glad_format.signed_money0(Decimal(-3300), "EUR").startswith("−")
            assert glad_format.pct(Decimal("2.5")) == "+2,50 %"
            assert glad_format.share(Decimal("31.24")) == "31,2 %"

    def test_english(self):
        with translation.override("en"):
            assert glad_format.money0(Money(1234, "USD")) == "$1,234"
            assert glad_format.signed_money0(Decimal(16920), "EUR") == "+€16,920"
            assert glad_format.signed_money0(Decimal(0), "EUR") == "€0"
            assert glad_format.pct(Decimal("-7.6234")) == "−7.62%"
            assert glad_format.pct(Decimal(0)) == "0.00%"

    def test_empty_values(self):
        assert glad_format.money0(None) == ""
        assert glad_format.money0("not a number") == ""
        assert glad_format.signed_money0("") == ""
        assert glad_format.pct(None) == "—"
        assert glad_format.share(None) == "—"
        assert glad_format.tone(None) == ""
        assert glad_format.percent_of(5, 0) is None

    def test_tone_and_css(self):
        assert glad_format.tone(Decimal(2)) == "g-pos"
        assert glad_format.tone(Decimal(-2)) == "g-neg"
        assert glad_format.css_pct(Decimal(150)) == "100.00%"
        assert glad_format.css_pct(None, 3) == "3.00%"
        assert glad_format.percent_of(25, 200) == Decimal("12.5")

    def test_unknown_language_falls_back(self):
        with translation.override("xx"):
            assert glad_format.money0(Decimal(5), "EUR") == "€5"
