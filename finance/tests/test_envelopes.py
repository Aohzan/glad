"""Tests for the French envelope rules (ceilings, milestones, liquidity)."""

import datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from moneyed import Money

from base.choices import Liquidity
from finance.envelopes import (
    DEFAULT_RULE,
    ENVELOPE_RULES,
    CeilingUsage,
    MilestoneStatus,
    get_rule,
)
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

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _saving(code: str, opening: str = "0", **kwargs) -> SavingAccount:
    return SavingAccount.objects.create(
        account_type=SavingAccountType.objects.get_or_create(code=code, name=code)[0],
        name=kwargs.pop("name", f"Test {code}"),
        opening_value=Money(Decimal(opening), "EUR"),
        **kwargs,
    )


def _investment(code: str, opening: str = "0", **kwargs) -> InvestmentAccount:
    return InvestmentAccount.objects.create(
        account_type=InvestmentAccountType.objects.get_or_create(code=code, name=code)[
            0
        ],
        name=kwargs.pop("name", f"Test {code}"),
        opening_cash_value=Money(Decimal(opening), "EUR"),
        **kwargs,
    )


class TestRules:
    def test_known_code(self):
        assert get_rule("LA").deposit_ceiling == Decimal(22950)
        assert get_rule("LA").fortnight_interest is True

    def test_unknown_code_uses_default(self):
        assert get_rule("XYZ") is DEFAULT_RULE
        assert get_rule(None) is DEFAULT_RULE
        assert DEFAULT_RULE.liquidity == Liquidity.CONDITIONAL

    def test_every_rule_code_exists_in_fixtures(self):
        codes: set[str] = set()
        for name in ("savingaccounttype", "investmentaccounttype"):
            with (FIXTURES_DIR / f"{name}.yaml").open(encoding="utf-8") as fh:
                codes |= {row["fields"]["code"] for row in yaml.safe_load(fh)}
        assert set(ENVELOPE_RULES) <= codes


class TestCeilingUsage:
    def test_remaining_and_percent(self):
        usage = CeilingUsage(Decimal(100), Decimal(25), "EUR")
        assert usage.remaining == Decimal(75)
        assert usage.percent == 25.0
        assert usage.is_reached is False

    def test_over_ceiling(self):
        usage = CeilingUsage(Decimal(100), Decimal(150), "EUR")
        assert usage.remaining == Decimal(0)
        assert usage.percent == 100.0
        assert usage.is_reached is True

    def test_zero_ceiling(self):
        assert CeilingUsage(Decimal(0), Decimal(0), "EUR").percent == 100.0


class TestMilestoneStatus:
    def test_future(self):
        status = MilestoneStatus(
            date=datetime.date.today() + datetime.timedelta(days=10),
            label="x",
            years=5,
        )
        assert status.is_reached is False
        assert status.days_left == 10

    def test_past(self):
        status = MilestoneStatus(
            date=datetime.date.today() - datetime.timedelta(days=1),
            label="x",
            years=5,
        )
        assert status.is_reached is True
        assert status.days_left == 0


@pytest.mark.django_db
class TestAccountEnvelope:
    def test_livret_a_counts_withdrawals(self):
        account = _saving("LA", opening="10000")
        now = datetime.datetime.now()
        SavingAccountDeposit.objects.create(
            account=account, amount=Money(5000, "EUR"), deposit_date=now
        )
        SavingAccountDeposit.objects.create(
            account=account,
            amount=Money(-3000, "EUR"),
            deposit_date=now - datetime.timedelta(days=1),
        )
        usage = account.ceiling_usage
        assert usage is not None
        assert usage.contributed == Decimal(12000)
        assert usage.remaining == Decimal(10950)
        assert account.liquidity == Liquidity.IMMEDIATE
        assert account.get_liquidity_display() == "Available immediately"

    def test_pea_ignores_withdrawals(self):
        account = _investment("PEA", opening="1000")
        today = datetime.date.today()
        InvestmentAccountDeposit.objects.create(
            account=account, amount=Money(2000, "EUR"), deposit_date=today
        )
        InvestmentAccountDeposit.objects.create(
            account=account,
            amount=Money(-500, "EUR"),
            deposit_date=today - datetime.timedelta(days=1),
        )
        usage = account.ceiling_usage
        assert usage is not None
        assert usage.contributed == Decimal(3000)

    def test_no_ceiling(self):
        assert _investment("CTO").ceiling_usage is None
        assert _investment("CTO").milestones == []

    def test_milestones_dated_from_opening(self):
        account = _investment("AV", opening_date=datetime.date(2020, 2, 29))
        (milestone,) = account.milestones
        assert milestone.years == 8
        assert milestone.date == datetime.date(2028, 2, 29)
        pel = _saving("PEL", opening_date=datetime.date(2015, 3, 1))
        assert [m.date.year for m in pel.milestones] == [2017, 2025, 2030]
        assert pel.milestones[0].is_reached is True


@pytest.mark.django_db
class TestEnvelopeCard:
    def test_saving_detail_shows_ceiling(self, user_client):
        account = _saving("LA", opening="22950")
        response = user_client.get(
            reverse("finance:saving_detail", kwargs={"pk": account.pk})
        )
        content = response.content.decode()
        assert 'id="envelope-panel"' in content
        assert "Ceiling reached" in content
        assert "Available immediately" in content

    def test_investment_detail_shows_milestones(self, user_client):
        account = _investment("PEA", opening_date=datetime.date(2010, 1, 1))
        response = user_client.get(
            reverse("finance:investment_detail", kwargs={"pk": account.pk})
        )
        content = response.content.decode()
        assert 'id="envelope-panel"' in content
        assert "Room left" in content
        assert "bi-check-circle-fill" in content

    def test_card_hidden_without_rules(self, user_client):
        account = _investment("CTO")
        response = user_client.get(
            reverse("finance:investment_detail", kwargs={"pk": account.pk})
        )
        assert 'id="envelope-panel"' not in response.content.decode()
