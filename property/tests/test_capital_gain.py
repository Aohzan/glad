"""Tests for the capital gain estimate of a property sale."""

import datetime
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from moneyed import Money

from base.models import Ownership
from property.models import AmortizationAsset, Property
from property.services import capital_gain, tax_lmnp
from property.services.capital_gain import (
    ResaleInputs,
    deducted_building_amortization,
    estimate_resale,
    income_tax_allowance,
    social_charges_allowance,
    surtax,
)

D = datetime.date


class TestAllowances:
    @pytest.mark.parametrize(
        ("years", "expected"), [(5, 0), (6, 6), (21, 96), (22, 100), (40, 100)]
    )
    def test_income_tax(self, years, expected):
        assert income_tax_allowance(years) == Decimal(expected)

    @pytest.mark.parametrize(
        ("years", "expected"),
        [
            (5, "0"),
            (6, "1.65"),
            (21, "26.40"),
            (22, "28"),
            (23, "37"),
            (29, "91"),
            (30, "100"),
        ],
    )
    def test_social_charges(self, years, expected):
        assert social_charges_allowance(years) == Decimal(expected)


class TestSurtax:
    @pytest.mark.parametrize(
        ("gain", "expected"),
        [
            (50000, "0"),
            (55000, "850.00"),
            (80000, "1600.00"),
            (105000, "2650.00"),
            (120000, "3600.00"),
            (155000, "5450.00"),
            (180000, "7200.00"),
            (205000, "9250.00"),
            (230000, "11500.00"),
            (255000, "14050.00"),
            (300000, "18000.00"),
        ],
    )
    def test_bands(self, gain, expected):
        assert surtax(Decimal(gain)) == Decimal(expected)


@pytest.fixture
def house(db):
    return Property.objects.create(
        name="Sold house",
        property_type=Property.HOUSE,
        buying_value=Money(200000, "EUR"),
        notary_fees=Money(15000, "EUR"),
        buying_date=D(2016, 1, 1),
    )


def _inputs(**kwargs) -> ResaleInputs:
    base = ResaleInputs(
        sale_price=Decimal(300000),
        sale_date=D(2026, 6, 1),
        seller_fees=Decimal(10000),
    )
    return replace(base, **kwargs)


@pytest.mark.django_db
class TestEstimate:
    def test_standard_sale(self, house):
        estimate = estimate_resale(house, _inputs())
        assert estimate.holding_years == 10
        assert estimate.acquisition_fees == Decimal(15000)
        assert estimate.flat_fees_used is False
        assert estimate.works == Decimal("30000.00")
        assert estimate.flat_works_used is True
        assert estimate.adjusted_cost == Decimal(245000)
        assert estimate.gross_gain == Decimal(45000)
        assert estimate.taxable_income_tax == Decimal("31500.00")
        assert estimate.income_tax == Decimal("5985.00")
        assert estimate.taxable_social_charges == Decimal("41287.50")
        assert estimate.social_charges == Decimal("7101.45")
        assert estimate.surtax == 0
        assert estimate.total_tax == Decimal("13086.45")
        assert estimate.net_proceeds == Decimal("276913.55")

    def test_flat_fees_and_actual_works(self, house):
        house.notary_fees = Money(1000, "EUR")
        house.save()
        estimate = estimate_resale(
            house, _inputs(actual_works=Decimal(40000), sale_date=D(2019, 1, 1))
        )
        assert estimate.acquisition_fees == Decimal("15000.00")
        assert estimate.flat_fees_used is True
        assert estimate.works == Decimal(40000)
        assert estimate.flat_works_used is False
        assert estimate.income_tax_allowance == 0

    def test_flat_works_after_five_years(self, house):
        house.buying_date = D(2020, 3, 1)
        house.save()
        estimate = estimate_resale(house, _inputs(sale_date=D(2025, 9, 1)))
        assert estimate.holding_years == 5
        assert estimate.works == Decimal("30000.00")
        exactly = estimate_resale(house, _inputs(sale_date=D(2025, 3, 1)))
        assert exactly.works == 0

    def test_main_residence_is_exempt(self, house):
        estimate = estimate_resale(house, _inputs(main_residence=True))
        assert estimate.is_exempt is True
        assert estimate.total_tax == 0

    def test_loss(self, house):
        estimate = estimate_resale(house, _inputs(sale_price=Decimal(150000)))
        assert estimate.gross_gain < 0
        assert estimate.total_tax == 0

    def test_surtax_per_seller(self, house):
        estimate = estimate_resale(
            house,
            _inputs(
                sale_price=Decimal(500000),
                seller_shares=(Decimal(50), Decimal(50)),
            ),
        )
        # Taxable gain 245,000 × 70 % = 171,500, i.e. 85,750 per seller.
        assert estimate.taxable_income_tax == Decimal("171500.00")
        assert estimate.surtax_by_seller == [Decimal("1715.00")] * 2
        assert estimate.surtax == Decimal("3430.00")


def _asset(prop, category):
    return AmortizationAsset.objects.create(
        property=prop,
        label=category,
        beginning_date=D(2020, 1, 1),
        value_total=Money(10000, "EUR"),
        duration_years=10,
        cerfa_category=category,
    )


@pytest.mark.django_db
class TestLmnpReintegration:
    def _lmnp(self, house, monkeypatch, results):
        house.tax_regime = Property.TaxRegime.LMNP_REEL
        house.save()
        _asset(house, AmortizationAsset.CerfaCategory.CONSTRUCTIONS)
        _asset(house, AmortizationAsset.CerfaCategory.AUTRES)
        monkeypatch.setattr(
            AmortizationAsset,
            "get_annual_amortization",
            lambda self, year: Decimal(0) if year == 2021 else Decimal(750),
        )
        monkeypatch.setattr(tax_lmnp, "compute_activity", lambda pk, year: results)

    def test_building_share_of_the_deducted_amortization(self, house, monkeypatch):
        results = [
            SimpleNamespace(
                year=2020,
                depreciation_deducted=Decimal(1000),
                deferred_depreciation_used_350=Decimal(0),
            ),
            SimpleNamespace(
                year=2021,
                depreciation_deducted=Decimal(900),
                deferred_depreciation_used_350=Decimal(0),
            ),
            SimpleNamespace(
                year=2022,
                depreciation_deducted=Decimal(1200),
                deferred_depreciation_used_350=Decimal(300),
            ),
        ]
        self._lmnp(house, monkeypatch, results)
        # Half of the dotations are the building's; 2021 has no dotation.
        assert deducted_building_amortization(house, 2026) == Decimal("1250.00")
        estimate = estimate_resale(house, _inputs())
        assert estimate.lmnp_reintegration == Decimal("1250.00")
        assert estimate.gross_gain == Decimal(46250)

    def test_exemptions(self, house, monkeypatch):
        self._lmnp(house, monkeypatch, [])
        assert (
            estimate_resale(house, _inputs(service_residence=True)).lmnp_reintegration
            == 0
        )
        house.tax_regime = Property.TaxRegime.NONE
        house.save()
        assert deducted_building_amortization(house, 2026) == 0

    def test_categories(self):
        assert AmortizationAsset.CerfaCategory.AUTRES not in (
            capital_gain.BUILDING_CATEGORIES
        )


@pytest.mark.django_db
class TestResaleView:
    def test_default_simulation(self, user_client, house):
        response = user_client.get(
            reverse("property:resale_simulation", args=[house.pk])
        )
        assert response.status_code == 200
        assert response.context["estimate"] is not None
        assert 'id="resale-result"' in response.content.decode()

    def test_parameters_and_owners(self, user_client, house):
        for name in ("seller1", "seller2"):
            Ownership.objects.create(
                content_type=ContentType.objects.get_for_model(house),
                object_id=house.pk,
                user=User.objects.create_user(username=name, password="x"),
                share=Decimal(50),
            )
        response = user_client.get(
            reverse("property:resale_simulation", args=[house.pk]),
            {
                "sale_price": "500000",
                "sale_date": "2026-06-01",
                "seller_fees": "",
                "actual_works": "",
            },
        )
        estimate = response.context["estimate"]
        assert estimate.inputs.seller_shares == (Decimal(50), Decimal(50))
        assert estimate.inputs.seller_fees == 0

    def test_invalid_parameters(self, user_client, house):
        response = user_client.get(
            reverse("property:resale_simulation", args=[house.pk]),
            {"sale_price": "-1", "sale_date": "x"},
        )
        assert response.context["estimate"] is None

    def test_link_on_detail_page(self, user_client, house):
        response = user_client.get(reverse("property:detail", args=[house.pk]))
        assert (
            reverse("property:resale_simulation", args=[house.pk])
            in response.content.decode()
        )
