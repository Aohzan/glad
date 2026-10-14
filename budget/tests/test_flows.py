"""Tests of the perspective and of the property, SCPI and account flows of a year."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from moneyed import Money

from base.models import Ownership, household_members
from base.services.ownership import flow_ratio
from budget.services.finance_flows import (
    FinanceFlows,
    Movement,
    account_year_flows,
    guess_origins,
)
from budget.services.perspective import Perspective
from budget.services.property_flows import property_year_flows, scpi_year_flows
from budget.tests.conftest import YEAR, day
from finance.models.base import DepositOrigin
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountDeposit,
    InvestmentAccountType,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountType,
)
from property.models import Property, PropertyLedgerEntry, PropertyLoan
from property.models.scpi import SCPI, SCPIDividend, SCPIInvestment

ManagementCategory = PropertyLedgerEntry.ManagementCategory
Recurrence = PropertyLedgerEntry.RecurrenceType


def _own(asset, user, share="100", right=Ownership.Right.FULL):
    return Ownership.objects.create(
        content_type=ContentType.objects.get_for_model(asset),
        object_id=asset.pk,
        user=user,
        share=Decimal(share),
        right=right,
    )


def _property(name="Flat", bought=datetime.date(2000, 1, 1), **kwargs):
    return Property.objects.create(
        name=name,
        property_type=Property.APARTMENT,
        buying_value=Money(100000, kwargs.pop("currency", "EUR")),
        buying_date=bought,
        **kwargs,
    )


def _entry(
    prop, category, amount, start, flow=None, recurrence=Recurrence.NONE, end=None
):
    income = category in PropertyLedgerEntry._INCOME_CATEGORIES
    return PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=flow
        or (
            PropertyLedgerEntry.FlowType.INCOME
            if income
            else PropertyLedgerEntry.FlowType.EXPENSE
        ),
        amount=Money(amount, "EUR"),
        entry_date=start,
        management_category=category,
        description=str(category),
        recurrence_type=recurrence,
        recurrence_end_date=end,
    )


def _flows_of(prop, perspective, year=YEAR, **kwargs):
    flows = property_year_flows(year, perspective, currency="EUR", **kwargs)
    return next((f for f in flows if f.property == prop), None)


class TestFlowRatio:
    def test_sides_of_a_dismembered_asset(self):
        rows = [
            Ownership(user_id=1, share=Decimal(100), right=Ownership.Right.USUFRUCT),
            Ownership(user_id=2, share=Decimal(100), right=Ownership.Right.BARE),
        ]
        assert flow_ratio(rows, {1}) == 1
        assert flow_ratio(rows, {2}) == 0
        assert flow_ratio(rows, {2}, capital=True) == 1
        assert flow_ratio(rows, {1}, capital=True) == 0

    def test_full_ownership_counts_on_both_sides(self):
        rows = [Ownership(user_id=1, share=Decimal(50), right=Ownership.Right.FULL)]
        assert flow_ratio(rows, {1}) == Decimal("0.5")
        assert flow_ratio(rows, {1}, capital=True) == Decimal("0.5")
        assert flow_ratio(rows, {3}) == 0


class TestPerspective:
    def test_household(self, household):
        assert household.is_household
        assert household.shared_ratio == 1
        assert household.line_ratio(None) == 1
        assert household.line_ratio(7) == 1

    def test_adult(self):
        adult = Perspective(person_id=1, members=frozenset({1, 2, 3}), adults=2)
        assert adult.shared_ratio == Decimal("0.5")
        assert adult.line_ratio(None) == Decimal("0.5")
        assert adult.line_ratio(1) == 1
        assert adult.line_ratio(2) == 0
        assert adult.asset_ratio([]) == Decimal("0.5")
        rows = [
            Ownership(user_id=1, share=Decimal(60), right=Ownership.Right.FULL),
            Ownership(user_id=2, share=Decimal(40), right=Ownership.Right.FULL),
        ]
        assert adult.asset_ratio(rows) == Decimal("0.6")

    def test_child_gets_only_their_items(self):
        child = Perspective(
            person_id=3, members=frozenset({1, 2, 3}), adults=2, person_is_child=True
        )
        assert child.shared_ratio == 0
        assert child.line_ratio(None) == 0
        assert child.line_ratio(3) == 1

    def test_household_without_adult(self):
        nobody = Perspective(person_id=1, members=frozenset({1}), adults=0)
        assert nobody.shared_ratio == 0

    @pytest.mark.django_db
    def test_build(self, admin_user, user, django_user_model):
        child = django_user_model.objects.create_user(username="kid")
        child.profile.is_child = True
        child.profile.save()
        members = list(household_members())
        whole = Perspective.build()
        assert whole.is_household
        assert whole.adults == sum(1 for m in members if not m.profile.is_child)
        assert whole.members == frozenset(m.pk for m in members)
        assert child.pk in whole.members
        seen = Perspective.build(child)
        assert seen.person_id == child.pk
        assert seen.person_is_child


@pytest.mark.django_db
class TestPropertyFlows:
    def test_ledger_of_the_year(self, household):
        prop = _property()
        _entry(
            prop,
            ManagementCategory.RENT_COLLECTED,
            500,
            datetime.date(2000, 6, 1),
            recurrence=Recurrence.MONTHLY,
        )
        _entry(prop, ManagementCategory.PROPERTY_TAX, 900, day(10, 15))
        _entry(prop, ManagementCategory.PROPERTY_TAX, 850, day(10, 15, YEAR - 1))
        _entry(prop, ManagementCategory.DEPOSIT_IN, 1000, day(3))
        flows = _flows_of(prop, household)
        assert flows.income == {ManagementCategory.RENT_COLLECTED.value: Decimal(6000)}
        assert flows.rent == Decimal(6000)
        assert flows.expenses == {ManagementCategory.PROPERTY_TAX.value: Decimal(900)}
        assert flows.loan.total == 0

    def test_future_year_projects_recurring_entries(self, household):
        prop = _property()
        _entry(
            prop,
            ManagementCategory.RENT_COLLECTED,
            700,
            datetime.date(2020, 1, 5),
            recurrence=Recurrence.MONTHLY,
        )
        year = datetime.date.today().year + 1
        flows = _flows_of(prop, household, year=year)
        assert flows.rent == Decimal(8400)

    def test_loan_schedule_replaces_the_ledger_loan_entries(self, household):
        prop = _property()
        PropertyLoan.objects.create(
            property=prop,
            name="Mortgage",
            start_date=datetime.date(2000, 1, 1),
            end_date=datetime.date(2020, 1, 1),
            original_amount=Money(120000, "EUR"),
            interest_rate=Decimal("2.0"),
            insurance=Money(Decimal(20), "EUR"),
        )
        _entry(prop, ManagementCategory.LOAN_INTEREST, 3000, day(12))
        flows = _flows_of(prop, household)
        assert flows.expenses == {}
        assert flows.loan.insurance == Decimal(240)
        assert flows.loan.principal > 0
        assert flows.loan.interest > 0

    def test_held_only_part_of_the_year(self, household):
        sold = _property(
            "Sold",
            bought=datetime.date(1990, 1, 1),
            selling_date=day(6, 30),
            is_active=False,
        )
        _entry(
            sold,
            ManagementCategory.RENT_COLLECTED,
            400,
            datetime.date(1995, 1, 1),
            recurrence=Recurrence.MONTHLY,
        )
        assert _flows_of(sold, household).rent == Decimal(400 * 12)
        gone = _property(
            "Gone",
            bought=datetime.date(1990, 1, 1),
            selling_date=datetime.date(2000, 6, 30),
        )
        _entry(
            gone,
            ManagementCategory.RENT_COLLECTED,
            400,
            datetime.date(1995, 1, 1),
            recurrence=Recurrence.MONTHLY,
        )
        assert _flows_of(gone, household) is None
        later = _property("Later", bought=datetime.date(YEAR + 1, 1, 1))
        _entry(
            later, ManagementCategory.RENT_COLLECTED, 400, datetime.date(YEAR + 1, 1, 1)
        )
        assert _flows_of(later, household) is None

    def test_excluded_and_empty_properties(self, household):
        prop = _property()
        _entry(prop, ManagementCategory.RENT_COLLECTED, 400, day(2))
        assert _flows_of(prop, household, excluded={prop.pk}) is None
        assert _flows_of(_property("Empty"), household) is None

    def test_other_currency_is_left_out(self, household):
        prop = _property(currency="USD")
        _entry(prop, ManagementCategory.RENT_COLLECTED, 400, day(2))
        assert _flows_of(prop, household) is None

    def test_dismembered_property(self, admin_user, user):
        prop = _property()
        _own(prop, admin_user, right=Ownership.Right.USUFRUCT)
        _own(prop, user, right=Ownership.Right.BARE)
        PropertyLoan.objects.create(
            property=prop,
            name="Mortgage",
            start_date=datetime.date(2000, 1, 1),
            end_date=datetime.date(2020, 1, 1),
            original_amount=Money(120000, "EUR"),
            interest_rate=Decimal("2.0"),
        )
        _entry(prop, ManagementCategory.RENT_COLLECTED, 1000, day(2))
        members = frozenset({admin_user.pk, user.pk})
        usufructuary = Perspective(person_id=admin_user.pk, members=members, adults=2)
        bare_owner = Perspective(person_id=user.pk, members=members, adults=2)
        mine = _flows_of(prop, usufructuary)
        assert mine.rent == Decimal(1000)
        assert mine.loan.total == 0
        theirs = _flows_of(prop, bare_owner)
        assert theirs.income == {}
        assert theirs.loan.total > 0

    def test_property_held_outside_the_perspective(self, admin_user):
        prop = _property()
        _own(prop, admin_user)
        _entry(prop, ManagementCategory.RENT_COLLECTED, 1000, day(2))
        other = Perspective(
            person_id=admin_user.pk + 1000, members=frozenset({admin_user.pk}), adults=1
        )
        assert _flows_of(prop, other) is None


@pytest.mark.django_db
class TestSCPIFlows:
    def _fund(self):
        fund = SCPI.objects.create(name="Fund")
        full = SCPIInvestment.objects.create(
            scpi=fund,
            subscription_date=day(3),
            shares_count=Decimal(10),
            unit_purchase_price=Money(Decimal(200), "EUR"),
        )
        SCPIInvestment.objects.create(
            scpi=fund,
            subscription_date=datetime.date(2000, 1, 1),
            shares_count=Decimal(30),
            unit_purchase_price=Money(Decimal(130), "EUR"),
            ownership_type=SCPIInvestment.OwnershipType.BARE,
            dismemberment_start_date=datetime.date(2000, 1, 1),
            dismemberment_end_date=datetime.date(2010, 1, 1),
            bare_ownership_ratio=Decimal(65),
        )
        SCPIDividend.objects.create(
            scpi=fund, payment_date=day(7), net_amount=Money(150, "EUR")
        )
        SCPIDividend.objects.create(
            scpi=fund, payment_date=day(7, 1, YEAR - 1), net_amount=Money(99, "EUR")
        )
        return fund, full

    def _of(self, fund, perspective):
        flows = scpi_year_flows(YEAR, perspective, currency="EUR")
        return next((f for f in flows if f.scpi == fund), None)

    def test_dividends_and_subscriptions(self, household):
        fund, _full = self._fund()
        flows = self._of(fund, household)
        assert flows.dividends == Decimal(150)
        assert flows.subscriptions == Decimal(2000)

    def test_split_by_owner_of_the_receiving_shares(self, admin_user, user):
        fund, full = self._fund()
        _own(full, admin_user, share="50")
        _own(full, user, share="50")
        members = frozenset({admin_user.pk, user.pk})
        flows = self._of(
            fund, Perspective(person_id=admin_user.pk, members=members, adults=2)
        )
        assert flows.dividends == Decimal(75)
        assert flows.subscriptions == Decimal(1000)

    def test_dividends_without_receiving_shares(self):
        fund = SCPI.objects.create(name="Orphan")
        SCPIDividend.objects.create(
            scpi=fund, payment_date=day(7), net_amount=Money(80, "EUR")
        )
        adult = Perspective(person_id=1, members=frozenset({1, 2}), adults=2)
        assert self._of(fund, adult).dividends == Decimal(40)
        assert self._of(SCPI.objects.create(name="Silent"), adult) is None


def _saving(
    name="Booklet", opened=datetime.date(2000, 1, 1), opening=0, currency="EUR"
):
    kind, _created = SavingAccountType.objects.get_or_create(name="Booklet", code="BKT")
    return SavingAccount.objects.create(
        account_type=kind,
        name=name,
        opening_date=opened,
        opening_value=Money(opening, currency),
    )


def _investment(name="Broker", opened=datetime.date(2000, 1, 1), opening=0):
    kind, _created = InvestmentAccountType.objects.get_or_create(
        name="Broker", code="BRK"
    )
    return InvestmentAccount.objects.create(
        account_type=kind,
        name=name,
        opening_date=opened,
        opening_cash_value=Money(opening, "EUR"),
    )


def _deposit(account, amount, when, origin=DepositOrigin.UNKNOWN):
    if isinstance(account, SavingAccount):
        return SavingAccountDeposit.objects.create(
            account=account,
            amount=Money(amount, "EUR"),
            deposit_date=datetime.datetime.combine(when, datetime.time(9)),
            origin=origin,
        )
    return InvestmentAccountDeposit.objects.create(
        account=account, amount=Money(amount, "EUR"), deposit_date=when, origin=origin
    )


class TestGuessOrigins:
    def _movement(self, account, amount, when, origin=DepositOrigin.UNKNOWN):
        return Movement(
            account=account, day=when, amount=Decimal(amount), origin=origin
        )

    def test_matching_movements_are_a_transfer(self):
        booklet, broker, other = (
            SavingAccount(pk=1),
            InvestmentAccount(pk=1),
            SavingAccount(pk=2),
        )
        out = self._movement(booklet, -500, day(3, 1))
        far = self._movement(broker, 500, day(3, 20))
        near = self._movement(broker, 500, day(3, 4))
        same_account = self._movement(booklet, 500, day(3, 2))
        lonely = self._movement(other, 80, day(5))
        guess_origins([out, far, near, same_account, lonely])
        assert out.guessed == near.guessed == DepositOrigin.TRANSFER
        assert far.guessed == DepositOrigin.INCOME
        assert same_account.guessed == DepositOrigin.INCOME
        assert lonely.guessed == DepositOrigin.INCOME
        assert near.url.endswith("/investment/1/#deposits-panel")

    def test_pairs_with_an_explicit_transfer_only(self):
        booklet, broker = SavingAccount(pk=1), InvestmentAccount(pk=1)
        explicit = self._movement(booklet, -300, day(6), DepositOrigin.TRANSFER)
        unknown = self._movement(broker, 300, day(6, 2))
        income = self._movement(booklet, -200, day(7), DepositOrigin.INCOME)
        unmatched = self._movement(broker, 200, day(7, 2))
        guess_origins([explicit, unknown, income, unmatched])
        assert unknown.guessed == DepositOrigin.TRANSFER
        assert explicit.guessed is None
        assert explicit.effective_origin == DepositOrigin.TRANSFER
        assert unmatched.guessed == DepositOrigin.INCOME
        assert income.effective_origin == DepositOrigin.INCOME


@pytest.mark.django_db
class TestAccountFlows:
    def _of(self, account, perspective, year=YEAR):
        flows = account_year_flows(year, perspective, currency="EUR")
        return next((f for f in flows.accounts if f.account == account), None), flows

    def test_deposits_by_origin(self, household):
        account = _saving()
        _deposit(account, 300, day(2), DepositOrigin.INCOME)
        _deposit(account, -100, day(5), DepositOrigin.INCOME)
        _deposit(account, 900, day(8), DepositOrigin.TRANSFER)
        _deposit(account, 5000, day(9), DepositOrigin.EXCEPTIONAL)
        _deposit(account, -7000, day(10), DepositOrigin.EXCEPTIONAL)
        _deposit(account, 1200, day(4), DepositOrigin.EMPLOYER)
        _deposit(account, -500, day(6), DepositOrigin.EMPLOYER)
        _deposit(account, 999, datetime.date(YEAR - 1, 5, 1), DepositOrigin.INCOME)
        flows, finance = self._of(account, household)
        assert flows.amount == Decimal(200)
        assert flows.exceptional == Decimal(5000)
        assert flows.employer == Decimal(1200)
        assert flows.kind == "saving"
        assert flows.key == f"account:saving:{account.pk}"
        assert flows.url.endswith(f"/{account.pk}/")
        assert finance.guesses == []

    def test_unknown_transfer_between_accounts(self, household):
        booklet = _saving()
        broker = _investment()
        _deposit(booklet, -2000, day(12, 30))
        _deposit(broker, 2000, datetime.date(YEAR + 1, 1, 2))
        _deposit(booklet, 150, day(4))
        flows, finance = self._of(booklet, household)
        assert flows.amount == Decimal(150)
        assert [(m.amount, m.guessed) for m in finance.guesses] == [
            (Decimal(150), DepositOrigin.INCOME),
            (Decimal(-2000), DepositOrigin.TRANSFER),
        ]
        assert finance.guesses[0].url.endswith("#deposits-panel")
        assert self._of(broker, household)[0] is None
        assert self._of(broker, household, YEAR + 1)[0] is None

    def test_opening_value_is_a_deposit(self, household):
        booklet = _saving()
        broker = _investment(opened=day(4), opening=1000)
        flows, finance = self._of(broker, household)
        assert flows.amount == Decimal(1000)
        assert finance.guesses[0].opening
        assert finance.guesses[0].url.endswith(f"/investment/{broker.pk}/edit/")
        _deposit(booklet, -1000, day(4, 3))
        flows, finance = self._of(broker, household)
        assert flows is None
        assert {m.guessed for m in finance.guesses} == {DepositOrigin.TRANSFER}

    def test_opening_value_with_an_origin(self, household):
        booklet = _saving(opened=day(5), opening=300)
        booklet.opening_origin = DepositOrigin.TRANSFER
        booklet.save()
        assert self._of(booklet, household) == (None, FinanceFlows())
        booklet.opening_origin = DepositOrigin.EXCEPTIONAL
        booklet.save()
        flows, finance = self._of(booklet, household)
        assert flows.exceptional == Decimal(300)
        assert finance.guesses == []
        assert Movement(
            account=booklet, day=day(5), amount=Decimal(1), origin="income"
        ).url.endswith(f"/saving/{booklet.pk}/#deposits-panel")

    def test_accounts_outside_the_perspective(self, admin_user):
        account = _saving()
        _own(account, admin_user)
        _deposit(account, 300, day(2))
        other = Perspective(
            person_id=admin_user.pk + 1000, members=frozenset({admin_user.pk}), adults=1
        )
        flows, finance = self._of(account, other)
        assert flows is None
        assert finance.guesses == []

    def test_other_currency_and_empty_accounts(self, household):
        dollars = _saving("Dollars", opened=day(1), opening=50, currency="USD")
        quiet = _saving("Quiet", opening=50)
        euros = _saving("Euros")
        SavingAccountDeposit.objects.create(
            account=euros,
            amount=Money(40, "USD"),
            deposit_date=datetime.datetime(YEAR, 3, 1),
        )
        assert self._of(dollars, household)[0] is None
        assert self._of(quiet, household)[0] is None
        assert self._of(euros, household)[0] is None
