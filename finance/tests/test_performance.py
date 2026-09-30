"""Tests for the money-weighted performance (XIRR, real return, benchmark)."""

import datetime
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from moneyed import Money

from base.models import EconomicIndex, EconomicIndexValue
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountType,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountType,
    SavingAccountValue,
)
from finance.services import performance
from finance.services.market_data import HistoricalPricePoint, MarketDataError
from finance.services.performance import (
    account_cash_flows,
    account_performance,
    benchmark_xirr,
    real_cash_flows,
    xirr,
)

D = datetime.date
TODAY = datetime.date.today()


class TestXirr:
    def test_one_year(self):
        rate = xirr([(D(2024, 1, 1), Decimal(-1000)), (D(2025, 1, 1), Decimal(1100))])
        assert rate == pytest.approx(0.0997, abs=1e-3)  # 366 days in 2024

    def test_deposit_during_the_year(self):
        flows = [
            (D(2023, 1, 1), Decimal(-1000)),
            (D(2023, 7, 2), Decimal(-1000)),
            (D(2024, 1, 1), Decimal(2150)),
        ]
        rate = xirr(flows)
        assert rate is not None
        # 150 € earned on 1000 € for a year and 1000 € for half a year.
        assert 0.09 < rate < 0.11

    def test_loss(self):
        rate = xirr([(D(2023, 1, 1), Decimal(-1000)), (D(2024, 1, 1), Decimal(500))])
        assert rate == pytest.approx(-0.5, abs=1e-3)

    @pytest.mark.parametrize(
        "flows",
        [
            [],
            [(D(2024, 1, 1), Decimal(-1000)), (D(2024, 2, 1), Decimal(1100))],
            [(D(2023, 1, 1), Decimal(-1000)), (D(2024, 1, 1), Decimal(-1))],
            [(D(2023, 1, 1), Decimal(0)), (D(2024, 1, 1), Decimal(0))],
        ],
    )
    def test_not_computable(self, flows):
        assert xirr(flows) is None

    def test_no_root(self):
        # NPV = 100 - 300x + 300x² with x = (1 + r)^-0.5 is always positive.
        flows = [
            (D(2023, 1, 1), Decimal(100)),
            (D(2023, 7, 2), Decimal(-300)),
            (D(2024, 1, 1), Decimal(300)),
        ]
        assert xirr(flows) is None


def _cpi(year, month, value):
    return EconomicIndexValue.objects.create(
        index=EconomicIndex.CPI, period=D(year, month, 1), value=Decimal(value)
    )


@pytest.fixture(autouse=True)
def _clean(request):
    cache.clear()
    if request.node.get_closest_marker("django_db"):
        EconomicIndexValue.objects.all().delete()


@pytest.mark.django_db
class TestRealFlows:
    def test_deflated_to_last_date(self):
        _cpi(2023, 1, "100")
        _cpi(2024, 1, "110")
        flows = [(D(2023, 1, 15), Decimal(-1000)), (D(2024, 1, 15), Decimal(1100))]
        real = real_cash_flows(flows)
        assert real is not None
        assert real[0][1] == Decimal(-1100)
        assert xirr(real) == pytest.approx(0, abs=1e-6)

    def test_missing_data(self):
        flows = [(D(2023, 1, 15), Decimal(-1000)), (D(2024, 1, 15), Decimal(1100))]
        assert real_cash_flows(flows) is None
        _cpi(2025, 1, "120")
        assert real_cash_flows(flows) is None
        _cpi(2023, 6, "105")
        assert real_cash_flows(flows) is None


@pytest.fixture
def saving():
    livret = SavingAccountType.objects.get_or_create(code="LA", name="Livret A")[0]
    account = SavingAccount.objects.create(
        account_type=livret,
        name="Perf livret",
        opening_value=Money(1000, "EUR"),
        opening_date=TODAY - datetime.timedelta(days=730),
    )
    SavingAccountDeposit.objects.create(
        account=account,
        amount=Money(500, "EUR"),
        deposit_date=datetime.datetime.combine(
            TODAY - datetime.timedelta(days=365), datetime.time(9)
        ),
        update_account_value=False,
    )
    SavingAccountDeposit.objects.create(
        account=account,
        amount=Money(100, "EUR"),
        deposit_date=datetime.datetime.combine(
            TODAY + datetime.timedelta(days=5), datetime.time(9)
        ),
        update_account_value=False,
    )
    SavingAccountValue.objects.create(
        account=account,
        value=Money(1600, "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=1),
    )
    return account


@pytest.mark.django_db
class TestAccountPerformance:
    def test_cash_flows(self, saving):
        flows = account_cash_flows(saving)
        assert [amount for _day, amount in flows] == [
            Decimal(-1000),
            Decimal(-500),
            Decimal(1600),
        ]

    def test_performance(self, saving):
        result = account_performance(saving)
        assert result.xirr is not None and result.xirr > 0
        assert result.xirr_percent == pytest.approx(result.xirr * 100)
        assert result.real_xirr is None
        assert result.real_xirr_percent is None

    def test_real_performance(self, saving):
        _cpi(TODAY.year - 3, 1, "100")
        _cpi(TODAY.year + 1, 1, "200")
        result = account_performance(saving)
        assert result.real_xirr == pytest.approx(result.xirr, abs=1e-6)

    def test_saving_detail_shows_card(self, user_client, saving):
        response = user_client.get(reverse("finance:saving_detail", args=[saving.pk]))
        assert 'id="performance-panel"' in response.content.decode()
        assert "Download the consumer price index" in response.content.decode()


def _points(*prices):
    return [
        HistoricalPricePoint(date=D(2023, month, 1), price=Decimal(price))
        for month, price in enumerate(prices, start=1)
    ]


class TestBenchmark:
    FLOWS = [
        (D(2023, 1, 10), Decimal(-1000)),
        (D(2023, 3, 10), Decimal(200)),
        (D(2024, 1, 10), Decimal(900)),
    ]

    def _patch(self, monkeypatch, points, currency="EUR"):
        calls = []

        def _fetch(symbol, start, end):
            calls.append(symbol)
            return points, currency

        monkeypatch.setattr(performance, "fetch_historical_prices", _fetch)
        return calls

    def test_simulation(self, monkeypatch):
        calls = self._patch(monkeypatch, _points(100, 100, 200))
        rate = benchmark_xirr(self.FLOWS, "CW8.PA", "EUR")
        # 10 units bought, 1 sold at 200: 9 units worth 1800 at the end.
        expected = xirr([*self.FLOWS[:2], (D(2024, 1, 10), Decimal(1800))])
        assert rate == pytest.approx(expected)
        benchmark_xirr(self.FLOWS, "CW8.PA", "EUR")
        assert calls == ["CW8.PA"]  # cached

    def test_first_flow_before_first_price(self, monkeypatch):
        self._patch(monkeypatch, _points(100, 100, 200))
        flows = [(D(2022, 12, 20), Decimal(-1000)), (D(2024, 1, 10), Decimal(1))]
        assert benchmark_xirr(flows, "X", "EUR") == pytest.approx(
            xirr([flows[0], (D(2024, 1, 10), Decimal(2000))])
        )

    def test_no_price(self, monkeypatch):
        self._patch(monkeypatch, [])
        assert benchmark_xirr(self.FLOWS, "X", "EUR") is None

    def test_no_last_price(self, monkeypatch):
        self._patch(monkeypatch, [HistoricalPricePoint(D(2025, 1, 1), Decimal(1))])
        flows = [(D(2023, 1, 10), Decimal(-1000)), (D(2024, 1, 10), Decimal(900))]
        assert benchmark_xirr(flows, "X", "EUR") is None

    def test_zero_price(self, monkeypatch):
        self._patch(monkeypatch, _points(0))
        assert benchmark_xirr(self.FLOWS, "X", "EUR") is None

    def test_currency_mismatch(self, monkeypatch):
        self._patch(monkeypatch, _points(100), currency="USD")
        with pytest.raises(MarketDataError):
            benchmark_xirr(self.FLOWS, "X", "EUR")


@pytest.fixture
def pea():
    pea_type = InvestmentAccountType.objects.get_or_create(code="PEA", name="PEA")[0]
    account = InvestmentAccount.objects.create(
        account_type=pea_type,
        name="Perf PEA",
        opening_cash_value=Money(0, "EUR"),
        opening_date=TODAY - datetime.timedelta(days=400),
        benchmark_symbol="CW8.PA",
    )
    InvestmentAccountDeposit.objects.create(
        account=account,
        amount=Money(1000, "EUR"),
        deposit_date=TODAY - datetime.timedelta(days=400),
        update_account_cash=False,
    )
    InvestmentAccountCash.objects.create(
        account=account, value=Money(1100, "EUR"), value_date=TODAY
    )
    return account


@pytest.mark.django_db
class TestBenchmarkApi:
    def _url(self, account):
        return reverse("finance:api_investment_benchmark", args=[account.pk])

    def test_ok(self, user_client, pea, monkeypatch):
        monkeypatch.setattr(
            performance,
            "fetch_historical_prices",
            lambda *a: (
                [
                    HistoricalPricePoint(
                        TODAY - datetime.timedelta(days=420), Decimal(10)
                    ),
                    HistoricalPricePoint(TODAY, Decimal(12)),
                ],
                "EUR",
            ),
        )
        data = user_client.get(self._url(pea)).json()
        assert data["symbol"] == "CW8.PA"
        assert data["xirr_percent"] > 15

    def test_not_computable(self, user_client, pea, monkeypatch):
        monkeypatch.setattr(
            performance, "fetch_historical_prices", lambda *a: ([], "EUR")
        )
        assert user_client.get(self._url(pea)).json()["xirr_percent"] is None

    def test_market_error(self, user_client, pea, monkeypatch):
        def _fail(*args):
            raise MarketDataError("down")

        monkeypatch.setattr(performance, "fetch_historical_prices", _fail)
        response = user_client.get(self._url(pea))
        assert response.status_code == 502

    def test_no_benchmark(self, user_client, pea):
        pea.benchmark_symbol = ""
        pea.save()
        assert user_client.get(self._url(pea)).status_code == 400

    def test_live_data_disabled(self, user_client, user, pea):
        user.profile.live_data_enabled = False
        user.profile.save()
        assert user_client.get(self._url(pea)).status_code == 403

    def test_detail_page_loads_benchmark(self, user_client, pea):
        response = user_client.get(reverse("finance:investment_detail", args=[pea.pk]))
        content = response.content.decode()
        assert 'id="benchmark-result"' in content
        assert self._url(pea) in content
