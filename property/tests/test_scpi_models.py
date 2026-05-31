"""Tests for property/models/scpi.py — SCPI, SCPISharePrice, SCPIInvestment, SCPIDividend."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from moneyed import Money

from property.models.scpi import SCPI, SCPIDividend, SCPIInvestment, SCPISharePrice

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def scpi():
    return SCPI.objects.create(
        name="Corum Eurion",
        management_company="Corum AM",
        entry_fee_rate=Decimal("8.00"),
        exit_fee_rate=Decimal("0.00"),
    )


@pytest.fixture
def scpi_with_price(scpi):
    SCPISharePrice.objects.create(
        scpi=scpi,
        date=datetime.date(2024, 1, 1),
        subscription_value=Money(Decimal("1080.00"), "EUR"),
        withdrawal_value=Money(Decimal("1020.00"), "EUR"),
    )
    return scpi


@pytest.fixture
def investment_full(scpi_with_price):
    return SCPIInvestment.objects.create(
        scpi=scpi_with_price,
        subscription_date=datetime.date(2023, 6, 1),
        shares_count=Decimal("10.0000"),
        unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
        ownership_type=SCPIInvestment.OwnershipType.FULL,
    )


@pytest.fixture
def investment_bare(scpi_with_price):
    return SCPIInvestment.objects.create(
        scpi=scpi_with_price,
        subscription_date=datetime.date(2020, 1, 1),
        shares_count=Decimal("20.0000"),
        unit_purchase_price=Money(Decimal("650.00"), "EUR"),  # 65% of 1000
        ownership_type=SCPIInvestment.OwnershipType.BARE,
        dismemberment_start_date=datetime.date(2020, 1, 1),
        dismemberment_end_date=datetime.date(2030, 1, 1),
        bare_ownership_ratio=Decimal("65.00"),
    )


@pytest.fixture
def investment_usufruct(scpi_with_price):
    return SCPIInvestment.objects.create(
        scpi=scpi_with_price,
        subscription_date=datetime.date(2020, 1, 1),
        shares_count=Decimal("20.0000"),
        unit_purchase_price=Money(Decimal("350.00"), "EUR"),  # 35% = 100-65
        ownership_type=SCPIInvestment.OwnershipType.USUFRUCT,
        dismemberment_start_date=datetime.date(2020, 1, 1),
        dismemberment_end_date=datetime.date(2030, 1, 1),
        bare_ownership_ratio=Decimal("65.00"),
    )


# ── SCPI model ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIModel:
    def test_str(self, scpi):
        assert str(scpi) == "Corum Eurion"

    def test_current_subscription_value_none_when_no_prices(self, scpi):
        assert scpi.current_subscription_value is None

    def test_current_subscription_value(self, scpi_with_price):
        assert scpi_with_price.current_subscription_value == Money(
            Decimal("1080.00"), "EUR"
        )

    def test_current_withdrawal_value(self, scpi_with_price):
        assert scpi_with_price.current_withdrawal_value == Money(
            Decimal("1020.00"), "EUR"
        )

    def test_current_withdrawal_value_falls_back_to_subscription(self):
        scpi = SCPI.objects.create(name="No Withdrawal SCPI")
        SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2024, 1, 1),
            subscription_value=Money(Decimal("500.00"), "EUR"),
        )
        # withdrawal_value not set → falls back to subscription_value
        assert scpi.current_withdrawal_value == Money(Decimal("500.00"), "EUR")

    def test_get_share_price_as_of_past_date(self, scpi):
        SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2022, 1, 1),
            subscription_value=Money(Decimal("900.00"), "EUR"),
        )
        SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2024, 1, 1),
            subscription_value=Money(Decimal("1000.00"), "EUR"),
        )
        price = scpi.get_share_price(datetime.date(2023, 6, 1))
        assert price is not None
        assert price.subscription_value.amount == Decimal("900.00")

    def test_get_share_price_returns_none_before_first_record(self, scpi):
        SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2024, 1, 1),
            subscription_value=Money(Decimal("1000.00"), "EUR"),
        )
        assert scpi.get_share_price(datetime.date(2020, 1, 1)) is None


# ── SCPISharePrice model ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPISharePrice:
    def test_str(self, scpi):
        price = SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2024, 3, 1),
            subscription_value=Money(Decimal("1080.00"), "EUR"),
        )
        assert "Corum Eurion" in str(price)
        assert "2024-03-01" in str(price)


# ── SCPIInvestment — purchase / fees ──────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIInvestmentPurchaseValue:
    def test_get_purchase_value(self, investment_full):
        # 10 shares × 1000 EUR = 10_000 EUR
        assert investment_full.get_purchase_value() == Money(Decimal("10000.00"), "EUR")

    def test_get_entry_fees(self, investment_full):
        # 10_000 × 8% = 800
        assert investment_full.get_entry_fees() == Money(Decimal("800.00"), "EUR")

    def test_get_total_invested(self, investment_full):
        # user entered 1000/share × 10 = 10_000 total (fees already included)
        assert investment_full.get_total_invested() == Money(Decimal("10000.00"), "EUR")

    def test_get_entry_fees_zero_when_no_rate(self):
        scpi = SCPI.objects.create(name="No Fee SCPI")
        inv = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("5.0000"),
            unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
        )
        assert inv.get_entry_fees() == Money(Decimal("0"), "EUR")
        assert inv.get_total_invested() == Money(Decimal("5000.00"), "EUR")


# ── SCPIInvestment — full ownership value ─────────────────────────────────────


@pytest.mark.django_db
class TestSCPIInvestmentCurrentFullValue:
    def test_get_current_full_value_with_price(self, investment_full):
        # 10 × 1080 = 10_800
        today = datetime.date(2025, 1, 1)
        assert investment_full.get_current_full_value(today) == Money(
            Decimal("10800.00"), "EUR"
        )

    def test_get_current_full_value_falls_back_to_purchase_when_no_price(self):
        scpi = SCPI.objects.create(name="No Price SCPI")
        inv = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("5.0000"),
            unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
        )
        assert inv.get_current_full_value(datetime.date(2025, 1, 1)) == Money(
            Decimal("5000.00"), "EUR"
        )


# ── SCPIInvestment — estimated value (ownership types) ────────────────────────


@pytest.mark.django_db
class TestSCPIInvestmentEstimatedValue:
    def test_full_ownership_equals_current_full_value(self, investment_full):
        today = datetime.date(2025, 1, 1)
        assert investment_full.get_estimated_value(
            today
        ) == investment_full.get_current_full_value(today)

    def test_bare_ownership_at_start_is_bare_ratio(self, investment_bare):
        # At start date: no share price before 2024 → falls back to purchase price (650/share)
        # full_value = 20 × 650 = 13_000 ; bare 65% = 8_450
        assert investment_bare.get_estimated_value(datetime.date(2020, 1, 1)) == Money(
            Decimal("8450.00"), "EUR"
        )

    def test_bare_ownership_at_end_is_full_value(self, investment_bare):
        # After end date: bare owner has 100% → 20 × 1080 = 21_600
        assert investment_bare.get_estimated_value(datetime.date(2030, 6, 1)) == Money(
            Decimal("21600.00"), "EUR"
        )

    def test_bare_ownership_midpoint_is_interpolated(self, investment_bare):
        # midpoint = 2025-01-01 (5/10 years elapsed)
        # current_pct = 65 + (100-65) × 0.5 = 65 + 17.5 = 82.5
        # full_value = 20 × 1080 = 21_600
        # estimated = 21_600 × 82.5 / 100 = 17_820
        mid = datetime.date(2025, 1, 1)
        val = investment_bare.get_estimated_value(mid)
        assert abs(float(val.amount) - 17820.0) < 5.0  # small rounding allowed

    def test_usufruct_at_start_is_usufruct_ratio(self, investment_usufruct):
        # At start: no share price before 2024 → falls back to purchase price (350/share)
        # full_value = 20 × 350 = 7_000 ; usufruct 35% = 2_450
        assert investment_usufruct.get_estimated_value(
            datetime.date(2020, 1, 1)
        ) == Money(Decimal("2450.00"), "EUR")

    def test_usufruct_at_end_is_zero(self, investment_usufruct):
        # After end date: usufruct pct = 100 - 100 = 0%
        assert investment_usufruct.get_estimated_value(
            datetime.date(2030, 6, 1)
        ) == Money(Decimal("0.00"), "EUR")

    def test_bare_ownership_exactly_at_end_is_full_value(self, investment_bare):
        assert investment_bare.get_estimated_value(datetime.date(2030, 1, 1)) == Money(
            Decimal("21600.00"), "EUR"
        )

    def test_bare_ownership_degenerate_total_days_zero(self, scpi):
        """When start == end, treat as fully reconstituted (100%)."""
        SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2019, 12, 31),
            subscription_value=Money(Decimal("1000.00"), "EUR"),
        )
        inv = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=datetime.date(2020, 1, 1),
            shares_count=Decimal("5.0000"),
            unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
            ownership_type=SCPIInvestment.OwnershipType.BARE,
            dismemberment_start_date=datetime.date(2020, 1, 1),
            dismemberment_end_date=datetime.date(2020, 1, 1),  # same as start
            bare_ownership_ratio=Decimal("65.00"),
        )
        # total_days = 0 → ratio = 100% → full value
        assert inv.get_estimated_value(datetime.date(2020, 1, 1)) == Money(
            Decimal("5000.00"), "EUR"
        )

    def test_estimated_value_bare_missing_dismemberment_returns_full(self, scpi):
        """BARE investment without dismemberment fields returns full value (fallback)."""
        inv = SCPIInvestment(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("5.0000"),
            unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
            ownership_type=SCPIInvestment.OwnershipType.BARE,
        )
        # Falls back to full value (purchase price since no share price)
        result = inv.get_estimated_value(datetime.date(2023, 6, 1))
        assert result == Money(Decimal("5000.00"), "EUR")

    def test_bare_ownership_at_start_with_known_share_price(self, scpi):
        """Verify ratio at start when a share price is available before or on the start date."""
        SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2019, 12, 31),
            subscription_value=Money(Decimal("1000.00"), "EUR"),
        )
        inv = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=datetime.date(2020, 1, 1),
            shares_count=Decimal("20.0000"),
            unit_purchase_price=Money(Decimal("650.00"), "EUR"),
            ownership_type=SCPIInvestment.OwnershipType.BARE,
            dismemberment_start_date=datetime.date(2020, 1, 1),
            dismemberment_end_date=datetime.date(2030, 1, 1),
            bare_ownership_ratio=Decimal("65.00"),
        )
        # full_value = 20 × 1000 = 20_000 ; bare 65% = 13_000
        assert inv.get_estimated_value(datetime.date(2020, 1, 1)) == Money(
            Decimal("13000.00"), "EUR"
        )


# ── SCPIInvestment — resale value ─────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIInvestmentResaleValue:
    def test_resale_with_no_exit_fee(self, investment_full):
        # gross = 10 × 1020 = 10_200 ; no exit fees ; entry_fees = 10_000 × 8% = 800
        # net resale = 10_200 - 800 = 9_400
        today = datetime.date(2025, 1, 1)
        assert investment_full.get_estimated_resale_value(today) == Money(
            Decimal("9400.00"), "EUR"
        )

    def test_resale_with_exit_fee(self):
        scpi = SCPI.objects.create(
            name="Exit Fee SCPI",
            exit_fee_rate=Decimal("2.00"),
        )
        SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2024, 1, 1),
            subscription_value=Money(Decimal("1000.00"), "EUR"),
            withdrawal_value=Money(Decimal("1000.00"), "EUR"),
        )
        inv = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("10.0000"),
            unit_purchase_price=Money(Decimal("900.00"), "EUR"),
        )
        # gross = 10 × 1000 = 10_000 ; exit_fee = 200 ; after_exit = 9_800
        # entry_fees = 0 (no entry_fee_rate on this scpi)
        # net resale = 9_800
        assert inv.get_estimated_resale_value(datetime.date(2025, 1, 1)) == Money(
            Decimal("9800.00"), "EUR"
        )

    def test_resale_falls_back_to_purchase_when_no_share_price(self):
        scpi = SCPI.objects.create(name="No Price SCPI 2")
        inv = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("5.0000"),
            unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
        )
        # Falls back to purchase value: 5 × 1000 = 5_000
        assert inv.get_estimated_resale_value(datetime.date(2025, 1, 1)) == Money(
            Decimal("5000.00"), "EUR"
        )


# ── SCPIInvestment — capital gain ─────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIInvestmentCapitalGain:
    def test_capital_gain_positive(self, investment_full):
        # New semantics:
        # total_invested = 10 × 1000 = 10_000
        # resale = 10 × 1020 - 800 (entry_fees) = 9_400
        # gain = 9_400 - 10_000 = -600
        today = datetime.date(2025, 1, 1)
        gain = investment_full.get_capital_gain(today)
        assert gain == Money(Decimal("-600.00"), "EUR")

    def test_capital_gain_default_date_is_today(self, investment_full):
        gain = investment_full.get_capital_gain()
        assert gain.currency.code == "EUR"


# ── SCPI — dividends ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIDividendMethods:
    def test_get_total_dividends_empty(self, scpi_with_price):
        assert scpi_with_price.get_total_dividends_received() == Money(
            Decimal("0"), "EUR"
        )

    def test_get_total_dividends_sum(self, scpi_with_price):
        SCPIDividend.objects.create(
            scpi=scpi_with_price,
            payment_date=datetime.date(2024, 3, 31),
            net_amount=Money(Decimal("120.00"), "EUR"),
        )
        SCPIDividend.objects.create(
            scpi=scpi_with_price,
            payment_date=datetime.date(2024, 6, 30),
            gross_amount=Money(Decimal("155.00"), "EUR"),
            net_amount=Money(Decimal("130.00"), "EUR"),
        )
        total = scpi_with_price.get_total_dividends_received()
        assert total == Money(Decimal("250.00"), "EUR")

    def test_get_dividends_in_period(self, scpi_with_price):
        SCPIDividend.objects.create(
            scpi=scpi_with_price,
            payment_date=datetime.date(2024, 3, 31),
            net_amount=Money(Decimal("120.00"), "EUR"),
        )
        SCPIDividend.objects.create(
            scpi=scpi_with_price,
            payment_date=datetime.date(2023, 6, 30),
            net_amount=Money(Decimal("50.00"), "EUR"),
        )
        total = scpi_with_price.get_dividends_received_in_period(
            datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)
        )
        assert total == Money(Decimal("120.00"), "EUR")


# ── SCPIInvestment — clean() validation ───────────────────────────────────────


@pytest.mark.django_db
class TestSCPIInvestmentClean:
    def test_clean_bare_ownership_missing_fields_raises(self, scpi):
        inv = SCPIInvestment(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("10.0000"),
            unit_purchase_price=Money(Decimal("650.00"), "EUR"),
            ownership_type=SCPIInvestment.OwnershipType.BARE,
            # Missing: dismemberment_start_date, dismemberment_end_date, bare_ownership_ratio
        )
        with pytest.raises(ValidationError):
            inv.clean()

    def test_clean_bare_ownership_end_before_start_raises(self, scpi):
        inv = SCPIInvestment(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("10.0000"),
            unit_purchase_price=Money(Decimal("650.00"), "EUR"),
            ownership_type=SCPIInvestment.OwnershipType.BARE,
            dismemberment_start_date=datetime.date(2025, 1, 1),
            dismemberment_end_date=datetime.date(2020, 1, 1),  # before start
            bare_ownership_ratio=Decimal("65.00"),
        )
        with pytest.raises(ValidationError):
            inv.clean()

    def test_clean_bare_ownership_ratio_out_of_range_raises(self, scpi):
        inv = SCPIInvestment(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("10.0000"),
            unit_purchase_price=Money(Decimal("650.00"), "EUR"),
            ownership_type=SCPIInvestment.OwnershipType.BARE,
            dismemberment_start_date=datetime.date(2020, 1, 1),
            dismemberment_end_date=datetime.date(2030, 1, 1),
            bare_ownership_ratio=Decimal("110.00"),  # > 100
        )
        with pytest.raises(ValidationError):
            inv.clean()

    def test_clean_full_ownership_no_validation_error(self, scpi):
        inv = SCPIInvestment(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("10.0000"),
            unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
            ownership_type=SCPIInvestment.OwnershipType.FULL,
        )
        inv.clean()  # should not raise


# ── SCPIDividend model ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIDividend:
    def test_str(self, scpi_with_price):
        div = SCPIDividend.objects.create(
            scpi=scpi_with_price,
            payment_date=datetime.date(2024, 3, 31),
            net_amount=Money(Decimal("120.00"), "EUR"),
        )
        result = str(div)
        assert "Corum Eurion" in result
        assert "2024-03-31" in result
        assert "120.00" in result

    def test_gross_amount_optional(self, scpi_with_price):
        div = SCPIDividend.objects.create(
            scpi=scpi_with_price,
            payment_date=datetime.date(2024, 3, 31),
            net_amount=Money(Decimal("100.00"), "EUR"),
        )
        assert div.gross_amount is None


# ── Additional coverage ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIModelCoverage:
    def test_current_withdrawal_value_none_when_no_prices(self, scpi):
        """SCPI.current_withdrawal_value returns None when no share prices exist."""
        assert scpi.current_withdrawal_value is None

    def test_investment_str(self, investment_full):
        """SCPIInvestment.__str__ is callable."""
        result = str(investment_full)
        assert "Corum Eurion" in result

    def test_get_current_full_value_no_args_uses_today(self, investment_full):
        """get_current_full_value() with no args defaults to today without error."""
        val = investment_full.get_current_full_value()
        assert val.currency.code == "EUR"

    def test_get_estimated_value_no_args_uses_today(self, investment_full):
        """get_estimated_value() with no args defaults to today without error."""
        val = investment_full.get_estimated_value()
        assert val.currency.code == "EUR"

    def test_get_estimated_resale_value_no_args_uses_today(self, investment_full):
        """get_estimated_resale_value() with no args defaults to today."""
        val = investment_full.get_estimated_resale_value()
        assert val.currency.code == "EUR"

    def test_get_exit_fees_no_args_uses_today(self, investment_full):
        """get_exit_fees() with no args defaults to today."""
        val = investment_full.get_exit_fees()
        assert val.currency.code == "EUR"

    def test_get_exit_fees_with_no_share_price_uses_purchase_value(self):
        """get_exit_fees falls back to purchase value when no share price exists."""
        scpi = SCPI.objects.create(name="Fee SCPI", exit_fee_rate=Decimal("2.00"))
        inv = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("5.0000"),
            unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
        )
        # withdrawal is None → gross = 5 × 1000 = 5000 ; fee = 5000 × 2% = 100
        assert inv.get_exit_fees(datetime.date(2025, 1, 1)) == Money(
            Decimal("100.00"), "EUR"
        )

    def test_get_exit_fees_with_share_price_and_exit_rate(self):
        """get_exit_fees with share price applies the exit fee rate."""
        scpi = SCPI.objects.create(name="Fee SCPI 2", exit_fee_rate=Decimal("2.00"))
        SCPISharePrice.objects.create(
            scpi=scpi,
            date=datetime.date(2024, 1, 1),
            subscription_value=Money(Decimal("1000.00"), "EUR"),
            withdrawal_value=Money(Decimal("950.00"), "EUR"),
        )
        inv = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=datetime.date(2023, 1, 1),
            shares_count=Decimal("10.0000"),
            unit_purchase_price=Money(Decimal("900.00"), "EUR"),
        )
        # gross = 10 × 950 = 9500 ; fee = 9500 × 2% = 190
        assert inv.get_exit_fees(datetime.date(2025, 1, 1)) == Money(
            Decimal("190.00"), "EUR"
        )
